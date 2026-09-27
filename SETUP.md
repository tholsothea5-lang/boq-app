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

## Bill of Quantities columns (build 2026-09-26a)

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

Typing in the Materials, Labor, Lump Sum Work or Bill of Quantities search box
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