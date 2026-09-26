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
    """Excel ROUNDUP(x, 2): always round up to 2 decimals. The -1e-9 slack
    removes binary floating-point artefacts (e.g. 2.2 * 100 = 220.0000...03),
    keeping results identical to Excel's decimal ROUNDUP."""
    x = float(v or 0)
    if x <= 0:
        return 0.0
    return math.ceil(x * 100 - 1e-9) / 100


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
                     "Quantity Mark-up %", "Charged Quantity", "Material Price",
                     "Labour Price", "Original Rate Material", "Original Rate Labour",
                     "Mark-up % Material", "Mark-up % Labour", "Rate Material",
                     "Rate Labour", "Total Material", "Total Labour", "Amount",
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


# ------------------------------------------------------------- Excel export
# Number formats copied from the reference workbook (Excel "accounting" style:
# money shows a "$" sign, budget/profit columns align without one, mark-ups
# display as percentages).
ACCT_CUR = '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)'
ACCT_NUM = '_(* #,##0_);_(* \\(#,##0\\);_(* "-"_);_(@_)'
COVER_CUR = '"$"#,##0.00_);\\("$"#,##0.00\\)'
PCT_FMT = "0%"
QTY_FMT = "0.00"


def _markup_decimal(row, which):
    """Mark-up % stored the way the Excel sheets multiply it (30 -> 0.3). A row
    without an Original Rate keeps its flat price, so its mark-up is 0."""
    if which == "material":
        orig = float(row.get("originalMaterial") or 0)
        markup = float(row.get("materialMarkup") or 0)
    else:
        orig = float(row.get("originalLabor") or 0)
        markup = float(row.get("laborMarkup") or 0)
    return markup / 100 if orig > 0 else 0.0


def _collect_bills(boq):
    """Split the BOQ tree into bill groups, one per top-level section. Loose
    top-level rows that are not headings share a 'WORK ITEMS' sheet."""
    leaves = [row for row in boq if not is_heading(row)]
    heads = [row for row in boq if is_heading(row)]
    groups = []
    if leaves:
        groups.append({"title": "WORK ITEMS", "nodes": leaves})
    for head in heads:
        groups.append({"title": head.get("name") or "ITEM", "nodes": [head]})
    return groups


# ---- Excel visual style layer (mirrors the reference workbook's look) ----
# Arial at every size, red labels on the green "input" columns, yellow header
# bands, an orange GRAND TOTAL band and the black address band on the cover.
# The fills are written as literal RGB values equal to what the reference's
# theme fills resolve to (theme9 + 70AD47 => E2EFDA, theme5 + ED7D31 => FBE5D6,
# theme0 => black), so every engine renders the colours exactly like the
# original.
AR = "Arial"
TNR = "Times New Roman"
RED = "FFFF0000"
YELLOW = "FFFFFF00"
T = "thin"
M = "medium"
# F,G,I,J,K,L are the green "input" columns (quantity / rate / mark-up).
GRAY_F = "FFE2EFDA"     # F/G/I/J/K/L body + header fill
GRAND_F = "FFFBE5D6"    # GRAND TOTAL band fill
BLACK_F = "FF000000"    # cover address band fill (black)
GRAY_COLS = [6, 7, 9, 10, 11, 12]



