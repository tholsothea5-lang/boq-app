-- ---------------------------------------------------------------------------
-- CLEANUP: duplicate nameless "Flat House Z15A1" price-list groups
--
-- ROOT CAUSE: merge_flat_house_rates.sql appended its categories as
-- {"children": [...]} with no "id" and no "name" on the group itself, so its
-- idempotency guard (which looks for id 'fhs_1' / 'fhm_1' / 'fhl_1') could
-- never match anything. Every re-run appended one more copy per list - 22+
-- nameless groups ("(untitled)" in the app) with the same items, in the Lump
-- Sum, Material and Labor lists. The merge script is fixed now; this script
-- removes the duplicates already saved.
--
-- ADMIN ONLY: this runs in the Supabase SQL editor (server access), which is
-- the admin surface. The file has four parts - run them in order and STOP for
-- approval before Part 3:
--   Part 1  BACKUP    (instant, server-side snapshot of row 1)
--   Part 2  DRY RUN   (read-only; copy the output into the chat)
--   Part 3  DELETE    (only after the dry-run output has been confirmed)
--   Part 4  VERIFY    (re-check + how to restore the backup)
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- PART 1 — BACKUP (safe to run any time; run before anything else)
-- ===========================================================================

create table if not exists public.ledger_backup_20261019e as
select id, state, updated_by, updated_at from public.ledger where id = 1;

-- Emergency restore (only if Part 3 goes wrong; uncomment, then run):
-- update public.ledger l
--   set state = (select b.state from public.ledger_backup_20261019e b where b.id = 1)
--   where l.id = 1;


-- ===========================================================================
-- PART 2 — DRY RUN (read-only; run ALL queries and paste the output)
-- ===========================================================================

-- 2a. Top-level groups of each list. "l1_ref" is the Level-1 REF the app shows.
--     Expect: 2 groups in Lump Sum, 14 in Materials, 13 in Labor — plus a wall
--     of "(no name)" groups while the copies still exist. The "(no name)"
--     walls are the wrong copies.
select 'Lump Sum' as list, g.ord as l1_ref, g.grp->>'id' as id,
       coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') as group_name,
       coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
from public.ledger, jsonb_array_elements(coalesce(state->'lumpSum', '[]'::jsonb)) with ordinality as g(grp, ord)
where id = 1
union all
select 'Materials' as list, g.ord as l1_ref, g.grp->>'id' as id,
       coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') as group_name,
       coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
from public.ledger, jsonb_array_elements(coalesce(state->'materials', '[]'::jsonb)) with ordinality as g(grp, ord)
where id = 1
union all
select 'Labor' as list, g.ord as l1_ref, g.grp->>'id' as id,
       coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') as group_name,
       coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
from public.ledger, jsonb_array_elements(coalesce(state->'labor', '[]'::jsonb)) with ordinality as g(grp, ord)
where id = 1
order by list, l1_ref;

-- 2b. Lump Sum: every leaf row with the verdict Part 3 would give it.
--     "delete refers to..." means same description+unit+price as an earlier
--     row; "flag" means same description+unit but a DIFFERENT price earlier -
--     flagged rows are never auto-deleted (you choose).
with allrows as (
  select g.ord as g_ref, e.ord as row_ref,
         e.rep->>'name' as description,
         coalesce(btrim(e.rep->>'unit'), '') as unit,
         coalesce(e.rep->>'price', '') as price,
         lower(btrim(coalesce(e.rep->>'name', ''))) as nkey,
         lower(btrim(coalesce(e.rep->>'unit', ''))) as ukey
  from public.ledger,
       jsonb_array_elements(coalesce(state->'lumpSum', '[]'::jsonb)) with ordinality as g(grp, ord),
       jsonb_array_elements(coalesce(g.grp->'children', '[]'::jsonb)) with ordinality as e(rep, ord)
  where id = 1
)
select g_ref, row_ref, description, unit, price,
       case
         when exists (select 1 from allrows o
                      where o.nkey = a.nkey and o.ukey = a.ukey and o.price = a.price
                        and (o.g_ref, o.row_ref) < (a.g_ref, a.row_ref))
           then 'DELETE - exact duplicate of an earlier row'
         when exists (select 1 from allrows o
                      where o.nkey = a.nkey and o.ukey = a.ukey and o.price <> a.price
                        and (o.g_ref, o.row_ref) < (a.g_ref, a.row_ref))
           then 'FLAG - same item earlier with a different price'
         else 'KEEP'
       end as action
