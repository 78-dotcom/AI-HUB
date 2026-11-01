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
3. Configure at least one provider in `AI_PROVIDERS_JSON` (see the example).
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
