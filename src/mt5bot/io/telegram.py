"""Envío de mensajes por la API de bots de Telegram (sin dependencias: urllib). Token y chat en .env."""
import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT_SECONDS = 20


class TelegramError(Exception):
    pass


def _call(token: str, method: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(API.format(token=token, method=method), data, TIMEOUT_SECONDS) as response:
            body = json.load(response)
    except (urllib.error.URLError, TimeoutError) as error:
        # El texto del error puede traer la URL, que lleva el token: no se incluye.
        raise TelegramError(f"Telegram {method}: {type(error).__name__}") from None
    if not body.get("ok"):
        raise TelegramError(f"Telegram {method}: {body.get('description')}")
    return body["result"]


def send(token: str, chat_id: str, text: str) -> None:
    _call(token, "sendMessage", {"chat_id": chat_id, "text": text})


def recent_chats(token: str) -> list[tuple[int, str]]:
    """Chats que le escribieron al bot hace poco: así se averigua el TELEGRAM_CHAT_ID."""
    chats = {}
    for update in _call(token, "getUpdates", {}):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("username") or chat.get("first_name") or ""
    return list(chats.items())