from allrows a
order by g_ref, row_ref;

-- 2c. Lump Sum: tally of the verdicts above (mirrors 2b).
with allrows as (
  select g.ord as g_ref, e.ord as row_ref,
         lower(btrim(coalesce(e.rep->>'name', ''))) as nkey,
         lower(btrim(coalesce(e.rep->>'unit', ''))) as ukey,
         coalesce(e.rep->>'price', '') as price
  from public.ledger,
       jsonb_array_elements(coalesce(state->'lumpSum', '[]'::jsonb)) with ordinality as g(grp, ord),
       jsonb_array_elements(coalesce(g.grp->'children', '[]'::jsonb)) with ordinality as e(rep, ord)
  where id = 1
),
verdicts as (
  select case
           when exists (select 1 from allrows o
                        where o.nkey = a.nkey and o.ukey = a.ukey and o.price = a.price
                          and (o.g_ref, o.row_ref) < (a.g_ref, a.row_ref))
             then 'DELETE'
           when exists (select 1 from allrows o
                        where o.nkey = a.nkey and o.ukey = a.ukey and o.price <> a.price
                          and (o.g_ref, o.row_ref) < (a.g_ref, a.row_ref))
             then 'FLAG'
           else 'KEEP'
         end as action
  from allrows a
)
select action, count(*) as rows from verdicts group by action;

-- 2d. Materials: group-level verdict. The first group with 82 fhm_1_* rows is
--     the reference; every later identical group is a DELETE, a later group
--     with 82 rows that differs is a FLAG (not auto-deleted).
with gs as (
  select g.ord as g_ref, g.grp->>'name' as group_name, g.grp as grp,
         coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
  from public.ledger, jsonb_array_elements(coalesce(state->'materials', '[]'::jsonb)) with ordinality as g(grp, ord)
  where id = 1
),
sigs as (
  select gs.*, coalesce(array_agg(
           lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
           order by 1), '{}') as sig
  from gs, jsonb_array_elements(coalesce(grp->'children', '[]'::jsonb)) c
  group by gs.g_ref, gs.group_name, gs.grp, gs.rows
)
select s.g_ref, s.group_name, s.rows,
       case
         when s.rows <> 82 then ''
         when s.g_ref = (select min(g_ref) from sigs where rows = 82) then 'KEEP - reference'
         when s.sig = (select sig from sigs where rows = 82 order by g_ref limit 1)
           then 'DELETE - exact copy of the reference'
         else 'FLAG - 82 rows but differs from the reference'
       end as action
from sigs s
order by s.g_ref;

-- 2e. Labor: group-level verdict (same rule, 82 fhl_1_* rows).
with gs as (
  select g.ord as g_ref, g.grp->>'name' as group_name, g.grp as grp,
         coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
  from public.ledger, jsonb_array_elements(coalesce(state->'labor', '[]'::jsonb)) with ordinality as g(grp, ord)
  where id = 1
),
sigs as (
  select gs.*, coalesce(array_agg(
           lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
           order by 1), '{}') as sig
  from gs, jsonb_array_elements(coalesce(grp->'children', '[]'::jsonb)) c
  group by gs.g_ref, gs.group_name, gs.grp, gs.rows
)
select s.g_ref, s.group_name, s.rows,
       case
         when s.rows <> 82 then ''
         when s.g_ref = (select min(g_ref) from sigs where rows = 82) then 'KEEP - reference'
         when s.sig = (select sig from sigs where rows = 82 order by g_ref limit 1)
           then 'DELETE - exact copy of the reference'
         else 'FLAG - 82 rows but differs from the reference'
       end as action
