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