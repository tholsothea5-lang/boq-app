# Site Ledger — Bill of Quantities (GitHub Pages build)

This is the **static build** of the Site Ledger BOQ web tool, published on
GitHub Pages. It works exactly like the local version except there is no
server:

- The whole ledger (materials, labor rates, projects and each project's bill)
  ships as `data.json`.
- Material photos ship as plain files under `photos/`.
- Edits you make are saved in **your browser only** (local storage), not on a
  server, so every visitor starts from the bundled ledger and keeps their own
  copy. Use **Reset saved copy** (next to Export CSV) to discard your local
  edits and go back to the bundled data.
- **Export CSV** generates the spreadsheet entirely in the browser.

## Files

| File | What it is |
| --- | --- |
| `index.html` | The tool itself (all UI and calculations) |
| `data.json` | The bundled ledger (source: `boq_app/data/boq_data.json`) |
| `photos/` | Material photos (source: `boq_app/data/photos/`) |
| `.nojekyll` | Tells GitHub Pages not to run Jekyll on the site |

## Updating the site after editing the real data

The live editable version runs from `boq_app/` (Flask). When that data
changes and you want to refresh this static site:

```bash
# from this folder's parent (the boq_app directory)
python - <<'PY'
import json, re, shutil, os
src = "data/boq_data.json"
raw = open(src, encoding="utf-8").read()
open("gh-pages/data.json", "w", encoding="utf-8").write(
    re.sub(r'"/api/photo/([A-Za-z0-9_.-]+)"', '"photos/\\1"', raw))
PY
# refresh photos (or just copy new ones)
cp -r data/photos/* gh-pages/photos/
# then commit and push:
git -C gh-pages add -A
git -C gh-pages commit -m "Refresh ledger"
git -C gh-pages push
```