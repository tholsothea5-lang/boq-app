"""
Site Ledger — Bill of Quantities (accounts edition)
===================================================

A Flask app that serves the BOQ web tool, stores its data server-side (a JSON
file shared by everyone who logs in), keeps per-user accounts, and records an
audit trail of every change each user makes.

Features added on top of the base version:
  - Email + password accounts (werkzeug password hashing, Flask sessions).
  - Roles: "admin" (can do anything, including managing users and viewing the
    audit log), "moderator" (can view the user list and audit log), and "user".
  - First account created on an empty server becomes the admin (setup).
  - Audit log in SQLite: login/logout/register, every data save with a summary
    of exactly what changed, photo uploads, and user management actions.
  - Online box: heartbeat tracking so the app can show who is online and each
    person's role title (Admin / Moderator / User).
  - Admin-only APIs to manage users; staff (admin + moderator) read audit.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000
"""

import csv
import io
import json
import math
import mimetypes
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, session)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "boq_data.json")
PHOTO_DIR = os.path.join(BASE_DIR, "data", "photos")
DB_FILE = os.path.join(BASE_DIR, "data", "ledger.db")
SECRET_FILE = os.path.join(BASE_DIR, "data", "secret_key.txt")
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".jfif"}
MAX_PHOTO_BYTES = 8 * 1024 * 1024

# Roles that may read the user list + audit log (admin can also manage users).
STAFF_ROLES = ("admin", "moderator")
# Online presence: user_id -> last heartbeat (epoch seconds). Kept in memory,
# so it resets on restart — fine for a local tool.
ONLINE = {}

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
if os.path.exists(SECRET_FILE):
    with open(SECRET_FILE, "r", encoding="utf-8") as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(app.secret_key)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 31  # 31 days


# ---------------------------------------------------------------- database

