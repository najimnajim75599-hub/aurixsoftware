begin;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text not null default '',
  status text not null default 'active' check (status in ('active', 'suspended')),
  created_at timestamptz not null default now()
);

create table if not exists public.admins (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null check (role in ('super_admin', 'moderator')),
  must_change_password boolean not null default true,
  created_at timestamptz not null default now()
);

alter table public.admins
  add column if not exists must_change_password boolean not null default true;

create or replace function public.track_admin_password_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if lower(coalesce(new.email, '')) = 'najimnajim75599@gmail.com'
    and old.encrypted_password is distinct from new.encrypted_password then
    update public.admins
    set must_change_password = false
    where user_id = new.id;
  end if;
  return new;
end;
$$;

drop trigger if exists aurix_admin_password_changed on auth.users;
create trigger aurix_admin_password_changed
after update of encrypted_password on auth.users
for each row execute function public.track_admin_password_change();

revoke all on function public.track_admin_password_change() from public, anon, authenticated;

create table if not exists public.releases (
  id uuid primary key default gen_random_uuid(),
  version text not null,
  platform text not null check (platform in ('windows', 'android', 'other')),
  file_path text,
  file_url text not null,
  file_size bigint not null default 0 check (file_size >= 0),
  notes text not null default '',
  min_version text,
  downloads bigint not null default 0 check (downloads >= 0),
  published boolean not null default false,
  is_latest boolean not null default false,
  downloads_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (version, platform)
);

create unique index if not exists releases_one_latest_per_platform
  on public.releases (platform) where is_latest;

create table if not exists public.announcements (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null default '',
  kind text not null default 'info' check (kind in ('info', 'update', 'maintenance')),
  active boolean not null default true,
  publish_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.site_settings (
  key text primary key,
  value text not null default '',
  updated_at timestamptz not null default now()
);

create table if not exists public.admin_logs (
  id uuid primary key default gen_random_uuid(),
  admin_email text not null,
  action text not null,
  detail text not null default '',
  created_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'full_name', ''))
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists aurix_handle_new_user on auth.users;
create trigger aurix_handle_new_user
after insert on auth.users
for each row execute function public.handle_new_user();

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.admins a
    join auth.users u on u.id = a.user_id
    where a.user_id = auth.uid()
      and lower(u.email) = 'najimnajim75599@gmail.com'
      and u.email_confirmed_at is not null
      and not a.must_change_password
  );
$$;

create or replace function public.is_super_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.admins a
    join auth.users u on u.id = a.user_id
    where a.user_id = auth.uid()
      and a.role = 'super_admin'
      and lower(u.email) = 'najimnajim75599@gmail.com'
      and u.email_confirmed_at is not null
      and not a.must_change_password
  );
$$;

create or replace function public.my_role()
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select a.role
  from public.admins a
  join auth.users u on u.id = a.user_id
  where a.user_id = auth.uid()
    and lower(u.email) = 'najimnajim75599@gmail.com'
    and u.email_confirmed_at is not null;
$$;

create or replace function public.admin_password_change_required()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce((
    select a.must_change_password
    from public.admins a
    join auth.users u on u.id = a.user_id
    where a.user_id = auth.uid()
      and lower(u.email) = 'najimnajim75599@gmail.com'
      and u.email_confirmed_at is not null
  ), true);
$$;