def _paint(ws, r, c, font=None, sz=10, bold=False, color=None, fill=None,
           fill_theme=None, z=None, top=None, bottom=None, left=None,
           right=None, hal=None, val=None, wrap=False, calibri=False,
           underline=False):
    """Layer font/fill/border/alignment onto a cell without touching its value
    or number format.  Creates the cell when the coordinate has nothing yet.
    Every painted cell carries an explicit font (Calibri 11 when `calibri`,
    otherwise Arial at the requested size - never the engine default).
    `fill_theme` is a literal RGB fill colour; `z` sets the number format
    (useful for styled-empty cells)."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    cell = ws.cell(row=r, column=c)
    if calibri:
        cell.font = Font(name="Calibri", sz=11)
    else:
        cell.font = Font(name=font or AR, sz=sz, bold=bold, color=color,
                         underline="single" if underline else None)
    if fill_theme:
        cell.fill = PatternFill(patternType="solid", fgColor=fill_theme)
    elif fill:
        cell.fill = PatternFill(patternType="solid", fgColor=fill)
    sides = {}
    for style, side in ((top, "top"), (bottom, "bottom"),
                        (left, "left"), (right, "right")):
        if style:
            sides[side] = Side(style=style)
    if sides:
        cell.border = Border(**sides)
    if hal or val or wrap:
        cell.alignment = Alignment(horizontal=hal, vertical=val, wrap_text=wrap)
    if z:
        cell.number_format = z
    return cell


def _set_h(ws, r, hpt):
    ws.row_dimensions[r].height = hpt


def _paint_body_row(ws, r, kind, skip_uaa=False, band_fmt=False, x_money=False,
                    money_colors=None):
    """Paints one table row of a detail sheet (B..R grid + U..AA analysis
    block) for a given kind, reproducing the reference template row-for-row:
    section / leaf / spacer / spacerB / subtotal / grand / bottom.  The green
    input cells carry red text on the theme-9 fill; SUB-TOTAL rows are all-bold
    with no fill and underlined money cells; GRAND TOTAL is all-bold on the
    orange band.  The stray band passes `skip_uaa` because the reference leaves
    its budget block empty.  `band_fmt` applies the ACCT number formats to the
    first band block only (rows 10-12 of the reference), later section bands
    and echoes carry none - exactly as the template is built."""
    is_grand = kind == "grand"
    money = kind in ("subtotal", "grand")
    leafy = kind in ("section", "leaf")
    band = leafy or kind in ("spacer", "spacerB", "bottom")
    _paint(ws, r, 2, bold=money or kind == "section" or kind == "spacerB",
           fill_theme=GRAND_F if is_grand else None,
           left=M, right=T, bottom=M if kind == "bottom" else None, hal="left")
    _paint(ws, r, 18, bold=money, fill_theme=GRAND_F if is_grand else None,
           left=T, right=M, bottom=M if kind == "bottom" else None)
    for c in range(3, 18):  # C..Q
        fmt = None
        bold = money
        color = RED if c in GRAY_COLS else None
        fill_t = None
        if not money:
            if band and c in GRAY_COLS:
                fill_t = GRAY_F
            if kind == "leaf":
                if c == 8:
                    fmt = ACCT_NUM
                elif c in (11, 12):
                    fmt = PCT_FMT
                elif 13 <= c <= 17:
                    fmt = ACCT_CUR
            elif band_fmt and kind in ("section", "spacerB"):
                if c == 8:
                    fmt = ACCT_NUM
                elif 13 <= c <= 17:
                    fmt = ACCT_CUR
            if kind in ("section", "spacerB") and c == 3:
                bold = True
        elif is_grand:
            fill_t = GRAND_F
            if c == 17:
                fmt = ACCT_CUR
        elif c == 17:
            fmt = ACCT_CUR
        _paint(ws, r, c, bold=bold, color=color, fill_theme=fill_t, z=fmt,
               left=T, right=T, bottom=M if kind == "bottom" else None,
               hal="right" if money and c == 3 else None,
               underline=money and c == 17)
    if not skip_uaa:
        for c in (21, 22, 23, 25, 26, 27):
            fmt = ACCT_CUR if money else (ACCT_NUM if kind == "leaf" else None)
            col = (money_colors or {}).get(c) if money else None
            _paint(ws, r, c, sz=10 if money else 11, bold=money, color=col,
                   fill_theme=GRAND_F if is_grand else None, z=fmt,
                   top=T if band else None, bottom=T if band else None,
                   left=T, right=T, underline=money)
        if x_money:
            _paint(ws, r, 24, sz=10 if money else 11, bold=money,
                   fill_theme=GRAND_F if is_grand else None,
                   z=ACCT_CUR if money else None,
                   top=T if band else None, bottom=T if band else None,
                   left=T, right=T, underline=money)


def _paint_gray_cells(ws, r):
    """The six red-on-green 'input' cells (F,G,I,J,K,L) of a row with no
    borders or formats - the mark-up band."""
    for c in GRAY_COLS:
        _paint(ws, r, c, color=RED, fill_theme=GRAY_F)


def _paint_gray_row(ws, r):
    """A whole grid row with no borders (the profit-block filler rows): B..R
    plain Arial 10 with B left-aligned, plus the six red-on-green inputs."""
    _paint(ws, r, 2, hal="left")
    for c in (3, 4, 5, 8, 13, 14, 15, 16, 17, 18):
        _paint(ws, r, c)
    _paint_gray_cells(ws, r)



def _write_bill_header(ws, name, sum_row, l_width, item_count=0, location=""):
    """Rows 1-9 of a detail sheet: title, project block, the two-row grouped
    column header with its merges, and the mark-up source cells. Exactly the
    layout of the reference workbook, shared by the data sheet and the blank
    template copies."""

    def cell(r, c, v=None, **kw):
        cobj = ws.cell(row=r, column=c, value=v)
        _paint(ws, r, c, **kw)
        return cobj

    cell(1, 2, "BILL OF QUANTITY", sz=12, bold=True, hal="center")
    ws.merge_cells("B1:R1")
    cell(2, 2, "Project :")
    cell(2, 3, name)
    cell(3, 2, "Item :")
    cell(3, 3, item_count)
    cell(4, 2, "Location :")
    cell(4, 3, location)
    cell(5, 2, "Date :")
    cell(5, 3, datetime.now().strftime("%d/%m/%Y"))
    cell(6, 2, "Work Scope :")

    # mark-up band: the six input cells are red-on-green, G7 holds the 10%
    _paint_gray_cells(ws, 7)
    g7 = cell(7, 7, "=10%", color=RED, fill_theme=GRAY_F)
    g7.number_format = PCT_FMT
    # the reference also numbers J7 and L7 as percents (styled empty)
    ws["J7"].number_format = PCT_FMT
    ws["L7"].number_format = PCT_FMT
    cell(7, 17, "=SUM!B{}".format(sum_row), bold=True)  # which Bill No. this sheet is

    # Row 8 main header band: yellow on the generic columns, red-on-grey on
    # the input columns F/G/I/J/K/L, plain white on the budget block.  Every
    # border exactly as stored in the reference file.
    header8 = [
        (2, "No.", YELLOW, {"left": M, "right": T}),
        (3, "Description", YELLOW, {}),
        (4, "Brand", YELLOW, {}),
        (5, "Unit", YELLOW, {}),
        (6, "Quantity", GRAY_F, {}),
        (8, "Quantity", YELLOW, {}),
        (9, "Original Rate ", GRAY_F, {}),
        (11, "Material Mark up (%)", GRAY_F, {}),
        (12, "Labour Mark up (%)", GRAY_F, {}),
        (13, "Rate ", YELLOW, {}),
        (15, "Total ", YELLOW, {}),
        (17, "Amount", YELLOW, {}),
        (18, "Remark", YELLOW, {"right": M}),
        (21, "Budget", None, {}),
        (23, "Total", None, {}),
        (25, "Profit", None, {}),
        (27, "Total", None, {}),
    ]
    for col, text, fill, extra in header8:
        cell(8, col, text)
        gray = fill == GRAY_F
        yellow = fill == YELLOW
        bd = {"top": T if (not yellow and not gray) or col in (11, 12) else M,
              "bottom": T, "left": T, "right": T}
        bd.update(extra)
        _paint(ws, 8, col, bold=True,
               color=RED if gray else None,
               fill_theme=GRAY_F if gray else None,
               fill=YELLOW if yellow else None,
               hal="center", val="center", wrap=col == 17, **bd)
    # Continuation cells inside the horizontal header merges keep the band's
    # top/bottom edges (the reference stores these as Calibri 11).
    for col, top_style in ((7, M), (10, M), (14, M), (16, M), (22, T), (26, T)):
        _paint(ws, 8, col, calibri=True, top=top_style, bottom=T, right=T)

    # Row 9 sub-headers (unit / mark-up / rate split).
    def subhead(col, text, band=None, z=None, hal="center"):
        cobj = cell(9, col, text,
                    bold=True,
                    color=RED if band == GRAY_F else None,
                    fill_theme=GRAY_F if band == GRAY_F else None,
                    fill=YELLOW if band == YELLOW else None,
                    z=z,
                    top=T, bottom=T, left=T, right=T,
                    hal=hal, val="center")
        return cobj

    subhead(6, "Drawing", GRAY_F)
    subhead(7, "Mark up 10%", GRAY_F, PCT_FMT, None)
    subhead(9, "Material", GRAY_F)
    subhead(10, "Labour", GRAY_F)
    subhead(11, 0.3, GRAY_F, PCT_FMT)
    subhead(12, 0.3, GRAY_F, PCT_FMT)
    for col, text in ((13, "Material"), (14, "Labour"),
                      (15, "Material"), (16, "Labour")):
        subhead(col, text, YELLOW)
    for col, text in ((21, "Material"), (22, "Labour"),
                      (25, "Material"), (26, "Labour")):
        subhead(col, text)

    # Continuation cells below the vertical header merges close the band.
    _paint(ws, 9, 2, calibri=True, bottom=T, left=M, right=T)   # B9
    for col in (3, 4, 5, 8, 17):  # C9..E9,H9,Q9
        _paint(ws, 9, col, calibri=True, bottom=T, left=T, right=T)
    _paint(ws, 9, 18, calibri=True, bottom=T, left=T, right=M)  # R9
    _paint(ws, 9, 23, calibri=True, bottom=T, left=T, right=T)  # W9
    _paint(ws, 9, 27, calibri=True, bottom=T, left=T, right=T)  # AA9

    for rng in ["B8:B9", "C8:C9", "D8:D9", "E8:E9", "H8:H9", "Q8:Q9",
                "R8:R9", "W8:W9", "AA8:AA9", "F8:G8", "I8:J8", "M8:N8",
                "O8:P8", "U8:V8", "Y8:Z8"]:
        ws.merge_cells(rng)
    # Exact column widths from the reference (F and G start hidden, S and T are
    # the narrow spacer columns between the table and the budget block).
    for col, w in {"A": 0.86, "B": 5.71, "C": 50.71, "D": 9.14, "E": 9.14,
                   "F": 9.14, "G": 11.71, "H": 9.14, "I": 9.14, "J": 9.14,
                   "K": 19.71, "L": l_width, "M": 9.14, "N": 9.14, "O": 9.14,
                   "P": 9.14, "Q": 10.71, "R": 9.14, "S": 0.57, "T": 3.43,
                   "U": 9.14, "V": 9.14, "W": 9.14, "X": 9.14, "Y": 9.14,
                   "Z": 9.14, "AA": 9.14}.items():
        ws.column_dimensions[col].width = w
    ws.column_dimensions["F"].hidden = True
    ws.column_dimensions["G"].hidden = True
    # Header row heights straight from the reference template.
    for r, h in ((1, 15.75), (2, 15), (3, 15), (4, 15), (5, 15), (6, 15),
                 (7, 13.5), (8, 15), (9, 12.75)):
        ws.row_dimensions[r].height = h
    ws.sheet_format.defaultRowHeight = 14.25



def _build_bill_sheet(ws, name, sum_row, groups, state, item_count=0, location=""):
    """Sheet 1.1 holds the whole BOQ like the reference template: a stray blank
    band at row 10, then one numbered section per top-level group (each closed
    by an echo divider, its leaves, a plain divider and a SUB-TOTAL row), a
    GRAND TOTAL row, the closing band and the estimated profit block. Returns
    the GRAND TOTAL row number."""
    from openpyxl.styles import Font

    bold = Font(bold=True)
    money16 = [(17, "Q"), (21, "U"), (22, "V"), (23, "W"), (25, "Y"), (26, "Z"), (27, "AA")]

    def cell(r, c, v=None):
        return ws.cell(row=r, column=c, value=v)

    _write_bill_header(ws, name, sum_row, 21.43, item_count, location)

    r = 10  # the stray blank band, exactly like the reference sheet
    sec_no = 0
    first_top = 0
    sec_start = 0
    pending = []

    def new_row():
        nonlocal r
        r += 1
        return r

    def flush_subtotal():
        if not pending or sec_no == 0:
            return
        first, last = sec_start, pending[-1]
        row = new_row()
        cell(row, 3, "SUB-TOTAL {}".format(sec_no))
        for col, letter in money16:
            c = cell(row, col, "=SUBTOTAL(9,{0}{1}:{0}{2})".format(letter, first, last))
            c.number_format = ACCT_CUR
        _paint_body_row(ws, row, "subtotal", x_money=sec_no == 3)
        _set_h(ws, row, 16.5)
        pending[:] = []

    def write_leaf(node):
        row = new_row()
        cell(row, 3, node.get("name") or "")
        cell(row, 4, node.get("brand") or "")
        cell(row, 5, node.get("unit") or "")
        quantity = float(node.get("quantity") or 0)
        cell(row, 6, quantity)
        cell(row, 7, round(quantity * (1 + qty_markup_pct(node) / 100), 2))  # General
        h = cell(row, 8, "=ROUNDUP(G{0},2)".format(row))
        h.number_format = ACCT_NUM
        cell(row, 9, round(original_rate(state, node, "material"), 2))
        cell(row, 10, round(original_rate(state, node, "labor"), 2))
        km = cell(row, 11, _markup_decimal(node, "material"))
        km.number_format = PCT_FMT
        kl = cell(row, 12, _markup_decimal(node, "labor"))
        kl.number_format = PCT_FMT
        formulas = [(13, "=ROUNDUP(I{0}+I{0}*K{0},2)".format(row)),
                    (14, "=ROUNDUP(J{0}+J{0}*L{0},2)".format(row)),
                    (15, "=M{0}*H{0}".format(row)),
                    (16, "=N{0}*H{0}".format(row)),
                    (17, "=O{0}+P{0}".format(row)),
                    (21, "=I{0}*H{0}".format(row)),
                    (22, "=J{0}*H{0}".format(row)),
                    (23, "=V{0}+U{0}".format(row)),
                    (25, "=O{0}-U{0}".format(row)),
                    (26, "=P{0}-V{0}".format(row)),
                    (27, "=Z{0}+Y{0}".format(row))]
        for col, formula in formulas:
            c = cell(row, col, formula)
            if col in (13, 14, 15, 16, 17):
                c.number_format = ACCT_CUR
            else:
                c.number_format = ACCT_NUM
        if node.get("remark"):
            cell(row, 18, node.get("remark"))
        _paint_body_row(ws, row, "leaf")
        pending.append(row)

    def emit_node(node):
        if is_heading(node):
            row = new_row()
            cell(row, 3, node.get("name") or "")
            _paint_body_row(ws, row, "section")
            for child in node.get("children") or []:
                emit_node(child)
        else:
            write_leaf(node)

    # stray first band (the reference's blank row 10 - no U..AA cells)
    _paint_body_row(ws, 10, "section", skip_uaa=True, band_fmt=True)

    for group in groups:
        flush_subtotal()
        sec_no += 1
        s_row = new_row()
        if sec_no == 1:
            first_top = s_row
        cell(s_row, 2, sec_no)
        cell(s_row, 3, group["title"])
        _paint_body_row(ws, s_row, "section", band_fmt=sec_no == 1)
        sec_start = s_row
        pending[:] = []
        # bold echo divider right after the section band
        echo = new_row()
        _paint_body_row(ws, echo, "spacerB", band_fmt=sec_no == 1)
        _set_h(ws, echo, 5.25)
        nodes = group["nodes"]
        if len(nodes) == 1 and is_heading(nodes[0]):
            nodes = nodes[0].get("children") or []
        for node in nodes:
            emit_node(node)
        # plain divider closes the leaf block before the sub-total
        div = new_row()
        _paint_body_row(ws, div, "spacer")
        _set_h(ws, div, 5.25)
    flush_subtotal()
    if not first_top:
        first_top = 11

    # plain divider before GRAND TOTAL (reference row 36)
    pre_g = new_row()
    _paint_body_row(ws, pre_g, "spacer")
    _set_h(ws, pre_g, 6.0)
    gt = new_row()
    cell(gt, 3, "GRAND TOTAL")
    for col, letter in money16:
        c = cell(gt, col, "=SUBTOTAL(9,{0}{1}:{0}{2})".format(letter, first_top, gt - 1))
        c.number_format = ACCT_CUR
    _paint_body_row(ws, gt, "grand")
    _set_h(ws, gt, 16.5)
    _paint_body_row(ws, gt + 1, "bottom")   # empty row that closes the table
    _set_h(ws, gt + 1, 15)

    for rr in (gt + 2, gt + 5):
        _paint_gray_row(ws, rr)
        _set_h(ws, rr, 14.25)
    p_label = gt + 3
    p_amt = gt + 4
    p_pct = gt + 6
    cell(p_label, 21, "ESTIMATED PROFIT :")
    cell(p_amt, 23, "=Q{0}-W{0}".format(gt)).number_format = ACCT_CUR
    cell(p_pct, 21, "ESTIMATED PROFIT (%) :")
    cell(p_pct + 1, 23, "=W{0}/Q{1}".format(p_amt, gt)).number_format = PCT_FMT
    cell(p_pct + 1, 24, "Project")
    cell(p_pct + 2, 23, "=W{0}/W{1}".format(p_amt, gt))  # General, like the reference
    cell(p_pct + 2, 24, "Budget")
    _paint(ws, p_label, 21, sz=11, bold=True)
    _paint(ws, p_amt, 23, sz=11, bold=True, color=RED)
    _paint(ws, p_pct, 21, sz=11, bold=True)
    _paint(ws, p_pct + 1, 23, sz=11, bold=True, color=RED)
    _paint(ws, p_pct + 1, 24, sz=11)
    _paint(ws, p_pct + 2, 23, sz=11, bold=True, color=RED)
    _paint(ws, p_pct + 2, 24, sz=11)
    for rr in (p_label, p_amt, p_pct, p_pct + 1, p_pct + 2):
        _paint_gray_row(ws, rr)
        _set_h(ws, rr, 15)
    return gt



def _build_empty_bill_sheet(ws, name, sum_row, l_width, item_count=0, location="",
                            grand_colored=False):
    """Blank template copy for sheets 1.2-1.4, keeping the workbook's sheet set
    identical to the reference template: a stray blank band, four named
    placeholder sections and the GRAND TOTAL at row 37, styled exactly like a
    real sheet but with no live math (like the reference file itself)."""
    def cell(r, c, v=None):
        return ws.cell(row=r, column=c, value=v)

    _write_bill_header(ws, name, sum_row, l_width, item_count, location)

    skeleton = [(10, "section", None), (11, "section", ("1", "PRELIMINARY WORK")),
                (12, "spacerB", None), (13, "leaf", None), (14, "leaf", None),
                (15, "spacer", None), (16, "subtotal", "SUB-TOTAL 1"),
                (17, "section", ("2", "FOUNDATION AND EARTH WORK")),
                (18, "spacerB", None), (19, "leaf", None), (20, "leaf", None),
                (21, "leaf", None), (22, "spacer", None), (23, "subtotal", "SUB-TOTAL 2"),
                (24, "section", ("3", "STRUCTURAL WORK")),
                (25, "spacerB", None), (26, "leaf", None), (27, "leaf", None),
                (28, "spacer", None), (29, "subtotal", "SUB-TOTAL 3"),
                (30, "section", ("4", "ARCHITECTURAL WORK")),
                (31, "spacerB", None), (32, "leaf", None), (33, "leaf", None),
                (34, "spacer", None), (35, "subtotal", "SUB-TOTAL 4"),
                (36, "spacer", None)]
    spacer_h = {12: 5.25, 15: 5.25, 18: 3.0, 22: 4.5, 25: 4.5, 28: 6.75,
                31: 4.5, 34: 3.75, 36: 6.0}
    sub_no = 0
    for row, kind, txt in skeleton:
        if kind == "subtotal":
            sub_no += 1
        _paint_body_row(ws, row, kind, band_fmt=row <= 12,
                        x_money=kind == "subtotal" and sub_no == 3)
        if kind in ("spacer", "spacerB"):
            _set_h(ws, row, spacer_h[row])
        elif kind == "subtotal":
            _set_h(ws, row, 16.5)
        if txt:
            if kind == "section":
                cell(row, 2, txt[0])
                cell(row, 3, txt[1])
            else:
                cell(row, 3, txt)

    gt = 37
    cell(gt, 3, "GRAND TOTAL")
    _paint_body_row(ws, gt, "grand",
                    money_colors={21: "FFFFC000", 22: "FFFFC000", 23: "FFFFC000",
                                  25: "FFFF0000", 26: "FFFF0000", 27: "FFFF0000"}
                    if grand_colored else None)
    _set_h(ws, gt, 16.5)
    _paint_body_row(ws, gt + 1, "bottom")
    _set_h(ws, gt + 1, 15)

    for rr in (gt + 2, gt + 5):
        _paint_gray_row(ws, rr)
        _set_h(ws, rr, 14.25)
    cell(gt + 3, 21, "ESTIMATED PROFIT :")
    cell(gt + 6, 21, "ESTIMATED PROFIT (%) :")
    _paint(ws, gt + 3, 21, sz=11, bold=True)
    _paint_gray_row(ws, gt + 3)
    _paint_gray_row(ws, gt + 4)
    _paint(ws, gt + 4, 23, sz=11, bold=True, color=RED, z=ACCT_CUR)  # styled empty
    _paint(ws, gt + 6, 21, sz=11, bold=True)
    _paint_gray_row(ws, gt + 6)
    _paint_gray_row(ws, gt + 7)
    _paint(ws, gt + 7, 23, sz=11, bold=True, color=RED, z=PCT_FMT)   # styled empty
    cell(gt + 7, 24, "Project")
    _paint(ws, gt + 7, 24, sz=11)
    _paint(ws, gt + 8, 23, sz=11, bold=True, color=RED)              # styled empty
    _paint_gray_row(ws, gt + 8)
    cell(gt + 8, 24, "Budget")
    _paint(ws, gt + 8, 24, sz=11)
    for rr in (gt + 3, gt + 4, gt + 6, gt + 7, gt + 8):
        _set_h(ws, rr, 15)



def _build_sum_sheet(ws, name, bill_sheets, item_count=0, location=""):
    """QUOTATION sheet, laid out on the exact rows of the reference template:
    four Bill rows at 17/19/21/23, SUB-TOTAL 28, DISCOUNT 29, VAT 30, GRAND
    TOTAL 31, notes at 34-39 and signatures at 46. Bill 1 links to sheet 1.1's
    GRAND TOTAL; bills 2-4 link to the blank templates' row 37 (zero). Returns
    the SUM GRAND TOTAL row (31) for the cover."""
    from openpyxl.styles import Font

    bold = Font(bold=True)

    def cell(r, c, v=None, **kw):
        cobj = ws.cell(row=r, column=c, value=v)
        _paint(ws, r, c, **kw)
        return cobj

    cell(2, 2, "QUOTATION", sz=12, bold=True, hal="center",
         top=M, bottom=M, left=M, right=T)
    ws.merge_cells("B2:H2")
    # the merged title cells keep their band edges so the block draws as one
    for c in range(3, 9):
        _paint(ws, 2, c, calibri=True, top=M, bottom=M, right=T if c == 8 else None)
    _paint(ws, 2, 9, sz=12)  # I2 styled empty (Arial 12)
    cell(3, 2, "Project :")
    cell(3, 3, name, bold=True)
    cell(4, 2, "Items :")
    cell(4, 3, item_count, bold=True)
    cell(5, 2, "Location :")
    cell(5, 3, location, bold=True)
    cell(6, 2, "Date :")
    cell(6, 3, datetime.now().strftime("%d/%m/%Y"), bold=True)
    cell(8, 2, "From :")
    cell(9, 2, "H/P :")
    cell(11, 2, "Attend to :")
    cell(12, 2, "H/P :")
    cell(14, 2, "Quote Ref :")
    for col, text in [(2, "Items"), (3, "Description"), (4, "Unit"),
                      (5, "Quantity"), (6, "Unit Price"), (7, "Amount"),
                      (8, "Remark")]:
        cell(15, col, text,
             bold=True, fill=YELLOW,
             top=M, bottom=T,
             left=M if col == 2 else T,
             right=M if col == 8 else T,
             hal="center")

    # r16 painted band under the header (no F16, exactly like the reference)
    _paint(ws, 16, 2, left=M, right=T)
    for c in (3, 4, 5):
        _paint(ws, 16, c, left=T, right=T)
    _paint(ws, 16, 7, left=T, right=T)
    _paint(ws, 16, 8, left=T, right=M)
    _set_h(ws, 16, 15)

    for index, bill in enumerate(bill_sheets, start=1):
        row = 17 + 2 * (index - 1)  # Bill No. 1 on SUM row 17, like the reference
        cell(row, 2, "Bill No. {}".format(index), bold=True, left=M, right=T)
        cell(row, 3, bill["title"], bold=True, left=T, right=T)
        cell(row, 4, "LOT", left=T, right=T, hal="center")
        cell(row, 5, 1, left=T, right=T, hal="center")
        fcell = cell(row, 6, "='{0}'!Q{1}".format(bill["sheet"], bill["gt"]),
                     left=T, right=T,
                     hal=None if index == 1 else "center")
        fcell.number_format = ACCT_CUR
        gcell = cell(row, 7, "=F{0}*E{0}".format(row),
                     left=T, right=T, hal="center")
        gcell.number_format = ACCT_CUR
        _paint(ws, row, 8, left=T, right=M, hal="center")
        _set_h(ws, row, 15)

    # quiet grid rows around the bill rows keep the frame continuous
    for r in (18, 20, 22):
        _paint(ws, r, 2, bold=True, left=M, right=T)
        _paint(ws, r, 3, bold=True, left=T, right=T)
        for c in (4, 5, 6):
            _paint(ws, r, c, left=T, right=T, hal="center")
        _paint(ws, r, 7, left=T, right=T, hal="center", z=ACCT_CUR)
        _paint(ws, r, 8, left=T, right=M, hal="center")
        _set_h(ws, r, 15)
    # r24 full-bold closing band (no alignment, G without a format)
    _paint(ws, 24, 2, bold=True, left=M, right=T)
    for c in range(3, 9):
        _paint(ws, 24, c, bold=True, left=T, right=M if c == 8 else T)
    _set_h(ws, 24, 15)
    # r25-27 plain spacer rows
    for r in (25, 26, 27):
        _paint(ws, r, 2, left=M, right=T)
        for c in range(3, 9):
            _paint(ws, r, c, left=T, right=M if c == 8 else T)
        _set_h(ws, r, 15)

    cell(28, 6, "SUB-TOTAL (EXCLUDE VAT)", bold=True, top=T, hal="right")
    cell(28, 7, "=SUM(G16:G27)", bold=True, top=T, left=T, right=T,
         z=ACCT_CUR)
    _paint(ws, 28, 2, top=T, left=M)
    for c in (3, 4, 5):
        _paint(ws, 28, c, top=T)
    _paint(ws, 28, 8, top=T, right=M)

    cell(29, 6, "DISCOUNT", bold=True, hal="right")
    _paint(ws, 29, 7, bold=True, left=T, right=T, z=ACCT_CUR)  # styled empty
    _paint(ws, 29, 2, left=M)
    _paint(ws, 29, 8, right=M)
    cell(30, 6, "VAT", bold=True, hal="right")
    cell(30, 7, "=G28*0.1", bold=True, left=T, right=T, z=ACCT_CUR)
    _paint(ws, 30, 2, left=M)
    _paint(ws, 30, 8, right=M)
    cell(31, 6, "GRAND TOTAL", bold=True, hal="right")
    cell(31, 7, "=G30+G28", bold=True, left=T, right=T, z=ACCT_CUR)
    _paint(ws, 31, 2, left=M)
    _paint(ws, 31, 8, right=M)
    # closing row 32
    _paint(ws, 32, 2, bottom=M, left=M)
    for c in (3, 4, 5, 6):
        _paint(ws, 32, c, bottom=M)
    _paint(ws, 32, 7, bottom=M, left=T, right=T)
    _paint(ws, 32, 8, bottom=M, right=M)
    _set_h(ws, 32, 13.5)

    cell(34, 2, "Note :", bold=True, underline=True)
    for i in range(1, 6):
        cell(34 + i, 2, i, hal="left")
    for c in range(2, 8):
        _paint(ws, 45, c, bold=True)  # styled empty
    cell(46, 2, "Prepared by :", bold=True)
    _paint(ws, 46, 3, bold=True)      # styled empty
    cell(46, 4, "Checked by :", bold=True)
    _paint(ws, 46, 5, bold=True)      # styled empty
    _paint(ws, 46, 6, bold=True)      # styled empty
    _paint(ws, 46, 7, bold=True, hal="left")   # styled empty
    cell(46, 8, "Accepted by :", bold=True, hal="left")
    for r in (47, 48, 49, 50, 51):
        _paint(ws, r, 7, hal="left")
        _paint(ws, r, 8, hal="left")
    spaces = " " * 34
    cell(52, 2, spaces, underline=True)
    cell(52, 4, spaces, underline=True)
    _paint(ws, 52, 7, hal="left", underline=True)     # styled empty
    cell(52, 8, spaces, hal="left", underline=True)

    for col, w in {"A": 1.71, "B": 10.14, "C": 30.71, "D": 4.57, "E": 8.57,
                   "F": 10.0, "G": 10.0, "H": 21.0, "I": 9.14}.items():
        ws.column_dimensions[col].width = w
    # the reference stores r1 = 13.5, but the client writer cannot emit an empty
    # row 1, so it is kept at the sheet default for parity between the two.
    for r, h in ((2, 16.5), (7, 7.5), (10, 6.75), (13, 6.0), (14, 13.5),
                 (16, 15.0), (17, 15.0), (18, 15.0), (19, 15.0), (20, 15.0),
                 (21, 15.0), (22, 15.0), (23, 15.0), (24, 15.0), (25, 15.0),
                 (26, 15.0), (27, 15.0), (32, 13.5)):
        ws.row_dimensions[r].height = h
    ws.sheet_format.defaultRowHeight = 12.75
    return 31



def _build_cover_sheet(ws, name, grand_row, grand_value=0, item_count=0, location=""):
    def cell(r, c, v=None, **kw):
        cobj = ws.cell(row=r, column=c, value=v)
        _paint(ws, r, c, **kw)
        return cobj

    # thin/medium black frame around the whole page, exactly like the reference
    for r in range(1, 48):
        _paint(ws, r, 1,
               top=M if r == 1 else None,
               bottom=M if r == 47 else None,
               left=M)
        _paint(ws, r, 10,
               top=M if r == 1 else None,
               bottom=M if r == 47 else None,
               right=M)
    for c in range(2, 10):
        _paint(ws, 1, c, top=M)
        _paint(ws, 47, c, bottom=M)

    cell(2, 9, "Quote Ref:", bold=True, hal="right")
    cell(3, 9, "Date :", bold=True, hal="right")
    # r6 blank Arial-14 bold band
    for c in range(1, 11):
        _paint(ws, 6, c, sz=14, bold=True,
               left=M if c == 1 else None, right=M if c == 10 else None)
    # the black address band: Times New Roman 12 on a theme-0 black fill, with
    # default (black) text - exactly the reference's black-on-black band
    addr = ["Lot 93, St.598, Phum Toul Kork, Sangkat Toul Sangke",
            "Khan Russey Keo, PNP, Kingdom of Cambodia",
            "Phone/Fax: +855 23 210 894"]
    for r, text in zip(range(7, 10), addr):
        cell(r, 1, text, font=TNR, sz=12, fill_theme=BLACK_F, left=M,
             hal="left" if r == 9 else None)
        _paint(ws, r, 2, font=TNR, sz=14)  # styled empty B column
    _paint(ws, 8, 3, sz=14)   # C8/C9/C10 styled empty (Arial 14)
    _paint(ws, 9, 3, sz=14)
    _paint(ws, 10, 3, sz=14)
    cell(11, 1, "QUOTATION", sz=18, bold=True, underline=True, color=RED,
         hal="center", left=M, right=M)
    ws.merge_cells("A11:J11")
    # the reference merges A11:J11 and leaves B..I unstyled (Calibri default)
    _paint(ws, 11, 10, calibri=True, right=M)
    # r13 blank Arial-18 bold band
    for c in range(1, 11):
        _paint(ws, 13, c, sz=18, bold=True,
               left=M if c == 1 else None, right=M if c == 10 else None)
    # r15-24 the 14pt bold right block
    for r in range(15, 25):
        _paint(ws, r, 2, sz=14, bold=True, hal="right")
        _paint(ws, r, 3, sz=14, bold=True, hal="right")
    cell(15, 3, "Project :", sz=14, bold=True, hal="right")
    cell(16, 2, name, sz=14, bold=True, hal="right")
    cell(17, 3, "Items :", sz=14, bold=True, hal="right")
    cell(18, 2, item_count, sz=14, bold=True, hal="right")
    cell(19, 3, "Location :", sz=14, bold=True, hal="right")
    cell(20, 2, location, sz=14, bold=True, hal="right")
    # r26 plain 14pt (non-bold) row
    _paint(ws, 26, 2, sz=14)
    _paint(ws, 26, 3, sz=14)
    cell(27, 1, "GRAND TOTAL", sz=18, bold=True, underline=True, color=RED,
         hal="center", left=M, right=M)
    ws.merge_cells("A27:J27")
    _paint(ws, 27, 10, calibri=True, right=M)
    # r28 carries the computed total (the reference leaves it blank); every
    # A28..J28 cell carries the money format
    cell(28, 1, grand_value, sz=18, bold=True, left=M, z=COVER_CUR)
    for c in range(2, 10):
        _paint(ws, 28, c, sz=18, bold=True, z=COVER_CUR)
    _paint(ws, 28, 10, sz=18, bold=True, right=M, z=COVER_CUR)
    cell(30, 1, "=SUM!G{}".format(grand_row), sz=18, bold=True, color=RED,
         hal="center", left=M, right=M, z=COVER_CUR)
    ws.merge_cells("A30:J30")
    _paint(ws, 30, 10, calibri=True, right=M)
    for col, w in {"A": 9.14, "J": 12.86, "K": 1.855469, "L": 9.14}.items():
        ws.column_dimensions[col].width = w
    for r, h in ((6, 18.0), (7, 18.75), (8, 20.1), (9, 20.1), (10, 20.1),
                 (11, 23.25), (13, 23.25), (15, 20.1), (16, 20.1), (17, 20.1),
                 (18, 20.1), (19, 20.1), (20, 22.5), (21, 22.5), (22, 22.5),
                 (23, 20.1), (24, 20.1), (26, 20.1), (27, 20.1), (28, 20.1),
                 (29, 20.1), (30, 20.1), (31, 20.1), (32, 20.1), (33, 20.1),
                 (47, 13.5)):
        ws.row_dimensions[r].height = h
    ws.sheet_format.defaultRowHeight = 12.75



def build_excel(state, project):
    """Build the .xlsx download: COVER, SUM, sheet 1.1 holding the whole BOQ
    (same quotation layout as the reference workbook) and blank template copies
    1.2-1.4 so the sheet set matches the reference file exactly."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    name = (project.get("name") if project else "") or ""
    boq = (project.get("boq") if project else []) or []
    groups = _collect_bills(boq)

    def count_items(nodes):
        n = 0
        for row in nodes:
            if is_heading(row):
                n += count_items(row.get("children") or [])
            else:
                n += 1
        return n

    item_count = count_items(boq)
    location = (project.get("location") if project else None) or ""

    cover = wb.create_sheet("COVER")
    summary = wb.create_sheet("SUM")

    main = wb.create_sheet("1.1")
    main_gt = _build_bill_sheet(main, name, 17, groups, state, item_count, location)

    bill_sheets = [
        {"sheet": "1.1", "gt": main_gt,
         "title": groups[0]["title"] if groups else ""},
    ]
    l_width = {2: 19.29, 3: 18.71, 4: 18.71}  # reference L width varies per blank sheet
    for index in range(2, 5):
        ws = wb.create_sheet("1.{}".format(index))
        _build_empty_bill_sheet(ws, name, 17 + 2 * (index - 1), l_width[index],
                                item_count, location, grand_colored=index == 4)
        bill_sheets.append({
            "sheet": "1.{}".format(index), "gt": 37,
            "title": groups[index - 1]["title"] if index - 1 < len(groups) else "",
        })

    grand = _build_sum_sheet(summary, name, bill_sheets, item_count, location)

    # cover value = the 1.1 GRAND TOTAL x 1.1 (VAT): the same figure the SUM
    # formula chain computes once Excel evaluates the formulas.
    def leaves(nodes):
        out = []
        for row in nodes:
            if is_heading(row):
                out.extend(leaves(row.get("children") or []))
            else:
                out.append(row)
        return out

    main_total = sum(own_amount(state, leaf) for leaf in leaves(boq))
    _build_cover_sheet(cover, name, grand, grand_value=round(main_total * 1.1, 2),
                       item_count=item_count, location=location)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


@app.route("/api/export.xlsx")
@login_required
def export_excel():
    try:
        import openpyxl  # noqa: F401  (lazy: the rest of the app runs without it)
    except Exception:
        return jsonify({"error": "Excel export needs openpyxl. "
                                 "Run: pip install openpyxl"}), 500
    state = read_state()
    projects = state.get("projects") or []
    wanted = request.args.get("project") or state.get("activeProjectId")
    project = next((p for p in projects if p.get("id") == wanted), None) \
        or (projects[0] if projects else None)
    filename = ((project.get("name") if project else "") or "bill-of-quantities").strip() \
        or "bill-of-quantities"
    filename = "".join(c for c in filename if c.isalnum() or c in "-_ ").replace(" ", "-") \
        or "bill-of-quantities"
    try:
        data = build_excel(state, project)
    except Exception as exc:
        return jsonify({"error": "Excel export failed: {}".format(exc)}), 500
    return Response(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 "attachment; filename={}.xlsx".format(filename)},
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