def db_connect():
    """Open the SQLite store (one writer at a time is plenty for this tool)."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def db_init():
    conn = db_connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            email      TEXT NOT NULL,
            action     TEXT NOT NULL,
            detail     TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_when ON audit(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit(user_id);
        """
    )
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def audit(user, action, detail="", email=None):
    """Append one line to the audit trail."""
    try:
        conn = db_connect()
        conn.execute(
            "INSERT INTO audit (user_id, email, action, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user.get("id") if isinstance(user, dict) else user,
             (user.get("email") if isinstance(user, dict) else email) or "",
             action, detail, now_iso()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # never let auditing break the tool itself


def get_user_by_email(email):
    conn = db_connect()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = db_connect()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    user = get_user_by_id(uid)
    if user is None or not user.get("is_active"):
        session.clear()
        return None
    return user


def user_count():
    conn = db_connect()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


# ------------------------------------------------------------------ guards

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not signed in"}), 401
            return redirect("/")
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not signed in"}), 401
            return redirect("/")
        if user.get("role") not in ("admin",):
            return jsonify({"error": "Admins only"}), 403
        return view(*args, **kwargs)
    return wrapped


def staff_required(view):
    """Admin or moderator may pass (read-only panels: users list + audit)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not signed in"}), 401
            return redirect("/")
        if user.get("role") not in STAFF_ROLES:
            return jsonify({"error": "Admin or moderator only"}), 403
        return view(*args, **kwargs)
    return wrapped


# ------------------------------------------------------------- data layer

def node(node_id, name, children=None, **fields):
    """One row of a hierarchy. Sub-rows live in "children"."""    
    row = {"id": node_id, "name": name, "children": children or []}
    row.update(fields)
    return row


def leaf(node_id, name, **fields):
    """An item: the deepest kind of row, the only one carrying a rate."""
    return node(node_id, name, **fields)


DEFAULT_STATE = {
    "projectName": "",
    "theme": "auto",
    "materials": [
        node("mc1", "Build materials", [
            node("ms1", "Binders", [
                leaf("m1", "Cement (Type I)", unit="bag (50kg)", price=6.50),
            ]),
            node("ms2", "Aggregates", [
                leaf("m2", "Gravel, coarse aggregate", unit="m3", price=18.00),
                leaf("m3", "Sand, fine aggregate", unit="m3", price=14.00),
            ]),
            node("ms3", "Boards", [
                leaf("m4", "Gypsum board, 12mm", unit="sheet", price=9.20),
                leaf("m5", "Cement board, 12mm", unit="sheet", price=15.50),
            ]),
        ]),
    ],
    "labor": [
        node("lc1", "Ceiling work", [
            node("ls1", "Gypsum ceiling", [
                leaf("l1", "Ceiling installation labor", unit="m2", price=4.50),
            ]),
        ]),
        node("lc2", "Floor tiling work", [
            node("ls2", "Tile fixing", [
                leaf("l2", "Floor tiling labor", unit="m2", price=6.00),
            ]),
        ]),
        node("lc3", "Concrete work", [
            node("ls3", "Pouring & placing", [
                leaf("l3", "Concrete pouring labor", unit="m3", price=12.00),
            ]),
        ]),
    ],
    "projects": [
        {
            "id": "p1",
            "name": "Project 1",
            "boq": [
                node("b1", "Sub-structure", [
                    node("b1a", "Excavation", [
                        leaf("b1a1", "Topsoil strip, average 150mm deep", unit="m3", quantity=60),
                        leaf("b1a2", "Trench excavation for footings", unit="m3", quantity=45),
                    ]),
                    node("b1b", "Concrete to foundations", [
                        leaf("b1b1", "Ground floor slab, 150mm thick", unit="m3", quantity=40,
                             materialRef="m1", laborRef="l3"),
                    ]),
                ]),
                node("b2", "Super-structure", [
                    node("b2a", "Suspended ceilings", [
                        leaf("b2a1", "Suspended ceiling, gypsum board", unit="m2", quantity=120,
                             materialRef="m4", laborRef="l1"),
                    ]),
                    node("b2b", "Floor finishes", [
                        leaf("b2b1", "Floor tiling, living areas", unit="m2", quantity=85,
                             materialRef="none", laborRef="l2"),
                    ]),
                ]),
            ],
        },
    ],
    "activeProjectId": "p1",
}

# Fields each level needs. A heading ignores them; an item falls back to them.
ITEM_DEFAULTS = {
    "boq": {"unit": "", "quantity": 0, "materialRef": "none", "laborRef": "none",
            "customMaterialPrice": 0, "customLaborPrice": 0},
    "materials": {"unit": "", "price": 0, "quantity": 0, "note": "", "photos": []},
    "labor": {"unit": "", "price": 0},
}
def repair_rows(rows, kind, next_id):
    """Make sure every row has an id, a name, a children list and the fields its
    level needs. Missing values are filled in; nothing is ever dropped."""
    out = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["id"] = row.get("id") or next_id()
        row["name"] = row.get("name") or row.get("description") or ""
        for field, value in ITEM_DEFAULTS[kind].items():
            if row.get(field) is None:
                row[field] = value
        row["children"] = repair_rows(row.get("children"), kind, next_id)
        out.append(row)
    return out


def flat_to_tree(rows, kind, next_id):
    """The first version stored one flat row per item, tagged with a "category"
    and a "subcategory". Rebuild exactly that as category -> sub-category ->
    item, so the classification is kept and each item keeps its own id (which
    is what the bill's materialRef / laborRef point at)."""
    roots = []
    by_category = {}
    by_sub = {}
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        category = raw.get("category") or "Uncategorized"
        subcategory = raw.get("subcategory") or "General"

        root = by_category.get(category)
        if root is None:
            root = node(next_id(), category)
            by_category[category] = root
            roots.append(root)

        key = category + "\x00" + subcategory
        group = by_sub.get(key)
        if group is None:
            group = node(next_id(), subcategory)
            by_sub[key] = group
            root["children"].append(group)

        item = dict(raw)
        item.pop("category", None)
        item.pop("subcategory", None)
        item["children"] = []
        group["children"].append(item)

    return repair_rows(roots, kind, next_id)


def normalize_project(raw, next_id):
    """Guarantee one project's shape: {id, name, boq hierarchy}."""
    if not isinstance(raw, dict):
        raw = {}
    boq = raw.get("boq")
    if not isinstance(boq, list):
        boq = []
    needs_rebuild = any(isinstance(r, dict) and "children" not in r for r in boq)
    if needs_rebuild:
        boq = flat_to_tree(boq, "boq", next_id)
    else:
        boq = repair_rows(boq, "boq", next_id)
    return {
        "id": raw.get("id") or next_id(),
        "name": raw.get("name") or "Untitled project",
        "boq": boq,
    }


def normalize_state(state):
    """Guarantee the shape the web page expects: a hierarchy per rate list and
    a list of projects, each carrying its own bill of quantities. An older
    single-bill file is wrapped into one project, so nothing is ever lost."""
    if not isinstance(state, dict):
        state = dict(DEFAULT_STATE)

    counter = [0]

    def next_id():
        counter[0] += 1
        return "auto{}".format(counter[0])

    for key in ("materials", "labor"):
        rows = state.get(key)
        if not isinstance(rows, list):
            state[key] = []
            continue
        needs_rebuild = any(
            isinstance(r, dict) and "children" not in r for r in rows
        )
        if needs_rebuild:
            state[key] = flat_to_tree(rows, key, next_id)
        else:
            state[key] = repair_rows(rows, key, next_id)

    projects = state.get("projects")
    if not isinstance(projects, list) or not projects:
        # Legacy file: one top-level "boq". Wrap it into a project, keeping the
        # old project name.
        legacy = state.get("boq")
        if not isinstance(legacy, list):
            legacy = []
        needs_rebuild = any(isinstance(r, dict) and "children" not in r for r in legacy)
        if needs_rebuild:
            legacy = flat_to_tree(legacy, "boq", next_id)
        else:
            legacy = repair_rows(legacy, "boq", next_id)
        projects = [{
            "id": "p1",
            "name": state.get("projectName") or "Project 1",
            "boq": legacy,
        }]
    state["projects"] = [normalize_project(p, next_id) for p in projects]

    active = state.get("activeProjectId")
    if not any(p["id"] == active for p in state["projects"]):
        state["activeProjectId"] = state["projects"][0]["id"]

    # The single-bill keys are retired; the active project's name is mirrored
    # into projectName so older bookmarks/filenames keep working.
    state.pop("boq", None)
    active_project = next(p for p in state["projects"] if p["id"] == state["activeProjectId"])
    state["projectName"] = active_project["name"]

    if not state.get("theme"):
        state["theme"] = "auto"
    return state


def ensure_data_file():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STATE, f, indent=2)


def read_state():
    ensure_data_file()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return normalize_state(json.load(f))


def write_state(state):
    ensure_data_file()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(normalize_state(state), f, indent=2)

def find_leaf(nodes, node_id):
    """Find a priced item anywhere in a hierarchy. Rows that have sub-rows are
    headings, so they are skipped: a heading is never used as a rate."""
    for row in nodes or []:
        if not isinstance(row, dict):
            continue
        children = row.get("children") or []
        if children:
            found = find_leaf(children, node_id)
            if found:
                return found
        elif row.get("id") == node_id:
            return row
    return None


def money(v):
    """Every price in the tool is USD; the CSV says so on every money cell."""
    return "${:.2f}".format(float(v or 0))


def row_rate(state, row, which):
    """Unit rate for one side of a bill row: a price typed on the row wins,
    otherwise the rate inherited from the rate list it references."""
    is_material = which == "material"
    ref = row.get("materialRef") if is_material else row.get("laborRef")
    custom = float(row.get("customMaterialPrice") or 0) if is_material \
        else float(row.get("customLaborPrice") or 0)
    if custom > 0:
        return custom
    if not ref or ref == "none" or ref == "custom":
        return 0.0
    tree = state.get("materials" if is_material else "labor", [])
    hit = find_leaf(tree, ref)
    return float(hit.get("price") or 0) if hit else 0.0


def round_up2(v):
    """Excel ROUNDUP(x, 2): always round up to 2 decimals."""
    return math.ceil(float(v or 0) * 100) / 100


def qty_markup_pct(row):
    p = float(row.get("qtyMarkupPct") or 0)
    return p if p > 0 else 0.0


def qty_charged(row):
    """Charged quantity = drawing quantity x (1 + quantity mark-up %), rounded
    up to 2 decimals, exactly like the Excel detail sheets."""
    quantity = float(row.get("quantity") or 0)
    if not quantity:
        return 0.0
    return round_up2(quantity * (1 + qty_markup_pct(row) / 100))


def original_rate(state, row, which):
    """Original (base) unit rate: the row's Original Rate when given, else the
    per-row custom price, else the rate inherited from the referenced list."""
    is_material = which == "material"
    orig = float(row.get("originalMaterial") or 0) if is_material \
        else float(row.get("originalLabor") or 0)
    if orig > 0:
        return orig
    return row_rate(state, row, which)


def final_rate(state, row, which):
    """Final unit rate used for pricing. When an Original Rate is entered apply
    the mark-up percentage like the Excel sheets (Rate = ROUNDUP(Original +
    Original x mark-up %)). Rows without an Original Rate keep the legacy
    behavior (custom price or the referenced rate list)."""
    is_material = which == "material"
    orig = float(row.get("originalMaterial") or 0) if is_material \
        else float(row.get("originalLabor") or 0)
    if orig > 0:
        markup = float(row.get("materialMarkup") or 0) if is_material \
            else float(row.get("laborMarkup") or 0)
        return round_up2(orig * (1 + markup / 100))
    return row_rate(state, row, which)


def material_total(state, row):
    return final_rate(state, row, "material") * qty_charged(row)


def labor_total(state, row):
    return final_rate(state, row, "labor") * qty_charged(row)


def own_amount(state, row):
    """What a row is worth on its own: Amount = Total M + Total L."""
    return material_total(state, row) + labor_total(state, row)


def own_budget(state, row):
    """Budget = original rates x charged quantity (M + L)."""
    return (original_rate(state, row, "material") +
            original_rate(state, row, "labor")) * qty_charged(row)


def subtree_total(state, row):
    """A row is worth its own amount plus everything filed underneath it, so a
    heading shows the subtotal of its whole branch and nothing is counted twice."""
    total = own_amount(state, row)
    for child in row.get("children") or []:
        total += subtree_total(state, child)
    return total


def subtree_budget(state, row):
    total = own_budget(state, row)
    for child in row.get("children") or []:
        total += subtree_budget(state, child)
    return total


def subtree_profit(state, row):
    return subtree_total(state, row) - subtree_budget(state, row)


def is_heading(row):
    return bool(row.get("children"))


def walk(rows, prefix=()):
    """Depth-first, yielding (reference, row) in the order the rows are drawn."""
    for index, row in enumerate(rows or [], start=1):
        ref = prefix + (index,)
        yield ref, row
        yield from walk(row.get("children") or [], ref)


# ------------------------------------------------------------- audit diff

# Visible field names per kind, so the audit trail reads like English.
FIELD_LABELS = {
    "boq": {"name": "description", "unit": "unit", "quantity": "quantity",
            "materialRef": "material", "laborRef": "labor",
            "customMaterialPrice": "material price", "customLaborPrice": "labor price"},
    "materials": {"name": "name", "unit": "unit", "price": "unit price",
                  "quantity": "quantity", "note": "note"},
    "labor": {"name": "name", "unit": "unit", "price": "unit price"},
}


def _row_path(rows, node_id, trail=()):
    """Return the human path to a row (parent names), or an empty tuple."""
    for i, row in enumerate(rows or []):
        if row.get("id") == node_id:
            return trail + ((row.get("name") or "?"),)
        found = _row_path(row.get("children") or [], node_id, trail + ((row.get("name") or "?"),))
        if found:
            return found
    return ()


def _tree_index(rows):
    """Map row id -> row for one kind of tree."""
    out = {}
    for row in rows or []:
        out[row["id"]] = row
        out.update(_tree_index(row.get("children") or []))
    return out


def _changed_fields(kind, old, new):
    """Human-readable list of which fields changed between two rows."""
    out = []
    labels = FIELD_LABELS.get(kind, {})
    for field, label in labels.items():
        if field == "name":
            continue
        ov, nv = old.get(field), new.get(field)
        if ov == nv:
            continue
        if kind == "boq" and field in ("materialRef", "laborRef"):
            ov = ov if ov and ov != "none" else "—"
            nv = nv if nv and nv != "none" else "—"
        out.append("{}: {} → {}".format(label, ov, nv))
    return out


def summarize_state_change(old, new, kind, label):
    """Describe what changed between the old and new tree of one kind
    (materials, labor, or one project's boq). Returns a list of short lines."""
    lines = []
    old_idx = _tree_index(old)
    new_idx = _tree_index(new)
    for nid in sorted(set(old_idx) - set(new_idx)):
        row = old_idx[nid]
        path = "/".join(_row_path(old, nid))
        lines.append("Removed {} '{}' from {}".format(_item_word(kind), row.get("name") or "?", path or label))
    for nid in sorted(set(new_idx) - set(old_idx)):
        row = new_idx[nid]
        path = "/".join(_row_path(new, nid))
        lines.append("Added {} '{}' to {}".format(_item_word(kind), row.get("name") or "?", path or label))
    for nid in set(old_idx) & set(new_idx):
        ov, nv = old_idx[nid], new_idx[nid]
        changes = _changed_fields(kind, ov, nv)
        if ov.get("name") != nv.get("name"):
            path = "/".join(_row_path(new, nid))
            changes.insert(0, "renamed '{}' → '{}' ({})".format(ov.get("name") or "?", nv.get("name") or "?", path or label))
        for line in changes:
            where = "/".join(_row_path(new, nid)) or label
            lines.append("{}: {}".format(where, line))
    return lines


def _item_word(kind):
    return {"boq": "bill row", "materials": "material", "labor": "labor item"}.get(kind, "row")


def summarize_save(old_state, new_state):
    """Summarise a whole data save into a compact, human-readable audit entry."""
    summary = []
    old_state = normalize_state(old_state)
    new_state = normalize_state(new_state)

    summary += summarize_state_change(old_state.get("materials") or [],
                                      new_state.get("materials") or [],
                                      "materials", "Materials")
    summary += summarize_state_change(old_state.get("labor") or [],
                                      new_state.get("labor") or [],
                                      "labor", "Labor")

    old_projects = {p["id"]: p for p in old_state.get("projects") or []}
    new_projects = {p["id"]: p for p in new_state.get("projects") or []}
    for pid in sorted(set(old_projects) - set(new_projects)):
        summary.append("Deleted project '{}'".format(old_projects[pid].get("name") or "?"))
    for pid in sorted(set(new_projects) - set(old_projects)):
        summary.append("Added project '{}'".format(new_projects[pid].get("name") or "?"))
    for pid in set(old_projects) & set(new_projects):
        op, np = old_projects[pid], new_projects[pid]
        if op.get("name") != np.get("name"):
            summary.append("Renamed project '{}' → '{}'".format(op.get("name") or "?", np.get("name") or "?"))
        summary += summarize_state_change(op.get("boq") or [], np.get("boq") or [],
                                          "boq", "BOQ · " + (np.get("name") or "?"))

    if not summary:
        return "No changes"
    if len(summary) > 24:
        summary = summary[:24] + ["…and {} more".format(len(summary) - 24)]
    return "; ".join(summary)


# ------------------------------------------------------------------ routes

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    payload = request.get_json(force=True, silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        audit(None, "login.failed", "email={}".format(email), email=email)
        return jsonify({"error": "Wrong email or password"}), 401
    if not user.get("is_active"):
        return jsonify({"error": "This account has been deactivated"}), 403
    session.permanent = True
    session["user_id"] = user["id"]
    audit(user, "login", "Signed in")
    return jsonify({"ok": True, "user": _public_user(user)})


@app.route("/register", methods=["POST"])
def register():
    payload = request.get_json(force=True, silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or len(email) > 254 or "@" not in email:
        return jsonify({"error": "Enter a valid email address"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    is_first = user_count() == 0
    if get_user_by_email(email):
        return jsonify({"error": "That email is already registered"}), 409
    conn = db_connect()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, role, is_active, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (email, generate_password_hash(password),
             "admin" if is_first else "user", now_iso()),
        )
        conn.commit()
        uid = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"error": "That email is already registered"}), 409
    conn.close()
    user = get_user_by_id(uid)
    audit(user, "register", "Created account" + (" (first account — admin)" if is_first else ""))
    session.permanent = True
    session["user_id"] = uid
    return jsonify({"ok": True, "user": _public_user(user), "first": is_first})


@app.route("/logout", methods=["POST"])
def logout():
    user = current_user()
    if user:
        audit(user, "logout", "Signed out")
    session.clear()
    return jsonify({"ok": True})


def _public_user(user):
    return {"id": user["id"], "email": user["email"], "role": user["role"],
            "isActive": bool(user["is_active"])}


@app.route("/api/me")
def api_me():
    user = current_user()
    if user:
        return jsonify({"user": _public_user(user)})
    return jsonify({"needsSetup": user_count() == 0})


@app.route("/api/data", methods=["GET"])
@login_required
def get_data():
    return jsonify(read_state())


@app.route("/api/data", methods=["POST"])
@login_required
def save_data():
    user = current_user()
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict) or not {"materials", "labor"}.issubset(payload):
        return jsonify({"error": "Invalid payload"}), 400
    if not (isinstance(payload.get("projects"), list) or isinstance(payload.get("boq"), list)):
        return jsonify({"error": "Invalid payload"}), 400
    detail = summarize_save(read_state(), payload)
    write_state(payload)
    audit(user, "data.saved", detail)
    return jsonify({"status": "ok"})


@app.route("/api/export.csv")
@login_required
def export_csv():
    state = read_state()
    projects = state.get("projects") or []
    wanted = request.args.get("project") or state.get("activeProjectId")
    project = next((p for p in projects if p.get("id") == wanted), None) \
        or (projects[0] if projects else None)
    boq = project.get("boq") if project else []
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ref", "Level", "Work description", "Brand", "Unit", "Quantity",
                     "Qty markup %", "Charged qty", "Material price", "Labor price",
                     "Original rate material", "Original rate labour",
                     "Mark up % material", "Mark up % labour", "Rate material",
                     "Rate labour", "Total material", "Total labour", "Amount",
                     "Budget", "Profit", "Remark"])

    for ref, row in walk(boq):
        level = len(ref)
        ref_text = ".".join(str(part) for part in ref)
        # Indent by level, so the parent/child relationship is as visible in the
        # spreadsheet as it is on screen.
        description = "    " * (level - 1) + (row.get("name") or "")

        if is_heading(row):
            # A heading carries no unit and no rate of its own, only the
            # subtotals of everything filed under it.
            writer.writerow([ref_text, level, description, "", "", "", "", "", "",
                             "", "", "", "", "", "", "", "", "",
                             money(subtree_total(state, row)),
                             money(subtree_budget(state, row)),
                             money(subtree_profit(state, row)), ""])
            continue

        writer.writerow([
            ref_text, level, description, row.get("brand") or "",
            row.get("unit") or "",
            float(row.get("quantity") or 0),
            qty_markup_pct(row),
            "{:.2f}".format(round(qty_charged(row) * 100) / 100),
            money(row_rate(state, row, "material")),
            money(row_rate(state, row, "labor")),
            money(original_rate(state, row, "material")),
            money(original_rate(state, row, "labor")),
            float(row.get("materialMarkup") or 0),
            float(row.get("laborMarkup") or 0),
            money(final_rate(state, row, "material")),
            money(final_rate(state, row, "labor")),
            money(material_total(state, row)),
            money(labor_total(state, row)),
            money(own_amount(state, row)),
            money(own_budget(state, row)),
            money(own_amount(state, row) - own_budget(state, row)),
            row.get("remark") or "",
        ])

    grand_total = sum(subtree_total(state, row) for row in boq)
    grand_budget = sum(subtree_budget(state, row) for row in boq)
    writer.writerow(["", "", "GRAND TOTAL", "", "", "", "", "", "", "", "", "",
                     "", "", "", "", "", "",
                     money(grand_total), money(grand_budget),
                     money(grand_total - grand_budget), ""])

    filename = ((project.get("name") if project else "") or "bill-of-quantities").strip() \
        or "bill-of-quantities"
    filename = "".join(c for c in filename if c.isalnum() or c in "-_ ").replace(" ", "-") \
        or "bill-of-quantities"

    return Response(
        # The BOM keeps Excel reading the file as UTF-8 (the material and labor
        # paths in it use the "›" separator).
        "\ufeff" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename={}.csv".format(filename)},
    )


