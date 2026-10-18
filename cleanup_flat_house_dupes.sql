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
--     Expect: 2 groups in Lump Sum, 14 in Materials, 14 in Labor — plus a wall
--     of "(no name)" groups. The "(no name)" walls are the wrong copies.
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
-- Dedupe rule: keep the FIRST matching group; a later group whose items are
-- an exact copy (same description+unit+price) is removed; a later group of
-- the same shape that differs in ANY price is LEFT and reported for you to
-- decide. The kept group gets its proper name. Nothing with a different
-- description is ever touched, and BOQ rows are not involved (BOQ references
-- only material/labor leaves, and lump-sum items are never referenced).
-- ===========================================================================

do $ls_cleanup$
declare
  v_expected text[] := array[
    'engineering & management fee',
    'site preparation & temporary fence',
    'temporary water supply',
    'temporary electricity supply',
    'safety & hse (health, safety, environment)'
  ];
  v_root jsonb; v_out jsonb := '[]'::jsonb;
  v_n int; v_i int; v_grp jsonb; v_name text;
  v_cnt int; v_hits int; v_shape boolean;
  v_keep_i int := 0; v_sig text[]; v_keep_sig text[];
  v_removed int := 0; v_flagged int := 0;
  v_renamed boolean := false;
begin
  select coalesce(state->'lumpSum', '[]'::jsonb) into v_root from public.ledger where id = 1;
  if v_root is null or v_root = '[]'::jsonb then
    raise notice 'Lump sum: nothing to do (list missing or empty)';
    return;
  end if;
  v_n := jsonb_array_length(v_root);

  -- pass 1: the keep-first reference is the first flat-house-shaped group
  for v_i in 1 .. v_n loop
    v_grp := v_root -> (v_i - 1);
    v_cnt := coalesce(jsonb_array_length(v_grp->'children'), 0);
    select count(*) into v_hits
      from jsonb_array_elements(coalesce(v_grp->'children', '[]'::jsonb)) c
      where lower(btrim(coalesce(c->>'name', ''))) = any(v_expected);
    if v_cnt = 5 and v_hits = 5 and v_keep_i = 0 then
      v_keep_i := v_i;
      select coalesce(array_agg(
               lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
               order by 1), '{}')
        into v_keep_sig
        from jsonb_array_elements(v_grp->'children') c;
    end if;
  end loop;
  if v_keep_i = 0 then
    raise notice 'Lump sum: no flat-house-shaped group found, nothing to do';
    return;
  end if;

  -- pass 2: rebuild the list; exact copies after the reference are deleted,
  -- variants (different prices) are kept and reported
  for v_i in 1 .. v_n loop
    v_grp := v_root -> (v_i - 1);
    if v_i = v_keep_i then
      v_name := coalesce(btrim(coalesce(v_grp->>'name', '')), '');
      if v_name = '' or lower(v_name) in ('undefined', '(untitled)', 'untitled', 'no name') then
        v_grp := jsonb_set(v_grp, '{name}', to_jsonb('Flat House Z15A1 · Lump Sum Work'::text));
        v_renamed := true;
      end if;
      v_out := v_out || v_grp;
    else
      v_cnt := coalesce(jsonb_array_length(v_grp->'children'), 0);
      select count(*) into v_hits
        from jsonb_array_elements(coalesce(v_grp->'children', '[]'::jsonb)) c
        where lower(btrim(coalesce(c->>'name', ''))) = any(v_expected);
      v_shape := (v_cnt = 5 and v_hits = 5);
      if v_shape and v_i > v_keep_i then
        select coalesce(array_agg(
                 lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
                 order by 1), '{}')
          into v_sig
          from jsonb_array_elements(v_grp->'children') c;
        if v_sig = v_keep_sig then
          v_removed := v_removed + 1;
        else
          v_flagged := v_flagged + 1;
          v_out := v_out || v_grp;
        end if;
      else
        v_out := v_out || v_grp;
      end if;
    end if;
  end loop;

  update public.ledger
    set state = jsonb_set(state, array['lumpSum'], v_out, true)
    where id = 1;
  raise notice 'Lump sum: kept group at l1_ref %, removed % exact-duplicate group(s), % differing-price group(s) left for you',
    v_keep_i, v_removed, v_flagged;
  if v_renamed then
    raise notice 'Lump sum: the kept group was unnamed, it is now "Flat House Z15A1 · Lump Sum Work"';
  end if;
