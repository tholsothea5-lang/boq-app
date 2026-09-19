-- ============================================================================
-- Site Ledger — one-time Supabase database setup
-- ============================================================================
-- Run this once in your Supabase project: Dashboard -> SQL Editor -> New query,
-- paste everything below, then click "Run". It is safe to run more than once.
--
-- It creates:
--   profiles   one row per user; the FIRST user ever registered becomes admin
--   ledger     a single shared row that holds the whole bill-of-quantities state
--   audit      a per-user change log (who, when, what changed)
-- plus row-level-security policies and the admin-only helper functions the
-- website talks to. The frontend uses only the PUBLIC (anon) key — every rule
-- below is what protects the data.

-- ---------------------------------------------------------------------------
-- 1. profiles + role columns
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  email      text not null,
  role       text not null default 'user' check (role in ('admin', 'moderator', 'user')),
  is_active  boolean not null default true,
  created_at timestamptz not null default now()
);

-- (In case this script was run before "moderator" existed:) replace the old
-- role check with the three-tier version. Safe to run more than once.
alter table public.profiles drop constraint if exists profiles_role_check;
alter table public.profiles add constraint profiles_role_check
  check (role in ('admin', 'moderator', 'user'));

-- The very first person to register becomes the admin; everyone after is a
-- plain user (the admin can promote them from the Admin panel).
create or replace function public.handle_new_user()
returns trigger
language plpgsql security definer set search_path = public
as $$
declare
  n int;
begin
  select count(*) into n from public.profiles;
  insert into public.profiles (id, email, role)
  values (new.id, new.email, case when n = 0 then 'admin' else 'user' end);
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- People who already have accounts on this project before the trigger existed:
insert into public.profiles (id, email, role)
select u.id, u.email, 'user'
from auth.users u
left join public.profiles p on p.id = u.id
where p.id is null;

-- ---------------------------------------------------------------------------
-- 2. the shared ledger (one row, id = 1)
-- ---------------------------------------------------------------------------
create table if not exists public.ledger (
  id         integer primary key check (id = 1),
  state      jsonb not null,
  updated_by uuid references auth.users (id) on delete set null,
  updated_at timestamptz not null default now()
);

insert into public.ledger (id, state) values (1, '{}'::jsonb)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- 3. the audit trail
-- ---------------------------------------------------------------------------
create table if not exists public.audit (
  id         bigint generated always as identity primary key,
  user_id    uuid references auth.users (id) on delete set null,
  email      text not null,
  action     text not null,
  detail     text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists idx_audit_when on public.audit (created_at desc);
create index if not exists idx_audit_user on public.audit (user_id);
create index if not exists idx_audit_detail on public.audit (detail text_pattern_ops);

-- ---------------------------------------------------------------------------
-- 4. security rules (row level security)
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.ledger   enable row level security;
alter table public.audit    enable row level security;

-- profiles: signed-in users may read the list (the Admin panel needs it).
-- Nobody can write their own row from the browser — role changes go through
-- the admin functions below.
drop policy if exists profiles_select_auth on public.profiles;
create policy profiles_select_auth on public.profiles
  for select to authenticated using (true);

-- ledger: signed-in users may read it and save changes to it (the whole point
-- of the tool — the ledger is shared). Everyone is trusted with edits.
drop policy if exists ledger_select_auth on public.ledger;
create policy ledger_select_auth on public.ledger
  for select to authenticated using (true);
drop policy if exists ledger_insert_auth on public.ledger;
create policy ledger_insert_auth on public.ledger
  for insert to authenticated with check (id = 1);
drop policy if exists ledger_update_auth on public.ledger;
create policy ledger_update_auth on public.ledger
  for update to authenticated with check (id = 1 and auth.uid() = updated_by);

-- audit: anyone may add THEIR OWN entry (the user_id is forced inside postgres
-- so nobody can log a change as somebody else), and only admins and moderators
-- may read it.
drop policy if exists audit_insert_auth on public.audit;
create policy audit_insert_auth on public.audit
  for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists audit_select_admin on public.audit;
create policy audit_select_admin on public.audit
  for select to authenticated
  using ((select role from public.profiles where id = auth.uid()) in ('admin', 'moderator'));

-- ---------------------------------------------------------------------------
-- 5. admin-only actions (checks run on the server, bypassing client access)
-- ---------------------------------------------------------------------------
create or replace function public.admin_set_role(target_id uuid, new_role text)
returns void
language plpgsql security definer set search_path = public
as $$
begin
  if (select role from public.profiles where id = auth.uid()) <> 'admin' then
    raise exception 'Admins only';
  end if;
  if new_role not in ('admin', 'moderator', 'user') then
    raise exception 'Invalid role';
  end if;
  if target_id = auth.uid() and new_role <> 'admin' then
    raise exception 'You cannot remove your own admin role';
  end if;
  update public.profiles set role = new_role where id = target_id;
end;
$$;

create or replace function public.admin_set_active(target_id uuid, new_active boolean)
returns void
language plpgsql security definer set search_path = public
as $$
begin
  if (select role from public.profiles where id = auth.uid()) <> 'admin' then
    raise exception 'Admins only';
  end if;
  if target_id = auth.uid() and not new_active then
    raise exception 'You cannot deactivate yourself';
  end if;
  update public.profiles set is_active = new_active where id = target_id;
end;
$$;

create or replace function public.admin_delete_user(target_id uuid)
returns void
language plpgsql security definer set search_path = public
as $$
begin
  if (select role from public.profiles where id = auth.uid()) <> 'admin' then
    raise exception 'Admins only';
  end if;
  if target_id = auth.uid() then
    raise exception 'You cannot delete your own account';
  end if;
  delete from auth.users where id = target_id;
end;
$$;

-- Revoke anything the public role could call directly; they go through the
-- policies and functions above.
revoke all on function public.admin_set_role(uuid, text) from public;
revoke all on function public.admin_set_active(uuid, boolean) from public;
revoke all on function public.admin_delete_user(uuid) from public;

-- ---------------------------------------------------------------------------
-- 6. quick check (should say profiles / ledger / audit)
-- ---------------------------------------------------------------------------
select table_name from information_schema.tables
where table_schema = 'public' and table_name in ('profiles', 'ledger', 'audit')
order by table_name;