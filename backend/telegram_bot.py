import os
import time
import tempfile
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path("/app/.env") if Path("/app/.env").exists() else Path(".env"), override=True)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BACKEND_URL = os.getenv("TELEGRAM_BACKEND_URL", "http://backend:8000").rstrip("/")
PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", "").rstrip("/")

DEFAULT_VOICE = os.getenv("TELEGRAM_DEFAULT_VOICE", "ErXwobaYiN019PkySvjV")
DEFAULT_RATE = os.getenv("TELEGRAM_DEFAULT_RATE", "+0%")
DEFAULT_PITCH = os.getenv("TELEGRAM_DEFAULT_PITCH", "+0Hz")
DEFAULT_SHOW_SUBTITLES = os.getenv("TELEGRAM_DEFAULT_SHOW_SUBTITLES", "true").lower() != "false"
DEFAULT_SUBTITLE_STYLE = os.getenv("TELEGRAM_DEFAULT_SUBTITLE_STYLE", "classic")

POLL_TIMEOUT = int(os.getenv("TELEGRAM_LONG_POLL_TIMEOUT", "30"))
JOB_TIMEOUT_SEC = int(os.getenv("TELEGRAM_JOB_TIMEOUT_SEC", "1800"))

allowed_chat_ids_raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
ALLOWED_CHAT_IDS = {
    chat_id.strip()
    for chat_id in allowed_chat_ids_raw.split(",")
    if chat_id.strip()
}


def _tg_url(method: str) -> str:
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def send_message(chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    requests.post(_tg_url("sendMessage"), json=payload, timeout=30)


def send_chat_action(chat_id: int, action: str) -> None:
    requests.post(_tg_url("sendChatAction"), json={"chat_id": chat_id, "action": action}, timeout=15)


def send_video_file(chat_id: int, file_path: str, caption: str) -> None:
    with open(file_path, "rb") as video_file:
        files = {"video": video_file}
        data = {"chat_id": chat_id, "caption": caption}
        response = requests.post(_tg_url("sendVideo"), data=data, files=files, timeout=300)
    response.raise_for_status()


def backend_generate(script: str) -> str:
    response = requests.post(
        f"{BACKEND_URL}/api/generate",
        json={
            "script": script,
            "voice": DEFAULT_VOICE,
            "rate": DEFAULT_RATE,
            "pitch": DEFAULT_PITCH,
            "show_subtitles": DEFAULT_SHOW_SUBTITLES,
            "subtitle_style": DEFAULT_SUBTITLE_STYLE,
            "selected_videos": {},
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["job_id"]


def backend_wait_for_job(job_id: str, chat_id: int) -> dict:
    started = time.time()
    last_sent_progress = -1

    while True:
        if time.time() - started > JOB_TIMEOUT_SEC:
            raise TimeoutError("El video tardó demasiado en generarse")

        response = requests.get(f"{BACKEND_URL}/api/status/{job_id}", timeout=30)
        response.raise_for_status()
        job = response.json()

        progress = int(job.get("progress", 0))
        status = job.get("status", "queued")
        message = job.get("message", "Procesando...")

        if progress >= last_sent_progress + 20 and status in ("queued", "running"):
            last_sent_progress = progress
            send_message(chat_id, f"⏳ {progress}% — {message}")

        if status == "done":
            return job
        if status == "error":
            raise RuntimeError(job.get("error") or "Error generando el video")

        time.sleep(2)


def backend_download_video(job_id: str) -> str:
    response = requests.get(f"{BACKEND_URL}/api/download/{job_id}", stream=True, timeout=300)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                temp_file.write(chunk)
        return temp_file.name


def handle_script(chat_id: int, script: str, message_id: Optional[int] = None) -> None:
    cleaned_script = (script or "").strip()
    if len(cleaned_script) < 12:
        send_message(chat_id, "Envíame un guion más largo (mínimo ~12 caracteres).", reply_to_message_id=message_id)
        return

    send_chat_action(chat_id, "typing")
    send_message(chat_id, "🎬 Guion recibido. Estoy generando tu video...")

    try:
        job_id = backend_generate(cleaned_script)
        send_message(chat_id, f"🧠 Job iniciado: {job_id[:8]}...", reply_to_message_id=message_id)

        backend_wait_for_job(job_id, chat_id)
        send_chat_action(chat_id, "upload_video")

        video_path = backend_download_video(job_id)
        caption = "✅ Tu video está listo"
        send_video_file(chat_id, video_path, caption=caption)

        try:
            os.remove(video_path)
        except Exception:
            pass

    except Exception as exc:
        fallback = ""
        if PUBLIC_BACKEND_URL:
            fallback = f"\nSi ya se generó, puedes descargarlo desde tu panel web en {PUBLIC_BACKEND_URL}."
        send_message(chat_id, f"❌ Error: {str(exc)}{fallback}")


def parse_user_script(text: str) -> Optional[str]:
    if not text:
        return None

    if text.startswith("/start") or text.startswith("/help"):
        return None

    if text.startswith("/generate"):
        payload = text[len("/generate"):].strip()
        return payload or None

    if text.startswith("/"):
        return None

    return text.strip()


def handle_update(update: dict) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        return

    chat_id_str = str(chat_id)
    if ALLOWED_CHAT_IDS and chat_id_str not in ALLOWED_CHAT_IDS:
        send_message(chat_id, "🚫 Este chat no está autorizado para usar este bot.")
        return

    text = (message.get("text") or "").strip()
    message_id = message.get("message_id")

    if text.startswith("/start") or text.startswith("/help"):
        send_message(
            chat_id,
            "Hola 👋\n\n"
            "Envíame un guion y te regreso un video automáticamente.\n\n"
            "También puedes usar:\n"
            "`/generate tu guion aquí`",
            reply_to_message_id=message_id,
        )
        return

    script = parse_user_script(text)
    if not script:
        send_message(chat_id, "Mándame un texto de guion o usa /generate <guion>.", reply_to_message_id=message_id)
        return

    handle_script(chat_id=chat_id, script=script, message_id=message_id)


def run_bot() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no está configurado en .env")

    print("[telegram-bot] iniciado")
    offset = 0

    while True:
        try:
            response = requests.get(
                _tg_url("getUpdates"),
                params={"offset": offset, "timeout": POLL_TIMEOUT},
                timeout=POLL_TIMEOUT + 10,
            )
            response.raise_for_status()
            payload = response.json()
            updates = payload.get("result", [])

            for upd in updates:
                offset = max(offset, upd.get("update_id", 0) + 1)
                handle_update(upd)

        except Exception as exc:
            print(f"[telegram-bot] error: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    run_bot()