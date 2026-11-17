# AURIX Admin Deployment

The production control panel is `admin.html`. It uses the existing AURIX Supabase project and `config.js`; `admin-local.html` is a separate browser-only prototype and is not the production admin.

## Supabase setup

1. Open the Supabase project referenced by `config.js` and run `aurix_supabase_setup.sql` in the SQL Editor. This creates or updates the admin password-change gate, protected RPCs, and public-read/admin-write policies for site assets.
2. In Supabase Auth, create or confirm the owner account for `najimnajim75599@gmail.com` and verify its email. Do not enable public registration from the admin panel. The SQL bootstrap grants the primary role only to that verified address; an unverified or different address cannot pass the admin checks.
3. Set the temporary password directly in the Supabase dashboard using the secure setup channel. Do not put it in `config.js`, browser code, source control, or chat. On first admin sign-in, AURIX requires a new password of at least 12 characters.
4. Add the deployed `admin.html` URL to Supabase Auth's allowed redirect URLs. Add the local development URL when testing. Password recovery uses Supabase Auth email delivery, so configure the project's email provider and sender settings.
5. Deploy `admin.html`, `index-5.html`, `profile.html`, `config.js`, and `aurix_supabase_setup.sql` together. Keep only the Supabase project URL and publishable/anon key in `config.js`; never put a service-role key there.
6. In Supabase Auth settings, choose the access-token lifetime and session limits appropriate for the deployment. The admin can globally revoke refresh sessions; already-issued access tokens remain usable until their configured expiry.

## What the panel manages

- Registered profiles, status flags, recent registrations, and Supabase user deletion through the admin-only RPC.
- Software releases, published announcements, public developer/site settings, AURIX homepage content, navigation and section visibility, SEO metadata, feature-card visibility/copy, and public site images.
- Activity logs, file storage, password changes, MFA, and global refresh-session revocation.

AURIX's website does not have a commerce backend, order/product catalog, revenue records, or visitor tracking. The desktop app stores its working data locally and does not report feature usage or errors to the website. Those statistics are intentionally not fabricated or collected by this admin implementation.
