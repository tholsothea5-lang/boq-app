# Site Ledger — Bill of Quantities (GitHub Pages + Supabase)

This is the **accounts edition** of the Site Ledger BOQ web tool, still
published at the GitHub Pages address.

GitHub Pages itself can only serve static files, so the login system, the
shared ledger and the audit log run on a free **Supabase** backend that the
static page talks to:

- **Accounts** — everyone signs in with an email + password. The **first
  account created on an empty project is the admin**.
- **Shared ledger** — every signed-in user edits the same ledger (materials,
  labor rates, projects, bills). No more "saved in this browser only".
- **Audit trail** — every save records who changed which row and how (e.g.
  `Added material 'Sand (river)' to Build materials/Aggregates`), plus sign-ins
  and user-management actions. Only admins can read it.
- **Admin** — the admin gets an Admin tab: promote/demote/disable/delete users,
  search the audit trail, reset the ledger to the bundled baseline.
- **Export CSV** still works entirely in the browser.
- Photos: the existing ones ship as files under `photos/`; new uploads are
  downscaled automatically and stored with the ledger.

## One-time setup (free)

Follow **SETUP.md** (in this folder): create a free supabase.com project, run
`supabase.sql` once in its SQL editor, and paste the Project URL + anon key into
`index.html` (the placeholders near the top of the script are marked
`YOUR_SUPABASE_URL` / `YOUR_SUPABASE_ANON_KEY`).

## Files

| File | What it is |
| --- | --- |
| `index.html` | The tool itself (UI, calculations, Supabase integration) |
| `data.json` | The bundled baseline ledger (source: `boq_app/data/boq_data.json`) |
| `photos/` | Material photos (source: `boq_app/data/photos/`) |
| `supabase.sql` | One-time database setup (run in Supabase SQL Editor) |
| `SETUP.md` | Step-by-step account/backend setup guide |
| `.nojekyll` | Tells GitHub Pages not to run Jekyll on the site |

## Updating the baseline data

The bundled baseline serves only as the starting point for a fresh database
(the current live edits live in Supabase, not here). To refresh the baseline:

```bash
# from this folder's parent (the boq_app directory)
python - <<'PY'
import json, re
src = "data/boq_data.json"
raw = open(src, encoding="utf-8").read()
open("gh-pages/data.json", "w", encoding="utf-8").write(
    re.sub(r'"/api/photo/([A-Za-z0-9_.-]+)"', '"photos/\\1"', raw))
PY
# refresh photos (or just copy new ones)
cp -r data/photos/* gh-pages/photos/
# then commit and push:
git -C gh-pages add -A
git -C gh-pages commit -m "Refresh baseline"
git -C gh-pages push
```

**Note:** refreshing `data.json` changes the baseline for future fresh Supabase
databases only; anyone who already opened the site keeps the shared ledger in
Supabase. The admin can reset the live ledger to the new baseline from the
Admin panel.