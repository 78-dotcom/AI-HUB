"""Telegram MVP for AI HUB. Secrets are supplied through environment variables."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("ai-hub")

MAX_MESSAGE_CHARS = 12_000
MAX_HISTORY_MESSAGES = 12
MAX_REPLY_CHARS = 4_000


@dataclass(frozen=True)
class Model:
    provider_id: str
    provider_name: str
    model_name: str
    base_url: str
    api_key: str

    @property
    def label(self) -> str:
        return f"{self.provider_id}:{self.model_name}"


def _expand_env(value: str) -> str:
    """Expand a whole-value ${NAME} reference without evaluating arbitrary text."""
    match = re.fullmatch(r"\$\{([A-Z0-9_]+)\}", value.strip())
    return os.getenv(match.group(1), "") if match else value


def load_models() -> dict[str, Model]:
    raw = os.getenv("AI_PROVIDERS_JSON", "[]")
    try:
        providers = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI_PROVIDERS_JSON must be valid JSON") from exc
    if not isinstance(providers, list):
        raise RuntimeError("AI_PROVIDERS_JSON must be a JSON array")

    result: dict[str, Model] = {}
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("id", "")).strip()
        provider_name = str(provider.get("name", provider_id)).strip()
        base_url = str(provider.get("base_url", "")).strip().rstrip("/")
        api_key = _expand_env(str(provider.get("api_key", ""))).strip()
        models = provider.get("models", [])
        if not provider_id or not base_url or not api_key or not isinstance(models, list):
            logger.warning("Skipping incomplete provider configuration: %s", provider_id or "(unnamed)")
            continue
        for model_name in models:
            name = str(model_name).strip()
            if name:
                model = Model(provider_id, provider_name, name, base_url, api_key)
                result[model.label] = model
    return result


MODELS = load_models()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "").strip()
if not DEFAULT_MODEL and MODELS:
    DEFAULT_MODEL = next(iter(MODELS))
ALLOWED_USER_IDS = {
    int(item.strip()) for item in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
    if item.strip().isdigit()
}
# Public access must be explicitly enabled; otherwise an empty allow-list denies everyone.
PUBLIC_ACCESS = os.getenv("BOT_PUBLIC_ACCESS", "false").strip().lower() in {"1", "true", "yes"}
HISTORY: dict[int, deque[dict[str, str]]] = defaultdict(
    lambda: deque(maxlen=MAX_HISTORY_MESSAGES)
)
USER_MODELS: dict[int, str] = {}


def is_allowed(user_id: int) -> bool:
    return PUBLIC_ACCESS or user_id in ALLOWED_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    if not is_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Доступ к боту пока не открыт для этого аккаунта.")
        return
    await update.effective_message.reply_text(
        "Привет! Это AI HUB — тестовая версия мультимодельного ИИ-ассистента.\n\n"
        "Напиши сообщение, чтобы начать. Команды: /models, /use, /help."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Команды:\n"
            "/start — начать работу\n"
            "/models — список доступных моделей\n"
            "/use provider:model — выбрать модель\n"
            "/help — эта справка\n\n"
            "Пример выбора: /use openai:gpt-4.1-mini"
        )


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    if not is_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Доступ не открыт.")
        return
    if not MODELS:
        await update.effective_message.reply_text(
            "Пока нет настроенных моделей. Администратору нужно добавить API-ключ и модели в AI_PROVIDERS_JSON."
        )
        return
    selected = USER_MODELS.get(update.effective_user.id, DEFAULT_MODEL)
    lines = ["Доступные модели (выбор: /use provider:model):"]
    for key, model in MODELS.items():
        marker = " ✓" if key == selected else ""
        lines.append(f"• {key} — {model.provider_name}{marker}")
    await update.effective_message.reply_text("\n".join(lines))


async def use_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    if not is_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Доступ не открыт.")
        return
    requested = " ".join(context.args).strip()
    if requested not in MODELS:
        await update.effective_message.reply_text(
            "Не нашла такую модель. Посмотри список командой /models.\n"
            "Формат: /use provider_id:model_name"
        )
        return
    USER_MODELS[update.effective_user.id] = requested
    HISTORY[update.effective_user.id].clear()
    await update.effective_message.reply_text(f"Готово! Выбрана модель: {requested}")


async def ask_model(model: Model, history: list[dict[str, str]]) -> str:
    url = f"{model.base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {model.api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": model.model_name,
        "messages": history,
        "temperature": 0.7,
    }
    timeout = httpx.Timeout(60.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return str(data["choices"][0]["message"]["content"]).strip()


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.effective_message.reply_text("Доступ к боту пока не открыт.")
        return
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    if len(text) > MAX_MESSAGE_CHARS:
        await update.effective_message.reply_text("Сообщение слишком длинное. Сократи его до 12 000 символов.")
        return
    selected = USER_MODELS.get(user_id, DEFAULT_MODEL)
    model = MODELS.get(selected)
    if not model:
        await update.effective_message.reply_text(
            "ИИ-модель пока не настроена. Администратору нужно добавить API-ключ. Команда /help."
        )
        return

    history = list(HISTORY[user_id])
    history.append({"role": "user", "content": text})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        answer = await ask_model(model, history)
        if not answer:
            answer = "Модель вернула пустой ответ. Попробуй ещё раз."
        HISTORY[user_id].append({"role": "user", "content": text})
        HISTORY[user_id].append({"role": "assistant", "content": answer})
        await update.effective_message.reply_text(answer[:MAX_REPLY_CHARS])
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.warning("Provider returned HTTP %s for %s", status, model.label)
        await update.effective_message.reply_text(
            f"Поставщик ИИ вернул ошибку HTTP {status}. Проверь API-ключ, доступ к модели и баланс провайдера."
        )
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        logger.exception("AI provider request failed")
        await update.effective_message.reply_text(
            "Не удалось получить ответ от ИИ. Проверь подключение и настройки API, затем попробуй снова."
        )


async def post_init(application: Application) -> None:
    logger.info("AI HUB bot started; configured models: %d", len(MODELS))


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in the environment")
    if not MODELS:
        logger.warning("No AI models configured. Bot commands will work, but chat replies are disabled.")
    application = Application.builder().token(token).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("models", models_command))
    application.add_handler(CommandHandler("use", use_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
