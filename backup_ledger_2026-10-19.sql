-- ============================================================================
-- STEP 1 of the 2026-10-19 migration -- BACK UP BEFORE ANY CHANGE
-- ============================================================================
-- Run once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run.
--
-- It COPIES ledger / profiles / audit into timestamped backup tables.
-- It does NOT modify, move or delete anything you already have. The original
-- ledger row (id = 1) stays exactly where it is and is never written to.
--
-- After it runs:
--   1. The second query returns the whole ledger as readable JSON.
--      Click the "Download CSV" button in the result pane and save it as
--      ledger_backup_2026-10-19.csv  (keep this file).
--   2. Dashboard -> Table Editor -> ledger_backup_20261019 -> Export -> CSV,
--      save as ledger_backup_2026-10-19-table.csv (file-level restore point).
--   3. Confirm BOTH files are saved BEFORE running migration_2026-10-19.sql.
--
-- Safe to run more than once (it replaces its own backup tables only).

drop table if exists public.ledger_backup_20261019;
create table public.ledger_backup_20261019 as table public.ledger;

drop table if exists public.profiles_backup_20261019;
create table public.profiles_backup_20261019 as table public.profiles;

drop table if exists public.audit_backup_20261019;
create table public.audit_backup_20261019 as table public.audit;

-- 1) sanity check -- write these numbers down, the migration is verified
--    against them afterwards
select (select count(*) from public.ledger_backup_20261019)   as ledger_rows_copied,
       (select count(*) from public.profiles_backup_20261019) as profiles_copied,
       (select count(*) from public.audit_backup_20261019)    as audit_copied,
       (select jsonb_array_length(coalesce(state->'projects','[]'::jsonb))
          from public.ledger_backup_20261019 where id = 1)    as projects_in_ledger,
       (select coalesce(sum(jsonb_array_length(coalesce(p->'boq','[]'::jsonb))), 0)
          from public.ledger_backup_20261019, jsonb_array_elements(state->'projects') p
         where id = 1)                                        as boq_rows_in_ledger;

-- 2) the full state as copyable JSON (save this too)
select jsonb_pretty(state) as ledger_state
  from public.ledger_backup_20261019
 where id = 1;