# AI HUB

AI HUB is a multilingual workspace for using AI models from multiple providers through one interface. The product is being developed in stages: the current web app is a private early-access MVP, not yet a public multi-user platform.

## Current state

- Responsive web chat with English and Russian interface text.
- FastAPI backend; provider API keys stay on the server.
- OpenAI-compatible provider adapter, with OpenRouter available as the simple default integration.
- Server-side model list and model selection.
- Password-protected single-workspace access.
- Signed HTTP-only session cookie, baseline security headers, and process-local login throttling.
- GitHub Actions runs unit tests and Python compilation checks.

The live Render service currently runs the web app from the repository's `Dockerfile`. The Telegram bot prototype in `app.py` is separate and is not part of that web deployment.

## Known MVP limitations

- Individual account endpoints and UI are implemented on the feature branch, but they remain unavailable in production until a PostgreSQL `DATABASE_URL` and private `HUB_SIGNUP_CODE` are configured.
- Chat history is stored in the browser's local storage, not in a server database. It does not sync between devices.
- Account signup is invitation-only; email verification, password recovery, distributed abuse protection, and admin account management are not implemented yet.
- No subscriptions, billing, usage metering, or user-level spending limits yet.
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
   - `HUB_SESSION_SECRET` — long, random secret used to sign legacy preview sessions.\n   - `DATABASE_URL` — optional PostgreSQL URL for individual accounts.\n   - `HUB_SIGNUP_CODE` — private invitation code; registration stays disabled unless this is set.
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

Only configure providers for which you have valid credentials and permission to use the models. Availability and pricing are controlled by each provider.

## Deploy on Render

The repository includes a Render Blueprint in `render.yaml`. It describes the existing web service configuration and expects secrets to be added in Render's environment settings:

- `HUB_ACCESS_PASSWORD`
- `HUB_SESSION_SECRET`
- `OPENROUTER_API_KEY`

Never commit real credentials, `.env` files, or API keys. The web service uses the root `Dockerfile`; the container starts Uvicorn on Render's `PORT`.

## Telegram prototype

The Telegram bot remains an experimental, separate entry point. It is started with `python -m app` after setting `TELEGRAM_BOT_TOKEN`, provider credentials, and (for private use) `TELEGRAM_ALLOWED_USER_IDS`. Public bot access is disabled unless explicitly enabled with `BOT_PUBLIC_ACCESS=true`. It is not deployed by the current Render web service.

## Product roadmap

1. Stabilize the web foundation, provider configuration, tests, and deployment.
2. Add individual accounts, secure password recovery, and persistent user data.
3. Add server-side chat history, usage metering, quotas, and admin controls.
4. Add more provider adapters and model capabilities with transparent pricing.
5. Add subscriptions and payment processing.
6. Expand into image, video, audio, research, coding, and agent workflows.
7. Deliver Android and iOS clients on the shared backend.

Crypto-arbitrage is not part of the built-in product scope; users choose their own tools and workflows.
