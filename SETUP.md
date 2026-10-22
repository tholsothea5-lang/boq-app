# Putting accounts on the GitHub Pages site — setup guide (10 minutes)

GitHub Pages can only serve static files, so the login accounts, the shared
editable ledger and the audit log live in a free **Supabase** project. The site
stays at its normal github.io address; Supabase runs in the background.

You'll do this once. I've filled in all the code — you only create the free
project and paste two keys.

## 1. Create the free Supabase project

1. Go to **https://supabase.com** and click **Start your project** (sign in
   with Google/GitHub/email — free plan, no card required).
2. **New project**:
   - Organization: anything (e.g. your name).
   - **Project name**: `site-ledger`
   - **Database password**: click **Generate a password** and save it somewhere
     safe (you won't need it for this setup, but keep it).
   - **Region**: pick the closest one (e.g. Singapore).
   - Click **Create new project**. It takes a minute or two.

## 2. Run the one-time database setup

1. In your project, open **SQL Editor** (left sidebar) → **New query**.
2. Open the file `supabase.sql` from this folder, select everything, paste it
   into the editor, and click **Run**.
3. You should see a small results table listing `profiles`, `ledger`, `audit`.

> **Already ran this script before?** Just run it again — it is written to be
> re-run safely, and the latest copy adds the **Moderator** role (three titles:
> Admin, Moderator, User), the online presence box, and (build 2026-09-20d)
> removes the per-writer lock on the shared ledger so every account can save.
> If two accounts could not see each other's new projects, re-running this
> whole file is the required step.

## 3. Point confirmation emails at the real site

When Supabase sends a "confirm your email" link it is built from the project's
**Site URL** setting. If that is left at `localhost:...`, the link in the email
goes nowhere useful. Set it to the real address:

1. Left sidebar → **Authentication → URL Configuration**.
2. **Site URL** = `https://tholsothea5-lang.github.io/boq-app`
3. **Redirect URLs** — add https://tholsothea5-lang.github.io/boq-app/**
   (keep any `http://localhost:...` entries if you also test locally).
4. Save. An already-sent email keeps its old link; you can either open it and
   swap just the host part to `https://tholsothea5-lang.github.io/boq-app`
   (keep everything from `/#/auth/confirm?` onward), or sign up again with the
   same address to get a fresh email with the correct link.

## 4. (Optional but recommended) Let people sign in instantly

By default Supabase requires email confirmation, which adds a click for new
users. To turn it off: **Authentication → Providers → Email → "Confirm email" =
off → Save**.

## 5. Copy the two keys

1. Left sidebar → **Project Settings → API**.
2. Copy **Project URL** (looks like `https://xxxx.supabase.co`).
3. Copy the **anon public** key (a long `eyJ...` string). This key is _meant_
   to be public — it only lets the site talk to your database through the rules
   in step 2.
4. Paste both to me (or, if you edit `index.html` yourself, replace the two
   placeholders near the top of the script marked `YOUR_SUPABASE_URL` and
   `YOUR_SUPABASE_ANON_KEY`).

Once the keys are in place I'll push the finished version to GitHub Pages. 

## 6. After it's live — your admin account

Open the site. The layout is the same one you hand builders/team members, but
now it starts with a **sign-in screen**:

- Create the very first account → it automatically becomes the **admin**.
- Everyone else can create their own account too, but as a plain user.
- Each account has a title — **Admin**, **Moderator** or **User** — shown in
  the bottom-left corner and in the **Online** box in the left rail. The box
  lists every account with a **green dot** when that person is online, and each
  person's title next to their name.
- Sign in as admin → you'll see an **Admin** tab on the left. There you can:
  - promote / demote / disable / delete users (roles: Admin, Moderator, User),
  - read the full audit trail (every save: who changed which row and how, with
    a search box),
  - reset the ledger to the original bundled baseline.
- Moderators can open the Admin tab too, but read-only: they see the user list
  and the audit trail without the manage/reset buttons.

## How data is stored now

| Thing       | Where                                                          |
| ----------- | ------------------------------------------------------------- |
| Ledger      | Supabase table `ledger` (one shared row, JSON)                |
| Accounts    | Supabase authentication + `profiles` table                    |
| Audit log   | Supabase table `audit` (admins and moderators can read it)        |
| Online box  | Supabase Realtime presence — who is online + their role title     |
| Baseline    | `data.json` — the starting point for an empty database        |
| Photos      | `photos/` folder (existing ones) + new photos saved with rows |

**Note:** this replaces the old "saved in this browser only" behaviour — edits
now go to the shared ledger, so everyone with an account sees the same numbers.
That is exactly what an audit log depends on.

## Build of Quantity columns (build 2026-09-26a)

The BOQ table mirrors your `Blank BOQ.xlsx` detail sheets (1.1–1.4). Per row:

- **Brand**, **Quantity (Drawing)**, **Quantity Mark-up %** (like the sheet's
  "Mark up 10%"), **Charged Quantity** (rounded up).
- **Original Rate — Material / Labour** (base unit rates), **Mark-up % —
  Material / Labour** (the sheets default to 30%), and computed **Rate —
  Material / Labour** (`ROUNDUP(Original × (1 + mark-up %))`).
- Computed **Total — Material / Labour** and **Amount**, plus **Budget**
  (original × charged qty) and **Profit** (Amount − Budget). Totals appear in
  the summary strip, the table footer, the CSV export and the Excel export.

**Export Excel** (next to Export CSV) downloads a real workbook that mirrors
`Blank BOQ.xlsx`: a **COVER** page, the **SUM** quotation (Bill No. 1–N rows
linked to each sheet's grand total, SUB-TOTAL, DISCOUNT, VAT 10% and GRAND
TOTAL) and one detail sheet per top-level BOQ section (`1.1`, `1.2`, …) with
the same two-row grouped header, `ROUNDUP` mark-up formulas, SUB-TOTAL /
GRAND TOTAL rows and the ESTIMATED PROFIT block. On the hosted site it is
built in the browser (the SheetJS library is loaded from a CDN); in the local
Flask app it is generated server-side (`/api/export.xlsx`).

The old **Material Price / Labour Price** columns stay — a row that has no
Original Rate is priced exactly as before, so existing bills are unaffected.
Rows with an Original Rate get the Excel mark-up treatment automatically.

## Go to top button (build 2026-09-27a)

The lists run to hundreds of rows, so scrolling far down leaves the panel
title and the search box off screen. A circular **Go to top** button fades in
at the bottom-right of the window once the page is scrolled more than 320px
down, and fades out again on the way back. Clicking it scrolls smoothly to the
top and hands keyboard focus to `<main>`, so the next Tab lands back inside the
content instead of at the foot of the document.

It is deliberately placed clear of the other floating pieces: bottom-right
rather than bottom-centre (the toast) and right rather than left-middle (the
show-left-panel button). Sign-in and photo overlays are stacked above it, and
it shrinks and moves in on narrow screens. `prefers-reduced-motion` turns both
the fade and the smooth scroll off.

Switching tab or ledger section also returns you to the top, since a tab change
always means new content further up the page.

## Search speed (build 2026-09-27b)

Typing in the Materials, Labor, Lump Sum Work or Build of Quantity search box
used to rebuild the whole matching list on every keystroke. Because a match
keeps its parent headings, a broad letter dragged in most of the ledger: `c`
matched 844 of the 1,061 material rows, and each rebuild built around 19,000
elements, bound 8,000 listeners and mutated the live table 900 times. That is
what made the box feel stuck.

Four things changed. None of them change what a search finds.

| | before | after |
| --- | --- | --- |
| type `concrete` in Materials | 77ms of blocking work | 4ms |
| type `plaster` in Materials | 38ms | 1ms |
| one keystroke on `c` | 48ms, 19,036 elements | 15ms, 7,594 elements |
| live table mutations per rebuild | up to 11,836 | 14–15, whatever the result |

- **Debounce** (`SEARCH_DEBOUNCE_MS = 160`). A burst of keys costs one rebuild
  instead of one per key. Enter, blur and `change` flush immediately, so the
  list is never left showing a filter you have already typed past. While a
  rebuild is queued the result count is greyed, so the number under the box is
  never silently out of date.
- **One swap per rebuild.** Each renderer builds its rows into a detached
  `DocumentFragment` and swaps it in with a single `replaceChildren`, so the
  table is not re-laid-out on every append. What is left is the branch filter
  chips (14 for Materials, 13 Labor, 2 Lump Sum, 5 BoQ), which are few enough
  not to matter.
- **A row cap, with disclosure** (`SEARCH_ROW_CAP = 300`, only while a term is
  active). A one-letter search cannot ask for an unbounded list. When the cap
  bites, an amber note under the search box says so in plain words — *Showing
  the first 300 of 844 matching rows* — and disappears on the next keystroke,
  so it never describes a list that is no longer on screen. **With no term
  there is no cap at all**, so Expand all and ordinary browsing still draw every
  row, and the result count always reports the true number of hits even when
  the drawing is capped.
- **Lazy thumbnails.** 500-odd material rows carry a photo. Those images now
  load lazily and decode asynchronously, so a search no longer fetches and
  decodes every thumbnail in the list.

Two smaller cleanups came with it: `visibleRows` remembers each node's match
verdict so a name is lower-cased once instead of twice, and the four search
boxes are wired through one `bindSearch` helper rather than four copies of the
same listener. The audit trail's own search was already debounced at 350ms; the
four lists had simply never been given the same treatment.

## BoQ grid (build 2026-10-18a)

The Build of Quantity table has 21 columns and used to be laid out at a fixed
1,560px inside a panel that is narrower than that on most laptops. Everything
past the panel edge was simply gone: no scrollbar to reach it, and the header
text cut mid-word, so *Quantity Mark-up %* read as `QUANTITY MARK-UP %` on one
line and *Original Rate – Material* as `ORIGINAL RATE –`. It now behaves like a
spreadsheet instead.

**The header stays put.** The BoQ table is inside a scrollport (`.boq-wrap`)
that scrolls both ways, so the column headings remain visible while the body
scrolls under them. The three other tables (Materials, Labor, Lump Sum) are
untouched.

**Columns.** A **Columns** button in the toolbar opens a checklist of all 21
columns with a **Show all** and a **Reset**. Each column header also carries
its own small menu for showing, hiding and pinning that one column. Hiding a
column keeps it out of the table, the footer and the widths calculation; there
is always at least one column on screen, so you cannot lock yourself out.

**Pinning.** REF and WORK DESCRIPTION are pinned by default. Up to eight
columns can be pinned to the left edge, and pinned columns stay put while the
rest of the table scrolls sideways — the two defaults mean the row identity and
its description never scroll away. Pinning from the header menu or the Columns
checklist does the same thing. Hiding a pinned column unpins it (otherwise a
hidden column would hold a slot it cannot be seen in). The top-left corner cell
is pinned on both axes, so it survives a vertical and a horizontal scroll at the
same time.

**Column width.** Every column is now wide enough for its own heading. The
width is measured rather than guessed: an off-screen probe draws each label at
the header's real 8.5px bold uppercase face with the header's real padding, and
the column takes that measurement plus room for the sort and menu buttons. The
21 default widths add up to more than the old 1,560px, which is what gives you
a reason to scroll — and dragging a column edge still works, so a width you set
by hand is respected and survives a reload.

**Scrolling.** The scrollport keeps its bottom scrollbar visible at all times
rather than only while the pointer is over the table, so there is always
something to drag to reach the far columns.

All of this is remembered per user (or per browser when signed out) and **per
project**, under the key `boq.grid.v1.<user>.<project>` — a layout set up for
one project's export does not get pushed onto another. Reset in the Columns
menu puts everything back to the defaults.

None of it touches the ledger itself: the values, the mark-up arithmetic, the
row hierarchy and collapse/expand behave exactly as before, and the footer's
Total / Budget / Profit / Remark cells stay aligned under the columns that are
actually visible.
## Column legend (build 2026-10-18b)

**What it is.** A collapsible *Column legend* panel now sits at the bottom of
the Build of Quantity card, directly under the bill. It has one row per
column — all 21 of them, in the same order as the headings — and three parts
each: the column's name, what it means in plain English, and where the number
comes from. It is open by default and folds away with one click once it has
been read.

**The formulas are the real ones.** Every entry in the third column is taken
from the arithmetic the app actually performs, not from a description of it:

- `Charged Quantity = ROUNDUP(Quantity × (1 + Quantity Mark-up % ÷ 100))`
- `Rate = ROUNDUP(Original Rate × (1 + Mark-up % ÷ 100))` — material and labour worked out separately
- `Total — Material = Rate — Material × Charged Quantity`, and likewise for Labour
- `Amount = Total — Material + Total — Labour`
- `Budget = (Original Rate — Material + Original Rate — Labour) × Charged Quantity`
- `Profit = Amount - Budget`

ROUNDUP always rounds up to two decimals, the way the reference Excel sheets
do it. The panel also spells out the fallback chain — a blank Original Rate
falls back to the row's own Material / Labour Price and then to the rate list —
and what a heading row shows in place of its own rates.

**The names match the headings exactly.** One check compares the legend's 21
column names against the 21 `<th>` labels byte for byte, so the two can never
drift apart; a second check compares each stated formula against the
JavaScript that computes it. Both have to pass before a build ships.

Markup and CSS only — no script changed, so nothing was added to the page's
runtime cost.

## Visual redesign (build 2026-10-18c)

**What it is.** A visual pass over the Build of Quantity interface. The data,
the mark-up arithmetic, the row hierarchy, collapse/expand, the column set and
the column order are all untouched — this build changes how the page looks and
how the controls answer, not what it computes. The 21 `<th>` labels are still
byte-identical to the previous build, and the same checks that guard them still
run.

**One type scale, four steps.** Everything now reads from a small set of
variables at the top of the stylesheet: a label step (12px, semi-bold, lightly
letter-spaced) for headings and field names, a body step for descriptions, a
value step for the money cells, and larger steps for the summary totals and the
grand total hero. Labels that used to be plain sentence case are now set in
uppercase, so the summary reads `ESTIMATED BUDGET` / `ESTIMATED PROFIT` as it
did before the redesign even though the markup carries the shorter wording.

**A radius ladder.** Corner rounding is three sizes rather than one: a small
size for controls (inputs, buttons, the search field), a medium size for cards
and panels, and a large size for the table container. The card keeps its
`overflow: hidden`, so the sticky header's top corners round with it.

**The summary board is grouped, not tiled.** The six metrics sit in three
labelled groups — Costs, Budget & profit, and the grand total on its own as a
hero card — each with a small icon and the value right underneath. The grid is
three columns on a wide screen, two at 1040px and one at 640px, and the hero
group drops onto its own full-width row at the two-column size. Every metric
still lives behind the same `#sumItems` … `#sumTotal` elements.

**Buttons have three tiers instead of one look.** Add-row is the primary
(solid navy), Expand / Collapse / Columns / Export are secondary (outlined),
and Clear all / Delete row are destructive (outlined in the danger colour).
All three share a height, a corner radius and the same hover, active and
disabled states, so a row of mixed buttons lines up. No button in the markup
changed class — the tiers are the existing `.btn-primary`, `.btn-ghost` and
`.btn-danger-ghost` doing the work.

**Motion, and how it is kept out of the way.** Four moments move: the summary
cards arrive, a new row fades in, a deleted row fades out before it is really
removed, and buttons lift a pixel on hover and press down on click. There is no
height animation — the list is fully re-rendered, so there is no height to
tween — and the entrance only ever plays on rows that were not in the previous
render. First paint is still, typing in a search is still, and a whole new
result set is still. The ceiling is on how many rows may move at once rather
than on how long the list is, so a single add animates wherever it happens
while expanding a long list does not. The count-up rolls the summary numbers
over 420ms, but the first time any value is written it lands on its final text
at once, so loading a project never shows numbers counting up from nothing.
Every one of these is CSS plus a few lines of script, and all of it is
switched off under `prefers-reduced-motion: reduce`.

**Readability.** The muted ink, the amber used for the owner badge and the
focus ring colour were each nudged until they clear a 4.5:1 contrast ratio in
both the light and the dark theme; two hover states that had picked up a navy
text colour now use the foreground ink, which was invisible against the dark
theme's steel background. Numeric cells keep tabular figures, and the summary
values overflow with an ellipsis rather than pushing the card wider.

**Checks.** A new harness drives the app against a DOM shim and asserts the
motion layer cannot change what the list contains: first paint adds no class,
a plain re-render adds no class, a search adds no class, an add marks exactly
the new row, a delete removes the right row after its fade, saying no to the
prompt changes nothing, the ceiling suppresses a mass arrival, and a
reduced-motion preference stops all of it. It also pins the count-up's
behaviour: the first write of a value is immediate, an unchanged value is not
rewritten, a changed value rolls and then lands on exactly the text it was
given, and a missing element returns quietly.

## Build 2026-10-19a — accounts, feedback, per-project permissions

This build moves the ledger from one shared database row to one row per
project, and adds the account layer on top of it. It does not change the bill
itself: the 21 columns, the formulas, the legend and the grid behaviour are
untouched, and every check that passed before still passes.

**One row per project.** `state.projects` used to hold every project inside a
single `ledger` row, which made it impossible to say who could edit what,
because any write replaced the whole bill for everyone. Projects now live in
their own `projects` table with an `owner_id`. The global rate libraries, the
theme and the other preferences stay in `ledger`. Saving writes only the
project being edited.

**Permissions are enforced in the database, not just in the interface.** Row
level security lets every signed-in account read every project, but lets only
the owner or an admin write one. The interface mirrors those rules through
`canEdit()`: a viewer still sees the whole bill, but the inputs take no clicks
and the add, delete and save controls are hidden rather than failing later. An
admin may edit anything.

**Usernames.** Registration asks for one, and Google sign-in derives one from
the display name, de-duplicated so two accounts cannot collide. Length,
character set and uniqueness are checked by `profiles_set_username()` on the
server rather than in the browser, so the rules hold for any client. The email
address is no longer shown anywhere in the app — the presence list, the
project owner and the admin table all show the username. Admins can rename an
account from the admin table through `admin_set_username()`, which applies the
same checks and writes to the audit trail.

**Presence.** The Online/Offline box used to loop: an empty list triggered a
refresh that reset the list to empty and triggered the box to render again, so
no row was ever drawn. Rendering is now guarded by a flag, so a user who is
online appears on first draw. `last_seen` is written by `presence_beat()` on a
heartbeat, so an offline account shows how long ago it was around rather than
nothing at all.

**Feedback.** A button in the bottom-right corner opens a dialog with a type
and a message. Submissions land in the `feedback` table with the username and
a timestamp. Reading them requires `is_staff()`, so the inbox in the admin tab
is visible to admins and moderators and to nobody else.

**Migrating existing data.** `backup_ledger_2026-10-19.sql` copies the ledger,
profiles and audit tables before anything is touched.
`migration_2026-10-19.sql` then splits the ledger into the projects table,
assigns every project to the admin account, and installs a trigger that keeps
the original ledger row frozen as a read-only snapshot. Its final query
compares project counts and row counts on both sides and prints PASS or FAIL
alongside a per-project breakdown. The split reads from the backup copy and is
skipped entirely if `projects` already has rows, so a re-run cannot overwrite
work done since.

**Checks.** The existing harnesses still pass: syntax 0, static 113/0, search
113/0, go-to-top 0 and 0, legend 0, grid 78/0. The legend check now asserts the
new stamp, and the bill header remains byte-identical to the previous build.

## Build 2026-10-19b/c — controls that were never wired

The 2026-10-19a build added markup for several features but never attached
anything to them, so the controls rendered and did nothing. Three were fixed
in `6b3f37f`:

- **Google sign-in.** The button had no click handler. It now calls
  `signInWithOAuth` and redirects back to the page it was opened from.
  Until the Google provider and the redirect URLs are configured in Supabase,
  clicking it reports the provider error in place.
- **Username at registration.** The field was collected and discarded. It is now
  saved through `profiles_set_username` once a session exists. With email
  confirmation on there is no session yet, so the message says the name will be
  based on the email and can be changed after signing in.
- **Presence heartbeat.** `last_seen` was never written. `presence_beat()` now
  fires on entry and every two minutes, and stops on sign-out. `enterApp` also
  fetches `username` so the chip, the online list and the project owner have a
  name to show.

**Feedback, 2026-10-19c.** The same defect: the dialog had no JavaScript at all,
so nothing could open and Cancel and Submit were unreachable. It is now a small
popover card above the button rather than a full-screen overlay — no backdrop,
so the page behind stays visible and clickable, and the rest of the layout is
untouched. Cancel, the X, Escape and clicking elsewhere all close it; a
successful submit validates the message, writes the row, toasts `Feedback sent`
and resets the form; a failed submit keeps the card open with the message intact.
Below 560px it becomes a bottom sheet, still without a backdrop. The `feedback`
policies are unchanged: any signed-in user may insert their own row, and reading
requires `is_staff()`.

**Unit Price Search, 2026-10-19d.** A floating "Price Search" pill sits directly
above the Feedback button. Clicking it opens a small floating panel (340px wide,
max 70vh) anchored above the stack, with no dark backdrop — the page stays visible
and clickable behind it. Only one floating panel is ever open at a time (opening
Search closes Feedback, and vice versa). The panel includes a search box (type at
least 2 characters), filter chips (All, Lump Sum, Labor, Material), a scrollable
results list (up to 20 results) and an X button. Typing searches as you go with a
200ms debounce, is case-insensitive, ignores extra spaces and still matches Khmer
text. Each result shows the description, unit, unit price ($x.xx) and a coloured
source tag (Material/Labor/Lump Sum). Keyboard navigation (Up/Down/Enter), a `/`
or Ctrl+K shortcut (ignored when typing into another field), Esc, clicking the
pill again, and clicking away all close it. Clicking a result copies the price to
the clipboard and shows a short "Copied" toast; the panel stays open. If a BOQ row
is selected, the "Use in selected row" button appears and writes the price into that
row's matching slot (Material → Material Price; Labor → Labour Price); Lump Sum
results have no BOQ slot, so the button is hidden. The search is read-only: it
walks the price lists already loaded in the app and never edits them. On phones
it drops to a bottom sheet, uses the existing `@media (max-width: 560px)` block
only, and does not add a third `@media (max-width: 780px)` block. The pill reuses
the Feedback button's size and style; its vertical offset uses `calc` with
`--h-btn-sm`, which keeps the to-go-top layout unchanged.

**Checks.** `check_static` had no failure count and no exit code, so a failing
assertion printed a line and was still treated as green. It now reports
`structural checks: N failures: M` and exits 1, and it asserts the Google,
username, presence and feedback handlers stay bound and that no full-screen
feedback backdrop returns. It also asserts the new price-search bindings, the
200ms debounce, the 2-character minimum, the cap at 20, the `/` and Ctrl+K
shortcuts, that the panels are mutually exclusive, that the feature is read-only
and that the new pill did not add a third 780px media block. `fbtest.js` drives
the popover through the DOM shim — open, Cancel, X, Escape, click-away, click-
inside, empty validation and the failed-save path — so a control that is rendered
but unbound fails the build. `psearch.js` does the same for the Unit Price
Search: open via pill and via keyboard, filter chips, Up/Down/Enter, click-away,
case-insensitive/whitespace normalization, Khmer matching, the read-only guarantee
and the "Use in selected row" slot mapping. The gates (check_syntax, check_static,
check_search, check_totop, check_totop_dom, check_legend, gridtest, fbtest,
psearch, bench_noregress, bench_debounce, motion_logic, test_lumpsum_logic) all
pass with 31/0, 85/0 and the structural/numerical totals unchanged elsewhere.

**Duplicate flat-house categories, 2026-10-19e.** The Lump Sum Work list (and,
later found, also the Material and Labor lists) had grown nameless copies of the
"Flat House Z15A1" categories — 20+ groups each titled "(untitled)" with the
same five lump-sum items repeated. Root cause: `merge_flat_house_rates.sql`
wrote its three categories as `{ "children": [...] }` with no group `"id"` and
no `"name"`, so its own idempotency guard (which searches the list for id
`fhs_1`/`fhm_1`/`fhl_1`) could never match what it had already inserted, and
every re-run appended one more copy. Fixes: the merge script now writes proper
`id`+`name` wrappers and its guard accepts either the id or the name; the app
refuses to save a heading without a title (adding a sub-item under a blank row,
indenting under a blank row, and clearing a heading's name all fall back to
"New group"); and `cleanup_flat_house_dupes.sql` is the admin cleanup — Part 1
snapshots the ledger row into `public.ledger_backup_20261019e` (with a restore
one-liner), Part 2 is read-only dry-run queries (group listing and per-leaf
DELETE/FLAG verdicts), Part 3 deletes only groups whose items exactly match the
first kept one (same description+unit+price; anything whose prices differ is
flagged, never auto-deleted) and names the kept group, Part 4 re-verifies and
confirms no BOQ reference dangles. Lump-sum rows are never referenced by BOQ
rows (those carry only `materialRef`/`laborRef`), so no project total moves.
REF numbers are computed at render time, so they renumber themselves once the
groups are gone. Gate additions: check_static grew 8 checks (46 total) for the
wrapper/guard/cleanup-script wiring and the untitled-heading rule; stamps moved
to `2026-10-19e (Lump-sum cleanup)` ×2 and all suites (check_syntax, check_static, check_search,
check_totop, check_totop_dom, check_legend, gridtest, fbtest, psearch,
bench_noregress, bench_debounce, motion_logic, test_lumpsum_logic) pass.

2026-10-19e (cleanup executed) — the dupes are gone from the live ledger: Lump Sum 26 → 2
groups ("Preliminary Work" 15 rows, "Flat House Z15A1 · Lump Sum Work" 5 rows, with Site
Preparation kept at 16279.99), Materials 8 nameless 86-row copies and Labor 8 nameless 86-row
copies deleted (14 and 13 groups remain). `cleanup_flat_house_dupes.sql` Part 3 was rewritten
to the three plain UPDATE statements that were actually executed (one per Run of the SQL
editor); the earlier DO-block version proved unreliable there. Backup snapshot:
`public.ledger_backup_20261019e`. The only dangling BOQ refs are `m1`/`m4` (material) and
`l1`/`l2`/`l3` (labor) in the demo project "Sample" — pre-existing old seed ids, already
broken in the backup taken before the cleanup, so unrelated to it.