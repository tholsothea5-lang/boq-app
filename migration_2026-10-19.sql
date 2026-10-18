-- ============================================================================
-- STEP 2 of the 2026-10-19 migration -- usernames, Google sign-in,
--                           per-project permissions, feedback
-- ============================================================================
-- PREREQUISITE: backup_ledger_2026-10-19.sql has been run and its two output
-- files are saved. Do not run this before that.
--
-- Run once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run.
-- Safe to run more than once. The original ledger row (id = 1) is never
-- modified or deleted -- a trigger freezes its 'projects' key so the migrated
-- snapshot stays readable as a backup forever.
--
-- Sections:
--   1  profiles: username + last_seen columns, unique username
--   2  backfill a default username for every existing account
--   3  helper functions (is_admin, set username, presence heartbeat)
--   4  handle_new_user(): username = Google display name, de-duplicated
--   5  feedback table (admin-only read)
--   6  projects table -- one row per project, owner_id, admin/owner RLS
--   7  split the ledger blob into one row per project, owner = admin
--   8  freeze the ledger's projects key (read-only backup)
--   9  verification queries

-- ---------------------------------------------------------------------------
-- 1. profiles: username + last_seen
-- ---------------------------------------------------------------------------
alter table public.profiles add column if not exists username   text;
alter table public.profiles add column if not exists last_seen  timestamptz;
-- Google sign-in can arrive without an email scope, so email is no longer
-- mandatory. The username is what the app displays everywhere.
alter table public.profiles alter column email drop not null;

drop index if exists profiles_username_uniq;
create unique index profiles_username_uniq on public.profiles (lower(username));

-- ---------------------------------------------------------------------------
-- 2. Backfill a default username for every existing account.
--    Base = the part of the email before "@", cleaned up; if that collides,
--    " 2", " 3", ... is appended until it is unique.
-- ---------------------------------------------------------------------------
with cleaned as (
  select id,
         nullif(regexp_replace(coalesce(split_part(email, '@', 1), 'user'), '[^A-Za-z0-9_. -]', '', 'g'), '') as base
    from public.profiles
   where username is null
),
numbered as (
  select id, coalesce(base, 'user') as base,
         row_number() over (partition by lower(coalesce(base, 'user')) order by id) as n
    from cleaned
)
update public.profiles p
   set username = case when d.n = 1 then d.base else d.base || ' ' || d.n end
  from numbered d
 where p.id = d.id;

-- ---------------------------------------------------------------------------
-- 3. Helper functions
-- ---------------------------------------------------------------------------
create or replace function public.is_admin()
returns boolean language sql security definer set search_path = public stable
as $$ select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin') $$;

create or replace function public.is_staff()
returns boolean language sql security definer set search_path = public stable
as $$ select exists (select 1 from public.profiles where id = auth.uid() and role in ('admin','moderator')) $$;

-- Called by the registration form and by anyone renaming themselves.
-- Uniqueness is enforced here, on the server, so two accounts cannot claim
-- the same name at the same time.
create or replace function public.profiles_set_username(new_name text)
returns void language plpgsql security definer set search_path = public
as $$
declare clean text;
begin
  clean := trim(coalesce(new_name, ''));
  if length(clean) < 3 or length(clean) > 24 then
    raise exception 'Username must be between 3 and 24 characters';
  end if;
  if clean !~ '^[A-Za-z0-9_. -]+$' then
    raise exception 'Username may only use letters, numbers, spaces, dot, dash and underscore';
  end if;
  if exists (select 1 from public.profiles where id <> auth.uid() and lower(username) = lower(clean)) then
    raise exception 'That username is already taken';
  end if;
  update public.profiles set username = clean where id = auth.uid();
end;
$$;