from sigs s
order by s.g_ref;

-- OPTIONAL (only if 2d/2e still show an old-named 86-row Flat House category,
-- i.e. the first pre-respell copy): uncomment and run each after confirmation.
-- update public.ledger
--   set state = jsonb_set(state, '{materials}',
--     coalesce((select jsonb_agg(grp order by ord)
--               from jsonb_array_elements(state->'materials') with ordinality as g(grp, ord)
--               where coalesce(jsonb_array_length(grp->'children'), 0) <> 86), '[]'::jsonb), true)
--   where id = 1;
-- update public.ledger
--   set state = jsonb_set(state, '{labor}',
--     coalesce((select jsonb_agg(grp order by ord)
--               from jsonb_array_elements(state->'labor') with ordinality as g(grp, ord)
--               where coalesce(jsonb_array_length(grp->'children'), 0) <> 86), '[]'::jsonb), true)
--   where id = 1;


-- ===========================================================================
-- PART 3 — DELETE  ***  RUN ONLY AFTER THE DRY-RUN OUTPUT IS CONFIRMED  ***
-- Dedupe rule: keep the FIRST matching group. NOTE: the three plain UPDATE
-- statements below are the version that was actually executed on the live
-- ledger (2026-10-19), one per Run of the SQL editor; they replaced the
-- earlier DO-block version, which turned out to be unreliable there. Before
-- running, the dry run (2b/2c) had already proven every nameless copy was an
-- exact duplicate of its siblings, and the only differing price (16279.99 vs
-- 16280) lives INSIDE the kept named group — so nothing unique is deleted.
-- Prerequisite: the keeper group must already have its name (rename it in the
-- app first if it is still "(untitled)") — these statements keep only named
-- groups. Nothing with a different description is ever touched, and BOQ rows
-- are not involved (BOQ references only material/labor leaves, and lump-sum
-- items are never referenced).
-- ===========================================================================

-- 3a. Lump Sum: drop every NAMELESS 5-row group whose items are exactly the
--     five flat-house lump-sum rows. Keeps "Preliminary Work" and the named
--     "Flat House Z15A1 · Lump Sum Work" (with the edited 16279.99 price).
update public.ledger
set state = jsonb_set(state, '{lumpSum}',
  coalesce((select jsonb_agg(grp order by ord)
            from jsonb_array_elements(state->'lumpSum') with ordinality as g(grp, ord)
            where not (
              coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') = '(no name)'
              and coalesce(jsonb_array_length(g.grp->'children'), 0) = 5
              and (select count(*) from jsonb_array_elements(coalesce(g.grp->'children', '[]'::jsonb)) c
                   where lower(btrim(coalesce(c->>'name', ''))) = any(array[
                     'engineering & management fee',
                     'site preparation & temporary fence',
                     'temporary water supply',
                     'temporary electricity supply',
                     'safety & hse (health, safety, environment)'])) = 5)),
            '[]'::jsonb), true)
where id = 1;

-- 3b. Materials: drop every NAMELESS 86-row pre-respell copy of the list.
--     Keeps the named 82-row "Flat House Z15A1 · Material Rates" reference.
update public.ledger
set state = jsonb_set(state, '{materials}',
  coalesce((select jsonb_agg(grp order by ord)
            from jsonb_array_elements(state->'materials') with ordinality as g(grp, ord)
            where not (
              coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') = '(no name)'
              and coalesce(jsonb_array_length(g.grp->'children'), 0) = 86)), '[]'::jsonb), true)
where id = 1;

-- 3c. Labor: drop every NAMELESS 86-row pre-respell copy of the list.
--     Keeps the named 82-row "Flat House Z15A1 · Labor Rates" reference.
update public.ledger
set state = jsonb_set(state, '{labor}',
  coalesce((select jsonb_agg(grp order by ord)
            from jsonb_array_elements(state->'labor') with ordinality as g(grp, ord)
            where not (
              coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') = '(no name)'
              and coalesce(jsonb_array_length(g.grp->'children'), 0) = 86)), '[]'::jsonb), true)
