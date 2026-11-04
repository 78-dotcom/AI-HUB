# Supabase free PostgreSQL setup

AI HUB uses ordinary PostgreSQL through SQLAlchemy/psycopg. Supabase is the initial
managed PostgreSQL host; the application does not depend on Supabase-specific
database features, so the same schema can be moved to another PostgreSQL host later.

## Create the free project

1. Sign in at https://supabase.com and create a new project on the Free plan.
2. Choose a region close to the application server (for the current Render deployment,
   Frankfurt is a sensible first choice if available).
3. Save the database password in a password manager. Do not put it in GitHub or chat.
4. In the Supabase dashboard open **SQL Editor**, create a query, paste the contents
   of `supabase/migrations/20261104140000_initial_schema.sql`, and run it.
5. In **Project Settings → Database → Connection string**, select the URI format.
   Prefer the session pooler or direct connection when supported by the hosting network.
   If using the transaction pooler, use its pooler connection string and test it with
   the deployed app. Replace the password placeholder locally.

## Configure the application

Set these secrets in the web service's environment settings (never commit them):

- `DATABASE_URL`: PostgreSQL connection URI from Supabase. The app accepts
  `postgresql://` and normalizes it for psycopg 3.
- `HUB_SIGNUP_CODE`: a long, random invitation code. Keep registration closed
  until the database is configured and the app is ready for invited testers.

The existing account endpoints become available when both values are present.
Restart/redeploy the web service after adding them.

## What the initial schema contains

- `users` and `account_sessions`: the existing invitation-only account system.
- `conversations` and `messages`: server-side chat history, ready for the chat
  persistence feature.
- `user_preferences`: language and selected-model preferences.
- `usage_events`: per-request provider/model/token/cost records for future quotas
  and transparent usage accounting.

The chat, preferences, and usage tables are foundation only; the current web app
does not yet write to them. Billing/subscriptions are deliberately not included
until product limits and payment rules are defined.

## Free-tier and migration notes

Free plans have provider-specific quotas, inactivity/pause rules, and backup limits
that can change. Treat this as development/early-access infrastructure, not the
only copy of production data. Before public launch, enable a paid plan or move to
managed PostgreSQL with automated backups and verify a restore.

To migrate later, export PostgreSQL with `pg_dump`, restore into the target
PostgreSQL service, update only `DATABASE_URL`, and verify row counts and login/chat
flows. Keep application SQL portable and avoid relying on Supabase-only extensions.

## Security

The app connects from its trusted backend using a server-side database credential.
Never expose the database URI, database password, or provider API keys to browser
JavaScript or a mobile app. Do not enable unrestricted public database access.