@app.route("/api/photo/<path:name>")
@login_required
def get_photo(name):
    """Serve a saved material photo. The name is part of the stored URL, so only
    the basename is allowed through — there is no way to walk up directories."""
    if not name or any(part == ".." for part in name.split("/")):
        return jsonify({"error": "Bad photo name"}), 400
    safe = os.path.basename(name)
    path = os.path.join(PHOTO_DIR, safe)
    if not safe or not os.path.isfile(path):
        return jsonify({"error": "Photo not found"}), 404
    with open(path, "rb") as f:
        data = f.read()
    return Response(
        data,
        mimetype=mimetypes.guess_type(safe)[0] or "image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.route("/api/photo", methods=["POST"])
@login_required
def upload_photo():
    """Store one photo on the server and return the URL to put on a material row.

    Multipart form:
        file    the image to store
        id      the material row id, used only to build the filename
        replace the filename of a photo being swapped out (optional)
    The row's photos list itself is owned by the client, which saves it with the
    rest of the state, so nothing else happens here beyond storing the bytes."""
    user = current_user()
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "No file sent"}), 400
    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXT:
        return jsonify({"error": "Only image files are supported"}), 400

    data = upload.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        return jsonify({"error": "Photo too large (8 MB max)"}), 413

    node_id = re.sub(r"[^A-Za-z0-9_-]", "_", request.form.get("id", "") or "photo") or "photo"
    if ext == ".jfif":
        ext = ".jpeg"
    name = "{}_{}_{}".format(node_id, uuid.uuid4().hex[:8], int(time.time())) + ext

    os.makedirs(PHOTO_DIR, exist_ok=True)
    dest = os.path.join(PHOTO_DIR, name)
    with open(dest, "wb") as f:
        f.write(data)

    old = request.form.get("replace", "")
    action = "photo.replaced" if old else "photo.added"
    detail = "Material '{}': {}".format(node_id, name)
    if old:
        detail += " (replaced {})".format(os.path.basename(old))
        old_name = os.path.basename(old)
        if old_name != name and os.path.isfile(os.path.join(PHOTO_DIR, old_name)):
            try:
                os.remove(os.path.join(PHOTO_DIR, old_name))
            except OSError:
                pass
    audit(user, action, detail)

    return jsonify({"url": "/api/photo/" + name})


