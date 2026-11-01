# AI HUB

A multilingual, multi-provider AI assistant platform. The first milestone is a Telegram MVP; web, Android and iOS clients can be added on the same provider layer.

## Current MVP

- Telegram bot with `/start`, `/help`, `/models`, and `/use`.
- OpenAI-compatible API provider adapter, configurable for multiple providers.
- Per-user model selection and short in-memory conversation context.
- Secrets are read from environment variables; never commit API keys or bot tokens.
- Telegram user allow-list is enforced by default; public access requires an explicit opt-in.

## Run locally

1. Create a Telegram bot with BotFather and copy its token.
2. Copy `.env.example` to `.env` and fill in your Telegram token and provider API key(s).
3. Configure at least one provider in `AI_PROVIDERS_JSON` (see the example). For a simple OpenRouter-only setup, setting `OPENROUTER_API_KEY` is enough; when `AI_PROVIDERS_JSON` is empty, the app automatically configures `openrouter:openai/gpt-4.1-mini`. Override the model with `OPENROUTER_MODEL`.
4. Install Python 3.11+ dependencies and start the bot:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app
```

## Provider configuration

`AI_PROVIDERS_JSON` is a JSON array. Each entry has a unique `id`, display `name`, `base_url`, `api_key`, and `models` array. The API key can be written as an environment-variable reference such as `${OPENAI_API_KEY}`; the application resolves it at startup.

Example:

```json
[
  {
    "id": "openai",
    "name": "OpenAI",
    "base_url": "https://api.openai.com/v1",
    "api_key": "${OPENAI_API_KEY}",
    "models": ["gpt-4.1-mini"]
  },
  {
    "id": "openrouter",
    "name": "OpenRouter",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": "${OPENROUTER_API_KEY}",
    "models": ["openai/gpt-4.1-mini"]
  }
]
```

Only add providers for which you have your own valid API credentials and permission to use the models. Provider/model availability and pricing are controlled by the provider.

## Access control

By default, the bot is private: add your numeric Telegram user ID to `TELEGRAM_ALLOWED_USER_IDS`. An empty allow-list denies access. Only set `BOT_PUBLIC_ACCESS=true` when you intentionally want anyone to use the bot and have added suitable spending limits at the provider/hosting level. Do not expose a paid API-backed bot publicly without cost controls.

## Telegram commands

- `/myid` — show your Telegram numeric ID for private access setup
- `/start` — welcome and quick start.
- `/help` — commands and usage.
- `/models` — list configured provider/model pairs.
- `/use provider_id:model_name` — choose a model, e.g. `/use openai:gpt-4.1-mini`.
- Send a normal message to chat with the selected model.

## Deployment

For a first test, run locally. For always-on operation, deploy the container to a trusted host and set environment variables in the host's secret manager. Do not commit `.env`, tokens, or API keys.

## Roadmap

1. Validate Telegram MVP and provider connectivity.
2. Add user accounts, persistent settings, rate limits, usage/cost tracking and admin controls.
3. Add a documented REST API and web client.
4. Add Android and iOS clients.
5. Expand provider adapters and optional tools with explicit user choice.

Crypto-arbitrage is not part of the built-in product scope.

## AI HUB web app (early MVP)

The repository now includes a private, responsive web app alongside the Telegram prototype.

- `web/index.html` — responsive chat interface with English/Russian UI and model selection.
- `web_app.py` — FastAPI backend; provider API keys remain server-side.
- `Dockerfile.web` — web app container entry point.
- `render.yaml` — deploys only the web app as a free Render web service. The Telegram bot is not included in this web deployment.

### Web app configuration

Set these environment variables in the hosting provider's secret manager:

- `HUB_ACCESS_PASSWORD` — password for the private early-access workspace.
- `HUB_SESSION_SECRET` — long random secret used to sign login sessions.
- `OPENROUTER_API_KEY` — provider API key.
- `AI_PROVIDERS_JSON=[]` — enables the simple OpenRouter configuration when its API key is present.
- Optional: `OPENROUTER_MODEL` and `DEFAULT_MODEL`.

Do not commit real secrets. The first web release is a private single-workspace preview, not yet a public multi-user product. It does not yet include account registration, billing, persistent server-side chat history, or native mobile apps.


### Web app security and automated checks

- Workspace password sign-in is rate-limited to five failed attempts per client address in a 15-minute window.
- Session cookies are HTTP-only and use the Secure attribute on Render/HTTPS.
- API responses are marked as non-cacheable and receive baseline browser security headers.
- GitHub Actions runs the Python test suite on pushes to `main` and pull requests targeting `main`.
- The sign-in throttle is process-local in this preview; a multi-instance production deployment should move rate limiting to shared storage.