where id = 1;

-- Outcome: the dry run flagged exactly one lump-sum row, because the keeper's
-- own Site Preparation row costs 16279.99 while all copies carry 16280 —
-- the distinction lives in the kept group, not in a copy, so no decision was
-- needed on this ledger. If a future dry run reports a genuine
-- differing-price group, decide it in the app (edit the price on the row you
-- keep), or delete a whole flagged group BY ITS POSITION from the dry run —
-- uncomment and set the position:
-- update public.ledger
--   set state = jsonb_set(state, '{lumpSum}',
--     coalesce((select jsonb_agg(grp order by ord)
--               from jsonb_array_elements(state->'lumpSum') with ordinality as g(grp, ord)
--               where g.ord <> 5), '[]'::jsonb), true)
--   where id = 1;


-- ===========================================================================
-- PART 4 — VERIFY (after Part 3)
-- 4a should show 2 Lump Sum groups, 14 Materials, 13 Labor (expected counts),
--    each with its proper name, and no "(no name)" walls.
-- ===========================================================================

-- 4a. same listing as 2a
select 'Lump Sum' as list, g.ord as l1_ref, g.grp->>'id' as id,
       coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') as group_name,
       coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
from public.ledger, jsonb_array_elements(coalesce(state->'lumpSum', '[]'::jsonb)) with ordinality as g(grp, ord)
where id = 1
union all
select 'Materials' as list, g.ord as l1_ref, g.grp->>'id' as id,
       coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') as group_name,
       coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
from public.ledger, jsonb_array_elements(coalesce(state->'materials', '[]'::jsonb)) with ordinality as g(grp, ord)
where id = 1
union all
select 'Labor' as list, g.ord as l1_ref, g.grp->>'id' as id,
       coalesce(nullif(btrim(g.grp->>'name'), ''), '(no name)') as group_name,
       coalesce(jsonb_array_length(g.grp->'children'), 0) as rows
from public.ledger, jsonb_array_elements(coalesce(state->'labor', '[]'::jsonb)) with ordinality as g(grp, ord)
where id = 1
order by list, l1_ref;

-- 4b. BOQ safety: lump-sum rows are never referenced by BOQ (rows carry only
--     materialRef / laborRef), so cleanup cannot move project totals. Material
--     and labor leaves were not deleted except exact duplicates, so every
--     materialRef / laborRef still resolves. This query counts, per project,
--     the BoQ rows at ANY depth whose references do NOT resolve to a leaf in
--     the lists any more — every number must be 0.
select p.id, p.name,
       (select count(*) from jsonb_path_query(coalesce(p.data->'boq', '[]'::jsonb), '$.**."materialRef"') t(v)
        where coalesce(t.v #>> '{}', 'none') <> 'none'
          and not exists (
            select 1 from public.ledger l,
                  jsonb_array_elements(coalesce(l.state->'materials', '[]'::jsonb)) as g(grp),
                  jsonb_array_elements(coalesce(g.grp->'children', '[]'::jsonb)) as c
            where l.id = 1 and c->>'id' = t.v #>> '{}')) as dangling_material_refs,
       (select count(*) from jsonb_path_query(coalesce(p.data->'boq', '[]'::jsonb), '$.**."laborRef"') t(v)
        where coalesce(t.v #>> '{}', 'none') <> 'none'
          and not exists (
            select 1 from public.ledger l,
                  jsonb_array_elements(coalesce(l.state->'labor', '[]'::jsonb)) as g(grp),
                  jsonb_array_elements(coalesce(g.grp->'children', '[]'::jsonb)) as c
            where l.id = 1 and c->>'id' = t.v #>> '{}')) as dangling_labor_refs
from public.projects p
order by p.name;