create or replace function public.admin_delete_user(uid uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not public.is_super_admin() then
    raise exception 'Super administrator access required';
  end if;
  if uid is null or uid = auth.uid() then
    raise exception 'Cannot delete the active administrator account';
  end if;
  delete from auth.users where id = uid;
  if not found then
    raise exception 'User not found';
  end if;
end;
$$;

create or replace function public.log_action(a text, d text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_email text;
begin
  if not public.is_admin() then
    raise exception 'Administrator access required';
  end if;
  select u.email into v_email from auth.users u where u.id = auth.uid();
  insert into public.admin_logs (admin_email, action, detail)
  values (coalesce(v_email, ''), left(a, 100), left(coalesce(d, ''), 2000));
end;
$$;

create or replace function public.set_latest(rid uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_platform text;
begin
  if not public.is_super_admin() then
    raise exception 'Super administrator access required';
  end if;
  select r.platform into v_platform
  from public.releases r
  where r.id = rid and r.published and r.downloads_enabled;
  if v_platform is null then
    raise exception 'Release must be published and downloads enabled before it can go live';
  end if;
  update public.releases r set is_latest = (r.id = rid)
  where r.platform = v_platform;
end;
$$;

create or replace function public.publish_release(rid uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_platform text;
  v_downloads_enabled boolean;
begin
  if not public.is_super_admin() then
    raise exception 'Super administrator access required';
  end if;
  select r.platform, r.downloads_enabled into v_platform, v_downloads_enabled
  from public.releases r where r.id = rid;
  if not found then
    raise exception 'Release not found';
  end if;
  if not v_downloads_enabled then
    raise exception 'Enable downloads before publishing this release';
  end if;
  update public.releases set is_latest = false where platform = v_platform and is_latest;
  update public.releases set published = true, is_latest = true where id = rid;
end;
$$;

create or replace function public.unpublish_release(rid uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_platform text;
  v_fallback uuid;
begin
  if not public.is_super_admin() then
    raise exception 'Super administrator access required';
  end if;
  select r.platform into v_platform from public.releases r where r.id = rid;
  if not found then
    raise exception 'Release not found';
  end if;
  update public.releases set published = false, is_latest = false where id = rid;
  select r.id into v_fallback
  from public.releases r
  where r.platform = v_platform and r.published and r.downloads_enabled
  order by r.created_at desc
  limit 1;
  if v_fallback is not null then
    update public.releases r set is_latest = (r.id = v_fallback)
    where r.platform = v_platform;
  end if;
end;
$$;

create or replace function public.count_download(v text)
returns void
language sql
security definer
set search_path = ''
as $$
  update public.releases r
  set downloads = r.downloads + 1
  where r.version = v and r.platform = 'windows'
    and r.published and r.downloads_enabled;
$$;

alter table public.profiles enable row level security;
alter table public.admins enable row level security;
alter table public.releases enable row level security;
alter table public.announcements enable row level security;
alter table public.site_settings enable row level security;
alter table public.admin_logs enable row level security;

grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.profiles, public.admins,
  public.releases, public.announcements, public.site_settings, public.admin_logs
  to anon, authenticated;

drop policy if exists profiles_admin_read on public.profiles;
create policy profiles_admin_read on public.profiles
  for select to authenticated using (public.is_admin());
drop policy if exists profiles_admin_update on public.profiles;
create policy profiles_admin_update on public.profiles
  for update to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists admins_admin_read on public.admins;
create policy admins_admin_read on public.admins
  for select to authenticated using (public.is_admin());
drop policy if exists admins_super_admin_write on public.admins;
create policy admins_super_admin_write on public.admins
  for all to authenticated using (public.is_super_admin()) with check (public.is_super_admin());

drop policy if exists releases_public_read on public.releases;
create policy releases_public_read on public.releases
  for select to anon, authenticated
  using (public.is_admin() or (published and downloads_enabled));
drop policy if exists releases_admin_insert on public.releases;
create policy releases_admin_insert on public.releases
  for insert to authenticated with check (public.is_admin());
drop policy if exists releases_admin_update on public.releases;
create policy releases_admin_update on public.releases
  for update to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists releases_admin_delete on public.releases;
create policy releases_admin_delete on public.releases
  for delete to authenticated using (public.is_admin());

drop policy if exists announcements_public_read on public.announcements;
create policy announcements_public_read on public.announcements
  for select to anon, authenticated
  using (public.is_admin() or (active and publish_at <= now()));
drop policy if exists announcements_admin_write on public.announcements;
create policy announcements_admin_write on public.announcements
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists site_settings_public_read on public.site_settings;
create policy site_settings_public_read on public.site_settings
  for select to anon, authenticated using (true);
drop policy if exists site_settings_admin_write on public.site_settings;
create policy site_settings_admin_write on public.site_settings
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists admin_logs_admin_read on public.admin_logs;
create policy admin_logs_admin_read on public.admin_logs
  for select to authenticated using (public.is_admin());

 grant execute on function public.is_admin() to anon, authenticated;
grant execute on function public.is_super_admin() to anon, authenticated;
grant execute on function public.my_role() to anon, authenticated;
grant execute on function public.log_action(text, text) to authenticated;
grant execute on function public.set_latest(uuid) to authenticated;
revoke all on function public.publish_release(uuid) from public, anon;
revoke all on function public.unpublish_release(uuid) from public, anon;
grant execute on function public.publish_release(uuid) to authenticated;
grant execute on function public.unpublish_release(uuid) to authenticated;
grant execute on function public.count_download(text) to anon, authenticated;
revoke all on function public.admin_password_change_required() from public, anon;
revoke all on function public.admin_delete_user(uuid) from public, anon;
grant execute on function public.admin_password_change_required() to authenticated;
grant execute on function public.admin_delete_user(uuid) to authenticated;

insert into storage.buckets (id, name, public)
values ('releases', 'releases', true), ('profile', 'profile', true)
on conflict (id) do update set public = excluded.public;

insert into storage.buckets (id, name, public)
values ('site-assets', 'site-assets', true)
on conflict (id) do nothing;

drop policy if exists aurix_storage_admin_list on storage.objects;
create policy aurix_storage_admin_list on storage.objects
  for select to authenticated using (
    bucket_id in ('releases', 'profile') and public.is_admin()
  );
drop policy if exists aurix_storage_admin_upload on storage.objects;
create policy aurix_storage_admin_upload on storage.objects
  for insert to authenticated with check (
    bucket_id in ('releases', 'profile') and public.is_admin()
  );
drop policy if exists aurix_storage_admin_update on storage.objects;
create policy aurix_storage_admin_update on storage.objects
  for update to authenticated using (
    bucket_id in ('releases', 'profile') and public.is_admin()
  ) with check (
    bucket_id in ('releases', 'profile') and public.is_admin()
  );
drop policy if exists aurix_storage_admin_delete on storage.objects;
create policy aurix_storage_admin_delete on storage.objects
  for delete to authenticated using (
    bucket_id in ('releases', 'profile') and public.is_admin()
  );

drop policy if exists aurix_site_assets_public_read on storage.objects;
create policy aurix_site_assets_public_read on storage.objects
  for select to anon, authenticated using (bucket_id = 'site-assets');
drop policy if exists aurix_site_assets_admin_upload on storage.objects;
create policy aurix_site_assets_admin_upload on storage.objects
  for insert to authenticated with check (bucket_id = 'site-assets' and public.is_admin());
drop policy if exists aurix_site_assets_admin_update on storage.objects;
create policy aurix_site_assets_admin_update on storage.objects
  for update to authenticated using (bucket_id = 'site-assets' and public.is_admin())
  with check (bucket_id = 'site-assets' and public.is_admin());
drop policy if exists aurix_site_assets_admin_delete on storage.objects;
create policy aurix_site_assets_admin_delete on storage.objects
  for delete to authenticated using (bucket_id = 'site-assets' and public.is_admin());

insert into public.admins (user_id, role)
select u.id, 'super_admin'
from auth.users u
where lower(u.email) = lower('najimnajim75599@gmail.com')
  and u.email_confirmed_at is not null
on conflict (user_id) do update set role = excluded.role;

notify pgrst, 'reload schema';

commit;