end
$ls_cleanup$;

do $fhm_cleanup$
declare
  v_root jsonb; v_out jsonb := '[]'::jsonb;
  v_n int; v_i int; v_grp jsonb; v_name text;
  v_cnt int; v_fh int; v_shape boolean;
  v_keep_i int := 0; v_sig text[]; v_keep_sig text[];
  v_removed int := 0; v_flagged int := 0;
  v_renamed boolean := false;
begin
  select coalesce(state->'materials', '[]'::jsonb) into v_root from public.ledger where id = 1;
  if v_root is null or v_root = '[]'::jsonb then
    raise notice 'Materials: nothing to do (list missing or empty)';
    return;
  end if;
  v_n := jsonb_array_length(v_root);

  for v_i in 1 .. v_n loop
    v_grp := v_root -> (v_i - 1);
    v_cnt := coalesce(jsonb_array_length(v_grp->'children'), 0);
    select count(*) into v_fh
      from jsonb_array_elements(coalesce(v_grp->'children', '[]'::jsonb)) c
      where (c->>'id') like 'fhm_1_%';
    if v_cnt = 82 and v_fh = 82 and v_keep_i = 0 then
      v_keep_i := v_i;
      select coalesce(array_agg(
               lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
               order by 1), '{}')
        into v_keep_sig
        from jsonb_array_elements(v_grp->'children') c;
    end if;
  end loop;
  if v_keep_i = 0 then
    raise notice 'Materials: no 82-row flat-house group found, nothing to do';
    return;
  end if;

  for v_i in 1 .. v_n loop
    v_grp := v_root -> (v_i - 1);
    if v_i = v_keep_i then
      v_name := coalesce(btrim(coalesce(v_grp->>'name', '')), '');
      if v_name = '' or lower(v_name) in ('undefined', '(untitled)', 'untitled', 'no name') then
        v_grp := jsonb_set(v_grp, '{name}', to_jsonb('Flat House Z15A1 · Material Rates'::text));
        v_renamed := true;
      end if;
      v_out := v_out || v_grp;
    else
      v_cnt := coalesce(jsonb_array_length(v_grp->'children'), 0);
      select count(*) into v_fh
        from jsonb_array_elements(coalesce(v_grp->'children', '[]'::jsonb)) c
        where (c->>'id') like 'fhm_1_%';
      v_shape := (v_cnt = 82 and v_fh = 82);
      if v_shape and v_i > v_keep_i then
        select coalesce(array_agg(
                 lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
                 order by 1), '{}')
          into v_sig
          from jsonb_array_elements(v_grp->'children') c;
        if v_sig = v_keep_sig then
          v_removed := v_removed + 1;
        else
          v_flagged := v_flagged + 1;
          v_out := v_out || v_grp;
        end if;
      else
        v_out := v_out || v_grp;
      end if;
    end if;
  end loop;

  update public.ledger
    set state = jsonb_set(state, array['materials'], v_out, true)
    where id = 1;
  raise notice 'Materials: kept group at l1_ref %, removed % exact-duplicate group(s), % differing-price group(s) left for you',
    v_keep_i, v_removed, v_flagged;
  if v_renamed then
    raise notice 'Materials: the kept group was unnamed, it is now "Flat House Z15A1 · Material Rates"';
  end if;
end
$fhm_cleanup$;

