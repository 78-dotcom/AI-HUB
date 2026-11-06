# Render PostgreSQL setup for AI HUB

The current early-access deployment uses the Render web service `AI-HUB` and the Render PostgreSQL resource `AI-HUB-DB`, both in Oregon.

## Connect the database

1. Open the [AI-HUB-DB database dashboard](https://dashboard.render.com/d/dpg-dblhve95efls73fpq9s0-a).
2. In the **Connections** section, copy the **Internal Database URL**. Use the internal URL because the web service and database are in the same Render region.
3. Open the [AI-HUB web service environment settings](https://dashboard.render.com/web/srv-dbjkq9rbc2fs73d45lqg/env).
4. Add `DATABASE_URL` with that internal URL as its value. Keep it in Render only; never commit it or paste it into chat.
5. Save the change and allow Render to restart/redeploy the service.

The application normalizes Render's `postgres://` / `postgresql://` URI to the psycopg 3 SQLAlchemy driver. On first account-related database access, SQLAlchemy creates the application tables. The checked-in SQL migration is also available at `supabase/migrations/20261104140000_initial_schema.sql` for manual provisioning when needed.

## Enable invited account registration

Add `HUB_SIGNUP_CODE` as a long, randomly generated invitation code in the same Render environment settings. Share it only with invited testers. Registration requires an email address and a password of at least 12 characters. The app stores password hashes, not plaintext passwords.

## Enable AI model calls

Add `OPENROUTER_API_KEY` in Render to enable the default OpenRouter provider. The current app will expose the configured default model `openai/gpt-4.1-mini` unless `OPENROUTER_MODEL` is set to another model ID supported by the account. Alternatively, configure `AI_PROVIDERS_JSON` for multiple OpenAI-compatible providers; see the provider configuration in the application code. Never put provider keys in browser code, GitHub, or chat.

## Enable voice (optional)

No separate Render Worker is required. In the existing AI-HUB web service's **Environment** settings, add `GEMINI_API_KEY` from Google AI Studio. This enables the Gemini Live adapter, subject to Google's free-tier quotas and data-use terms. Optionally add `OPENAI_API_KEY` to enable the paid OpenAI Realtime adapter. Both keys remain server-side. Model overrides: `GEMINI_LIVE_MODEL` and `OPENAI_REALTIME_MODEL`.

The relay permits one active session per authenticated workspace/account per running service process and forcibly closes every session after 10 minutes. The browser client must send the provider's documented session-setup message. A 10-minute limit is not a $0.50 monetary guarantee; real-time audio usage metering and a hard spending cap are not implemented yet. Use provider-side budget controls where available.

## Verify after configuration

- `https://ai-hub-w6h6.onrender.com/api/health` should return `{"status":"ok","app":"AI HUB"}`.
- `https://ai-hub-w6h6.onrender.com/api/auth/status` should report `database_configured: true` and, after setting the invitation code, `registration_enabled: true`.
- Register a test account, sign out and sign back in, then confirm that chat history and language/model preferences persist.
- Send a short prompt through a configured model and confirm that a response is returned and usage is recorded.

## Free-tier warning

The current Render PostgreSQL instance is on the Free plan and is scheduled to expire on **December 4, 2026**. Free infrastructure is suitable for development and early testing, not as the only production copy. Before public launch, move to a paid database plan or another managed PostgreSQL provider with backups, and test a restore.