-- Admin only: rename somebody else's account. Same length/charset/uniqueness
-- rules as above, so an admin cannot create a name a user could not have made.
-- Every rename is written to the audit trail.
create or replace function public.admin_set_username(target_id uuid, new_name text)
returns void language plpgsql security definer set search_path = public
as $$
declare clean text;
begin
  if not exists (select 1 from public.profiles where id = auth.uid() and role = 'admin') then
    raise exception 'Only an admin can rename another account';
  end if;
  clean := trim(coalesce(new_name, ''));
  if length(clean) < 3 or length(clean) > 24 then
    raise exception 'Username must be between 3 and 24 characters';
  end if;
  if clean !~ '^[A-Za-z0-9_. -]+$' then
    raise exception 'Username may only use letters, numbers, spaces, dot, dash and underscore';
  end if;
  -- id <> target_id, so keeping the current name is not "taken by yourself"
  if exists (select 1 from public.profiles where id <> target_id and lower(username) = lower(clean)) then
    raise exception 'That username is already taken';
  end if;
  update public.profiles set username = clean where id = target_id;
  if not found then raise exception 'No such account'; end if;
  insert into public.audit (user_id, email, action, detail)
    values (auth.uid(),
            (select email from public.profiles where id = auth.uid()),
            'admin.username',
            'renamed ' || target_id::text || ' to ' || clean);
end;
$$;

-- Heartbeat: the presence box shows "last seen" for offline accounts.
create or replace function public.presence_beat()
returns void language sql security definer set search_path = public
as $$ update public.profiles set last_seen = now() where id = auth.uid() $$;

revoke all on function public.is_admin() from public;
revoke all on function public.is_staff() from public;
revoke all on function public.profiles_set_username(text) from public;
revoke all on function public.admin_set_username(uuid, text) from public;
revoke all on function public.presence_beat() from public;
grant execute on function public.is_admin() to authenticated;
grant execute on function public.is_staff() to authenticated;
grant execute on function public.profiles_set_username(text) to authenticated;
grant execute on function public.admin_set_username(uuid, text) to authenticated;
grant execute on function public.presence_beat() to authenticated;

-- ---------------------------------------------------------------------------
-- 4. New accounts (password or Google): username = display name, de-duplicated
--    so every new user lands in the Online/Offline list immediately.
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public
as $$
declare raw  text;
       base text;
       cand text;
       n    int;
begin
  raw := coalesce(new.raw_user_meta_data->>'full_name',
                  new.raw_user_meta_data->>'name',
                  split_part(coalesce(new.email,''), '@', 1),
                  'user');
  base := left(regexp_replace(trim(raw), '\s+', ' ', 'g'), 20);
  if base = '' then base := 'user'; end if;
  cand := base; n := 1;
  while exists (select 1 from public.profiles where lower(coalesce(username,'')) = lower(cand)) loop
    n := n + 1;
    cand := base || ' ' || n;
  end loop;
  insert into public.profiles (id, email, username, role)
  values (new.id, new.email, cand,
          case when not exists (select 1 from public.profiles) then 'admin' else 'user' end)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- 5. Feedback -- anyone may submit, only admins/moderators may read
