import os
import time
import tempfile
import subprocess
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


def _tg_call(method: str, *, json: Optional[dict] = None, params: Optional[dict] = None, timeout: int = 30) -> dict:
    response = requests.post(_tg_url(method), json=json, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok", False):
        raise RuntimeError(f"Telegram API {method} error: {payload}")
    return payload


def send_message(chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    _tg_call("sendMessage", json=payload, timeout=30)


def send_chat_action(chat_id: int, action: str) -> None:
    _tg_call("sendChatAction", json={"chat_id": chat_id, "action": action}, timeout=15)


def compress_for_telegram(input_path: str, max_size_mb: int = 45) -> str:
    """
    Compress video for Telegram to stay under 50MB limit.
    Uses progressive compression if needed.
    """
    # Check original size
    original_size = os.path.getsize(input_path) / (1024 * 1024)
    
    if original_size <= max_size_mb:
        return input_path
    
    print(f"[telegram-bot] Comprimiendo video: {original_size:.1f}MB → <{max_size_mb}MB")
    
    # Create temporary output file
    output_path = input_path.replace(".mp4", "_compressed.mp4")
    
    try:
        # Use FFmpeg to compress: lower bitrate + CRF optimization
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-crf", "30",  # Higher CRF = smaller file (range: 0-51, default 23)
            "-preset", "fast",  # Faster but still good quality
            "-c:a", "aac",
            "-b:a", "96k",  # Reduce audio bitrate to 96kbps
            "-movflags", "+faststart",  # Enable streaming
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg compression failed: {result.stderr[-500:]}")
        
        compressed_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[telegram-bot] ✓ Video comprimido: {original_size:.1f}MB → {compressed_size:.1f}MB")
        
        # If still too large, use more aggressive compression
        if compressed_size > max_size_mb:
            print(f"[telegram-bot] Compresión agresiva: {compressed_size:.1f}MB → <{max_size_mb}MB")
            intermediate = output_path
            output_path = input_path.replace(".mp4", "_compressed_v2.mp4")
            
            cmd = [
                "ffmpeg", "-y",
                "-i", intermediate,
                "-c:v", "libx264",
                "-crf", "35",  # Very aggressive compression
                "-preset", "ultrafast",
                "-s", "1080x1920",  # Ensure resolution stays at 1080x1920
                "-c:a", "aac",
                "-b:a", "64k",  # Further reduce audio
                "-movflags", "+faststart",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
            
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg aggressive compression failed: {result.stderr[-500:]}")
            
            try:
                os.remove(intermediate)
            except Exception:
                pass
            
            final_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[telegram-bot] ✓ Video comprimido (v2): {compressed_size:.1f}MB → {final_size:.1f}MB")
        
        # Remove original
        try:
            os.remove(input_path)
        except Exception:
            pass
        
        return output_path
    
    except subprocess.TimeoutExpired:
        raise RuntimeError("Video compression timeout (>600s)")
    except Exception as e:
        # If compression fails, try to return original if it exists
        if os.path.exists(input_path):
            print(f"[telegram-bot] ⚠️ Compression error: {e}, using original file")
            return input_path
        raise


def send_video_file(chat_id: int, file_path: str, caption: str) -> None:
    # Compress for Telegram if needed (50MB limit)
    compressed_path = compress_for_telegram(file_path, max_size_mb=45)
    
    try:
        file_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
        print(f"[telegram-bot] Enviando video: {file_size_mb:.1f}MB")
        
        with open(compressed_path, "rb") as video_file:
            files = {"video": video_file}
            data = {"chat_id": chat_id, "caption": caption}
            response = requests.post(_tg_url("sendVideo"), data=data, files=files, timeout=300)
        response.raise_for_status()
        print(f"[telegram-bot] ✓ Video enviado exitosamente")
    finally:
        # Clean up compressed file if it's different from original
        try:
            if compressed_path != file_path and os.path.exists(compressed_path):
                os.remove(compressed_path)
        except Exception:
            pass


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

    if text.startswith("/start") or text.startswith("/help") or text.startswith("/ping") or text.startswith("/id"):
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
            "`/generate tu guion aquí`\n"
            "`/ping` para verificar el bot\n"
            "`/id` para ver tu chat id",
            reply_to_message_id=message_id,
        )
        return

    if text.startswith("/ping"):
        send_message(chat_id, "✅ Bot activo y escuchando.", reply_to_message_id=message_id)
        return

    if text.startswith("/id"):
        send_message(chat_id, f"🆔 Tu chat_id es: {chat_id}", reply_to_message_id=message_id)
        return

    script = parse_user_script(text)
    if not script:
        send_message(chat_id, "Mándame un texto de guion o usa /generate <guion>.", reply_to_message_id=message_id)
        return

    handle_script(chat_id=chat_id, script=script, message_id=message_id)


def run_bot() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no está configurado en .env")

    # Ensure polling mode works even if a previous webhook was configured
    _tg_call("deleteWebhook", json={"drop_pending_updates": False}, timeout=30)
    me = _tg_call("getMe", timeout=30).get("result", {})
    print(f"[telegram-bot] iniciado como @{me.get('username', 'unknown')} (id={me.get('id', 'n/a')})")
    offset = 0

    while True:
        try:
            response = requests.get(_tg_url("getUpdates"), params={"offset": offset, "timeout": POLL_TIMEOUT}, timeout=POLL_TIMEOUT + 10)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok", False):
                raise RuntimeError(f"Telegram API getUpdates error: {payload}")
            updates = payload.get("result", [])

            for upd in updates:
                offset = max(offset, upd.get("update_id", 0) + 1)
                handle_update(upd)

        except Exception as exc:
            print(f"[telegram-bot] error: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    run_bot()