# ------------------------------------------------- online box (presence)

ONLINE_TIMEOUT = 20  # seconds since last heartbeat before someone is "offline"

def prune_online(now=None):
    now = now or time.time()
    stale = [uid for uid, seen in ONLINE.items() if now - seen > ONLINE_TIMEOUT]
    for uid in stale:
        ONLINE.pop(uid, None)


@app.route("/api/heartbeat", methods=["POST"])
@login_required
def api_heartbeat():
    me = current_user()
    ONLINE[me["id"]] = time.time()
    prune_online()
    return jsonify({"ok": True})


@app.route("/api/online")
@login_required
def api_online():
    me = current_user()
    ONLINE[me["id"]] = time.time()  # you are online too
    prune_online()
    conn = db_connect()
    rows = conn.execute(
        "SELECT id, email, role, is_active, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    now = time.time()
    out = []
    for r in rows:
        d = dict(r)
        d["is_online"] = now - ONLINE.get(d["id"], 0) <= ONLINE_TIMEOUT
        out.append(d)
    return jsonify(out)


# ----------------------------------------------------------- admin routes

@app.route("/api/admin/users")
@staff_required
def admin_users():
    conn = db_connect()
    rows = conn.execute(
        "SELECT id, email, role, is_active, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/users/<int:uid>", methods=["PATCH"])
@admin_required
def admin_update_user(uid):
    actor = current_user()
    target = get_user_by_id(uid)
    if target is None:
        return jsonify({"error": "No such user"}), 404
    payload = request.get_json(force=True, silent=True) or {}
    conn = db_connect()
    if "role" in payload and payload["role"] in ("admin", "moderator", "user"):
        if uid == actor["id"] and payload["role"] != "admin":
            conn.close()
            return jsonify({"error": "You cannot remove your own admin role"}), 400
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (payload["role"], uid))
        audit(actor, "user.role", "Set {} to {}".format(target["email"], payload["role"]))
    if "isActive" in payload and isinstance(payload["isActive"], bool):
        if uid == actor["id"] and not payload["isActive"]:
            conn.close()
            return jsonify({"error": "You cannot deactivate yourself"}), 400
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?",
                     (1 if payload["isActive"] else 0, uid))
        audit(actor, "user.active",
              "{} {}".format("Activated" if payload["isActive"] else "Deactivated",
                             target["email"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    actor = current_user()
    target = get_user_by_id(uid)
    if target is None:
        return jsonify({"error": "No such user"}), 404
    if uid == actor["id"]:
        return jsonify({"error": "You cannot delete your own account"}), 400
    conn = db_connect()
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
    audit(actor, "user.deleted", "Deleted account {}".format(target["email"]))
    return jsonify({"ok": True})


@app.route("/api/admin/audit")
@staff_required
def admin_audit():
    q = request.args.get("q") or ""
    conn = db_connect()
    if q:
        rows = conn.execute(
            "SELECT id, user_id, email, action, detail, created_at FROM audit "
            "WHERE email LIKE ? OR action LIKE ? OR detail LIKE ? "
            "ORDER BY id DESC LIMIT 300",
            ("%{}%".format(q), "%{}%".format(q), "%{}%".format(q)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, user_id, email, action, detail, created_at FROM audit "
            "ORDER BY id DESC LIMIT 300"
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/reset", methods=["POST"])
@admin_required
def admin_reset():
    user = current_user()
    write_state(DEFAULT_STATE)
    audit(user, "data.reset", "Admin reset the ledger to the default state")
    return jsonify({"ok": True})


if __name__ == "__main__":
    db_init()
    ensure_data_file()
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1",
            host="0.0.0.0", port=port)