-- ---------------------------------------------------------------------------
create table if not exists public.feedback (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  username   text not null default '',
  type       text not null default 'Other' check (type in ('Improvement','Bug','Other')),
  message    text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_feedback_when on public.feedback (created_at desc);

alter table public.feedback enable row level security;
drop policy if exists feedback_insert_auth on public.feedback;
create policy feedback_insert_auth on public.feedback
  for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists feedback_select_staff on public.feedback;
create policy feedback_select_staff on public.feedback
  for select to authenticated using (public.is_staff());

-- ---------------------------------------------------------------------------
-- 6. Projects -- one row per project, owner_id recorded, enforced by RLS
-- ---------------------------------------------------------------------------
create table if not exists public.projects (
  id         text primary key,
  owner_id   uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name       text not null default '',
  data       jsonb not null default '{}'::jsonb,   -- { "boq": [ ... ] }
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_projects_owner on public.projects (owner_id);

alter table public.projects enable row level security;

-- Everyone signed in may READ every project (that is the view-only tier).
drop policy if exists projects_select_auth on public.projects;
create policy projects_select_auth on public.projects
  for select to authenticated using (true);

-- Only the owner or an admin may create it, and the owner cannot be reassigned.
drop policy if exists projects_insert_own on public.projects;
create policy projects_insert_own on public.projects
  for insert to authenticated with check (owner_id = auth.uid() or public.is_admin());

drop policy if exists projects_update_own on public.projects;
create policy projects_update_own on public.projects
  for update to authenticated
  using (owner_id = auth.uid() or public.is_admin())
  with check (owner_id = auth.uid() or public.is_admin());

drop policy if exists projects_delete_own on public.projects;
create policy projects_delete_own on public.projects
  for delete to authenticated using (owner_id = auth.uid() or public.is_admin());

-- ---------------------------------------------------------------------------
-- 7. Split the ledger blob into one row per project.
--    Owner = the admin account (you reassign later). Idempotent: it is skipped
--    entirely if public.projects already has rows, so a re-run can never
--    overwrite projects people have edited since.
-- ---------------------------------------------------------------------------
with ready as (
  select 1 where not exists (select 1 from public.projects)
),
adm as (
  select id from public.profiles where role = 'admin' order by created_at asc limit 1
),
fallback as (
  select id from public.profiles order by created_at asc limit 1
),
owner as (
  select coalesce((select id from adm), (select id from fallback)) as id
),
src as (
  select jsonb_array_elements(coalesce(state->'projects','[]'::jsonb)) p
    from public.ledger_backup_20261019 where id = 1
)
insert into public.projects (id, owner_id, name, data)
select p->>'id', owner.id, coalesce(p->>'name',''),
       jsonb_build_object('boq', coalesce(p->'boq','[]'::jsonb))
from src cross join owner cross join ready
where p->>'id' is not null
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- 8. Freeze the ledger's projects key: the migrated snapshot can never be
--    overwritten, so the original row stays a valid read-only backup.
-- ---------------------------------------------------------------------------
create or replace function public.ledger_freeze_projects()
returns trigger language plpgsql as $$
begin
  if new.state ? 'projects' and old.state ? 'projects' then
    new.state := jsonb_set(new.state, '{projects}', old.state->'projects');
  end if;
  return new;
end;
$$;
drop trigger if exists trg_ledger_freeze_projects on public.ledger;
create trigger trg_ledger_freeze_projects before update on public.ledger
for each row execute function public.ledger_freeze_projects();

-- ---------------------------------------------------------------------------
-- 9. VERIFICATION -- paste this result back to me
-- ---------------------------------------------------------------------------
with ledger_projects as (
  select p->>'id' as id, coalesce(p->>'name','') as name,
         jsonb_array_length(coalesce(p->'boq','[]'::jsonb)) as boq_rows
    from public.ledger_backup_20261019, jsonb_array_elements(state->'projects') p
   where id = 1
),
table_projects as (
  select id, name, jsonb_array_length(coalesce(data->'boq','[]'::jsonb)) as boq_rows
    from public.projects
)
select (select count(*) from ledger_projects)                                              as ledger_project_count,
       (select count(*) from table_projects)                                               as migrated_project_count,
       (select coalesce(sum(boq_rows),0) from ledger_projects)                             as ledger_boq_rows,
       (select coalesce(sum(boq_rows),0) from table_projects)                              as migrated_boq_rows,
       (select count(*) from ledger_projects l join table_projects t using (id)
         where l.boq_rows <> t.boq_rows)                                                   as row_count_mismatches,
       case when (select count(*) from ledger_projects) = (select count(*) from table_projects)
             and (select coalesce(sum(boq_rows),0) from ledger_projects) =
                 (select coalesce(sum(boq_rows),0) from table_projects)
             and (select count(*) from ledger_projects l join table_projects t using (id)
                  where l.boq_rows <> t.boq_rows) = 0
            then 'PASS' else 'FAIL' end                                                     as verdict;

-- per-project breakdown (any MISMATCH line is the one to look at)
with ledger_projects as (
  select p->>'id' as id, coalesce(p->>'name','') as name,
         jsonb_array_length(coalesce(p->'boq','[]'::jsonb)) as boq_rows
    from public.ledger_backup_20261019, jsonb_array_elements(state->'projects') p
   where id = 1
),
table_projects as (
  select id, name, jsonb_array_length(coalesce(data->'boq','[]'::jsonb)) as boq_rows
    from public.projects
)
select coalesce(l.id, t.id)   as project_id,
       coalesce(l.name, t.name) as name,
       l.boq_rows             as ledger_rows,
       t.boq_rows             as migrated_rows,
       case when l.boq_rows = t.boq_rows then 'OK' else 'MISMATCH' end as status
  from ledger_projects l
  full outer join table_projects t using (id)
 order by 1;