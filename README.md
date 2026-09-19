# Site Ledger — Bill of Quantities (accounts edition)

A Flask web tool for keeping material rates, labor rates and bill-of-quantities
lines. Data is stored server-side in `data/boq_data.json` and **shared by every
signed-in user**.

This edition adds:

- **Accounts** — email + password sign in. The **first account created on an
  empty server is the admin**. New accounts are plain `user`s (or ask the admin
  to promote you).
- **Admin role** — the admin can do anything:
  - edit the ledger just like everyone else,
  - promote / demote / disable / delete other users,
  - browse the full audit trail,
  - reset the ledger to defaults (recorded in the audit log).
- **Audit trail** — every meaningful action is recorded with who, when, and a
  summary: sign in/out, account creation, every data save (what rows were
  added / removed / renamed / changed, with their paths), photo uploads, and
  user management.

## Run it locally

```
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 — you will be asked to **create the admin
account** (this is the very first account, so it is granted the admin role).

## How it stores things

| Thing             | Where                                     |
| ----------------- | ----------------------------------------- |
| Ledger (shared)   | `data/boq_data.json` (still human-editable) |
| Accounts, roles   | `data/ledger.db` (SQLite, `users` table)   |
| Audit log         | `data/ledger.db` (SQLite, `audit` table)   |
| Photos            | `data/photos/`                             |
| Session secret    | `data/secret_key.txt` (generated once)     |

Nothing sensitive is ever stored in plain text: passwords are salted hashes
(`werkzeug.security`), only inside `ledger.db`.

## API summary

- `POST /login`, `POST /register`, `POST /logout`, `GET /api/me`
- `GET|POST /api/data` — read / save the ledger (signed in only)
- `GET /api/export.csv` — spreadsheet export (signed in only)
- `GET|POST /api/photo/<name>` — material photos (signed in only)
- `GET /api/admin/users` · `PATCH|DELETE /api/admin/users/<id>` — manage users (admin only)
- `GET /api/admin/audit` — audit trail (admin only)
- `POST /api/admin/reset` — reset the ledger (admin only)

## Deploying

Free options that run Flask + SQLite cleanly:

- **Render** (free web service) — deploy from this GitHub repo. `Procfile`
  (included) starts gunicorn on `$PORT`.
- **Railway** — same, `Procfile` is honored.
- **PythonAnywhere** — upload the folder and run `app.py` as a WSGI app.

On Render/Railway the SQLite file lives on the service's disk; it is kept
between restarts but is not guaranteed to survive a fresh redeploy. For a real
team installation, attach a disk/volume or switch the store to Postgres — the
local SQLite setup keeps things simple for a small crew.