# AI HUB

AI HUB is a multilingual workspace for using AI models from multiple providers through one interface. The product is being developed in stages: the current web app is a private early-access MVP, not yet a public multi-user platform.

## Current state

- Responsive web chat with English and Russian interface text.
- FastAPI backend; provider API keys stay on the server.
- OpenAI-compatible provider adapter, with OpenRouter available as the simple default integration.
- Server-side model list and model selection.
- Account preferences sync for language and preferred model.
- Per-account successful request and provider-reported token usage tracking; cost estimates stay disabled until provider pricing is configured.
- Password-protected single-workspace access.
- Signed HTTP-only session cookie, baseline security headers, and process-local login throttling.
- GitHub Actions runs unit tests and Python compilation checks.

The live Render service currently runs the web app from the repository's `Dockerfile`. The Telegram bot prototype in `app.py` is separate and is not part of that web deployment.

## PostgreSQL database foundation

The Render project includes a provisioned PostgreSQL database named `AI-HUB-DB` in the same Oregon region as the web service. Account-owned chat history, messages, preferences, and usage events are wired to PostgreSQL and sync across sessions once the database's **Internal Database URL** is set as `DATABASE_URL` in the Render service environment.

Follow [the Render PostgreSQL connection checklist](docs/RENDER_POSTGRES.md) to connect the existing database, enable invitation-only registration, and configure an AI provider. The app creates its SQLAlchemy tables on first account-related database access. A portable SQL migration and a Supabase alternative are also included under `supabase/` and [`docs/SUPABASE.md`](docs/SUPABASE.md). The shared-workspace preview still keeps its history in the browser; synced history requires an individual account.

## Known MVP limitations

- Individual account registration and login remain invitation-only and require a PostgreSQL `DATABASE_URL` plus private `HUB_SIGNUP_CODE` in the hosting environment.
- Account-owned chat history is stored server-side and syncs when the same individual account signs in on another device. The shared-workspace preview still uses browser-local history.
- Account signup is invitation-only; email verification, password recovery, distributed abuse protection, and admin account management are not implemented yet.
- No subscriptions, billing, provider price catalogue, or user-level spending limits yet. Token usage is recorded, but monetary cost is not guessed.
- Only OpenAI-compatible chat-completion providers are supported by the current web backend.
- No native Android or iOS apps yet.

Do not expose a paid provider key through an unrestricted public deployment. Add provider credentials only through the hosting platform's secret manager, and keep provider spending limits enabled.

## Run the web app locally

1. Use Python 3.12 or newer.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set the environment variables:

   - `HUB_ACCESS_PASSWORD` — password for the private preview.
   - `HUB_SESSION_SECRET` — long, random secret used to sign legacy preview sessions.
   - `DATABASE_URL` — optional PostgreSQL URL for individual accounts.
   - `HUB_SIGNUP_CODE` — private invitation code; registration stays disabled unless this is set.
   - `OPENROUTER_API_KEY` — optional provider key for the default OpenRouter model.
   - `AI_PROVIDERS_JSON=[]` — use the simple OpenRouter setup when its key is present.
   - `OPENROUTER_MODEL` — optional model override; defaults to `openai/gpt-4.1-mini`.
   - `DEFAULT_MODEL` — optional configured model ID override.

5. Start the API and web app:

   ```bash
   uvicorn web_app:app --reload
   ```

Open `http://127.0.0.1:8000`.

## Configure multiple providers

Set `AI_PROVIDERS_JSON` to a JSON array. Each provider entry contains an ID, display name, OpenAI-compatible base URL, API key (or an environment-variable reference), and model IDs.

Example:

```json
[
  {
    "id": "openrouter",
    "name": "OpenRouter",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": "${OPENROUTER_API_KEY}",
    "models": ["openai/gpt-4.1-mini"]
  },
  {
    "id": "openai",
    "name": "OpenAI",
    "base_url": "https://api.openai.com/v1",
    "api_key": "${OPENAI_API_KEY}",
    "models": ["gpt-4.1-mini"]
  }
]
```

Model entries may also be objects when you want richer catalogue information:

```json
{
  "id": "vision-model",
  "name": "Vision Model",
  "description": "A short description shown in the model catalogue",
  "category": "vision",
  "capabilities": ["chat", "vision"],
  "input_modalities": ["text", "image"],
  "output_modalities": ["text"],
  "context_window": 128000
}
```

String model IDs remain supported for backward compatibility. The catalogue metadata is descriptive only: listing a capability does not add an image/audio/video API adapter by itself. Only configure capabilities that the provider and selected model actually support.

Only configure providers for which you have valid credentials and permission to use the models. Availability and pricing are controlled by each provider.

## Deploy on Render

The repository includes a Render Blueprint in `render.yaml`. It describes the existing web service configuration and expects secrets to be added in Render's environment settings:

- `HUB_ACCESS_PASSWORD`
- `HUB_SESSION_SECRET`
- `OPENROUTER_API_KEY`
- `DATABASE_URL` (after a persistent PostgreSQL database is provisioned)
- `HUB_SIGNUP_CODE` (private invitation code)

Never commit real credentials, `.env` files, or API keys. The web service uses the root `Dockerfile`; the container starts Uvicorn on Render's `PORT`.

## Telegram prototype

The Telegram bot remains an experimental, separate entry point. It is started with `python -m app` after setting `TELEGRAM_BOT_TOKEN`, provider credentials, and (for private use) `TELEGRAM_ALLOWED_USER_IDS`. Public bot access is disabled unless explicitly enabled with `BOT_PUBLIC_ACCESS=true`. It is not deployed by the current Render web service.

## Product roadmap

1. Stabilize the web foundation, provider configuration, tests, and deployment.
2. Provision PostgreSQL and enable individual accounts in the deployed environment.
3. Add usage metering, quotas, email verification, password recovery, and admin controls.
4. Add more provider adapters and model capabilities with transparent pricing.
5. Add subscriptions and payment processing.
6. Expand into image, video, audio, research, coding, and agent workflows.
7. Deliver Android and iOS clients on the shared backend.

Crypto-arbitrage is not part of the built-in product scope; users choose their own tools and workflows.