do $fhl_cleanup$
declare
  v_root jsonb; v_out jsonb := '[]'::jsonb;
  v_n int; v_i int; v_grp jsonb; v_name text;
  v_cnt int; v_fh int; v_shape boolean;
  v_keep_i int := 0; v_sig text[]; v_keep_sig text[];
  v_removed int := 0; v_flagged int := 0;
  v_renamed boolean := false;
begin
  select coalesce(state->'labor', '[]'::jsonb) into v_root from public.ledger where id = 1;
  if v_root is null or v_root = '[]'::jsonb then
    raise notice 'Labor: nothing to do (list missing or empty)';
    return;
  end if;
  v_n := jsonb_array_length(v_root);

  for v_i in 1 .. v_n loop
    v_grp := v_root -> (v_i - 1);
    v_cnt := coalesce(jsonb_array_length(v_grp->'children'), 0);
    select count(*) into v_fh
      from jsonb_array_elements(coalesce(v_grp->'children', '[]'::jsonb)) c
      where (c->>'id') like 'fhl_1_%';
    if v_cnt = 82 and v_fh = 82 and v_keep_i = 0 then
      v_keep_i := v_i;
      select coalesce(array_agg(
               lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
               order by 1), '{}')
        into v_keep_sig
        from jsonb_array_elements(v_grp->'children') c;
    end if;
  end loop;
  if v_keep_i = 0 then
    raise notice 'Labor: no 82-row flat-house group found, nothing to do';
    return;
  end if;

  for v_i in 1 .. v_n loop
    v_grp := v_root -> (v_i - 1);
    if v_i = v_keep_i then
      v_name := coalesce(btrim(coalesce(v_grp->>'name', '')), '');
      if v_name = '' or lower(v_name) in ('undefined', '(untitled)', 'untitled', 'no name') then
        v_grp := jsonb_set(v_grp, '{name}', to_jsonb('Flat House Z15A1 · Labor Rates'::text));
        v_renamed := true;
      end if;
      v_out := v_out || v_grp;
    else
      v_cnt := coalesce(jsonb_array_length(v_grp->'children'), 0);
      select count(*) into v_fh
        from jsonb_array_elements(coalesce(v_grp->'children', '[]'::jsonb)) c
        where (c->>'id') like 'fhl_1_%';
      v_shape := (v_cnt = 82 and v_fh = 82);
      if v_shape and v_i > v_keep_i then
        select coalesce(array_agg(
                 lower(btrim(coalesce(c->>'name', ''))) || '|' || lower(btrim(coalesce(c->>'unit', ''))) || '|' || coalesce(c->>'price', '')
                 order by 1), '{}')
          into v_sig
          from jsonb_array_elements(v_grp->'children') c;
        if v_sig = v_keep_sig then
          v_removed := v_removed + 1;
        else
          v_flagged := v_flagged + 1;
          v_out := v_out || v_grp;
        end if;
      else
        v_out := v_out || v_grp;
      end if;
    end if;
  end loop;

  update public.ledger
    set state = jsonb_set(state, array['labor'], v_out, true)
    where id = 1;
  raise notice 'Labor: kept group at l1_ref %, removed % exact-duplicate group(s), % differing-price group(s) left for you',
    v_keep_i, v_removed, v_flagged;
  if v_renamed then
    raise notice 'Labor: the kept group was unnamed, it is now "Flat House Z15A1 · Labor Rates"';
  end if;
end
$fhl_cleanup$;

-- If the Part 3 notices report flagged (differing-price) groups, decide each
-- in the app (edit the price on the row you keep), or delete a whole flagged
-- group BY ITS POSITION from the dry run — uncomment and set the position:
-- update public.ledger
--   set state = jsonb_set(state, '{lumpSum}',
--     coalesce((select jsonb_agg(grp order by ord)
--               from jsonb_array_elements(state->'lumpSum') with ordinality as g(grp, ord)
--               where g.ord <> 5), '[]'::jsonb), true)
--   where id = 1;


-- ===========================================================================
-- PART 4 — VERIFY (after Part 3)
-- 4a should show 2 Lump Sum groups, 14 Materials, 14 Labor (expected counts),
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
