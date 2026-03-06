"""
VideoGen Backend — FastAPI Main
Handles script parsing, TTS generation, video search, and composition.
"""
import os
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv, dotenv_values

from modules.script_parser import parse_script
from modules.tts import generate_audio_sync, get_available_voices, DEFAULT_VOICE
from modules.video_search import (
    search_and_download_video,
    search_and_download_video_info,
    search_video_options,
    download_video_from_url,
    infer_provider_from_url,
)
from modules.composer import compose_video, get_audio_duration

ENV_FILE = Path("/app/.env") if Path("/app/.env").exists() else Path(".env")
load_dotenv(dotenv_path=ENV_FILE, override=True)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_DEFAULT_VOICE = os.getenv("TELEGRAM_DEFAULT_VOICE", DEFAULT_VOICE)
TELEGRAM_DEFAULT_RATE = os.getenv("TELEGRAM_DEFAULT_RATE", "+0%")
TELEGRAM_DEFAULT_PITCH = os.getenv("TELEGRAM_DEFAULT_PITCH", "+0Hz")
TELEGRAM_DEFAULT_SHOW_SUBTITLES = os.getenv("TELEGRAM_DEFAULT_SHOW_SUBTITLES", "true").lower() != "false"
TELEGRAM_DEFAULT_SUBTITLE_STYLE = os.getenv("TELEGRAM_DEFAULT_SUBTITLE_STYLE", "classic")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

OUTPUT_DIR = Path("/app/output")
CACHE_DIR = Path("/app/cache")
TEMP_DIR = Path("/app/cache/temp")

for d in [OUTPUT_DIR, CACHE_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="VideoGen API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["http://localhost:5173"],
    allow_credentials="*" not in CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store: job_id -> status dict
jobs: Dict[str, Dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=2)

# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class GenerateRequest(BaseModel):
    script: str
    voice: str = DEFAULT_VOICE
    rate: str = "+0%"
    pitch: str = "+0Hz"
    show_subtitles: bool = True
    subtitle_style: str = "classic"
    selected_videos: Dict[str, str] = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    job_id: str
    segments: list
    message: str


class SetupRequest(BaseModel):
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    elevenlabs_api_key: str
    deepgram_api_key: str
    telegram_bot_token: str = ""

class VoicePreviewRequest(BaseModel):
    text: str
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"


class PreferencesRequest(BaseModel):
    voice: str = DEFAULT_VOICE
    rate: str = "+0%"
    pitch: str = "+0Hz"
    show_subtitles: bool = True
    subtitle_style: str = "classic"


class ParseRequest(BaseModel):
    script: str


class VideoOptionsRequest(BaseModel):
    keywords: str
    context_text: str = ""
    min_duration: int = 5
    limit: int = 8
    global_search: bool = False
    page: int = 1
    exclude_urls: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "configured": bool(PEXELS_API_KEY or PIXABAY_API_KEY),
        "pexels_configured": bool(PEXELS_API_KEY),
        "pixabay_configured": bool(PIXABAY_API_KEY),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "deepgram_configured": bool(DEEPGRAM_API_KEY),
        "telegram_bot_configured": bool(TELEGRAM_BOT_TOKEN),
    }


@app.get("/api/config")
def get_config():
    """Return current configuration (keys are masked for security)."""
    return {
        "configured": bool(PEXELS_API_KEY or PIXABAY_API_KEY),
        "pexels_key_preview": f"...{PEXELS_API_KEY[-4:]}" if PEXELS_API_KEY else "",
        "pixabay_key_preview": f"...{PIXABAY_API_KEY[-4:]}" if PIXABAY_API_KEY else "",
        "elevenlabs_key_preview": f"...{ELEVENLABS_API_KEY[-4:]}" if ELEVENLABS_API_KEY else "",
        "deepgram_key_preview": f"...{DEEPGRAM_API_KEY[-4:]}" if DEEPGRAM_API_KEY else "",
        "telegram_bot_token_preview": f"...{TELEGRAM_BOT_TOKEN[-6:]}" if TELEGRAM_BOT_TOKEN else "",
    }


@app.get("/api/preferences")
def get_preferences():
    """Return current default generation preferences used by Telegram bot and web defaults sync."""
    return {
        "voice": TELEGRAM_DEFAULT_VOICE,
        "rate": TELEGRAM_DEFAULT_RATE,
        "pitch": TELEGRAM_DEFAULT_PITCH,
        "show_subtitles": TELEGRAM_DEFAULT_SHOW_SUBTITLES,
        "subtitle_style": TELEGRAM_DEFAULT_SUBTITLE_STYLE,
    }


@app.post("/api/preferences")
def save_preferences(req: PreferencesRequest):
    """Persist default generation preferences to .env for bot/web synchronization."""
    voice = (req.voice or "").strip() or DEFAULT_VOICE
    rate = (req.rate or "").strip() or "+0%"
    pitch = (req.pitch or "").strip() or "+0Hz"
    subtitle_style = (req.subtitle_style or "").strip() or "classic"

    _write_env({
        "TELEGRAM_DEFAULT_VOICE": voice,
        "TELEGRAM_DEFAULT_RATE": rate,
        "TELEGRAM_DEFAULT_PITCH": pitch,
        "TELEGRAM_DEFAULT_SHOW_SUBTITLES": "true" if req.show_subtitles else "false",
        "TELEGRAM_DEFAULT_SUBTITLE_STYLE": subtitle_style,
    })
    _reload_env_globals()

    return {
        "success": True,
        "message": "Preferencias guardadas",
        "preferences": {
            "voice": TELEGRAM_DEFAULT_VOICE,
            "rate": TELEGRAM_DEFAULT_RATE,
            "pitch": TELEGRAM_DEFAULT_PITCH,
            "show_subtitles": TELEGRAM_DEFAULT_SHOW_SUBTITLES,
            "subtitle_style": TELEGRAM_DEFAULT_SUBTITLE_STYLE,
        },
    }


@app.post("/api/setup")
def setup(req: SetupRequest):
    """Save configuration to .env file and reload env vars."""
    # Only update non-empty keys (preserve existing if user leaves blank)
    new_pexels = req.pexels_api_key.strip()
    new_pixabay = req.pixabay_api_key.strip()
    new_elevenlabs = req.elevenlabs_api_key.strip()
    new_deepgram = req.deepgram_api_key.strip()
    new_telegram_bot_token = req.telegram_bot_token.strip()

    pexels_key = new_pexels if new_pexels else PEXELS_API_KEY
    pixabay_key = new_pixabay if new_pixabay else PIXABAY_API_KEY
    elevenlabs_key = new_elevenlabs if new_elevenlabs else ELEVENLABS_API_KEY
    deepgram_key = new_deepgram if new_deepgram else DEEPGRAM_API_KEY
    telegram_bot_token = new_telegram_bot_token if new_telegram_bot_token else TELEGRAM_BOT_TOKEN

    # Validate NEW keys only (don't re-validate existing)
    if new_pexels and len(new_pexels) < 20:
        raise HTTPException(status_code=400, detail="La API key de Pexels parece inválida (muy corta)")
    if new_pixabay and len(new_pixabay) < 12:
        raise HTTPException(status_code=400, detail="La API key de Pixabay parece inválida (muy corta)")
    if new_telegram_bot_token and ":" not in new_telegram_bot_token:
        raise HTTPException(status_code=400, detail="El token del bot de Telegram parece inválido")

    # Require at least one video provider (existing or new)
    if not pexels_key and not pixabay_key:
        raise HTTPException(status_code=400, detail="Debes configurar al menos una API key de videos (Pexels o Pixabay)")

    # Write to .env file
    _write_env({
        "PEXELS_API_KEY": pexels_key, 
        "PIXABAY_API_KEY": pixabay_key,
        "ELEVENLABS_API_KEY": elevenlabs_key,
        "DEEPGRAM_API_KEY": deepgram_key,
        "TELEGRAM_BOT_TOKEN": telegram_bot_token,
    })

    # Reload in-process
    _reload_env_globals()

    return {"success": True, "message": "Configuración guardada correctamente"}


def _write_env(updates: dict):
    """Merge updates into the .env file."""
    existing = {}
    if ENV_FILE.exists():
        existing = dict(dotenv_values(ENV_FILE))
    existing.update(updates)
    with open(ENV_FILE, "w") as f:
        for k, v in existing.items():
            f.write(f"{k}={v}\n")


def _reload_env_globals():
    global PEXELS_API_KEY, PIXABAY_API_KEY, ELEVENLABS_API_KEY, DEEPGRAM_API_KEY, TELEGRAM_BOT_TOKEN
    global TELEGRAM_DEFAULT_VOICE, TELEGRAM_DEFAULT_RATE, TELEGRAM_DEFAULT_PITCH
    global TELEGRAM_DEFAULT_SHOW_SUBTITLES, TELEGRAM_DEFAULT_SUBTITLE_STYLE

    load_dotenv(dotenv_path=ENV_FILE, override=True)
    PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
    PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_DEFAULT_VOICE = os.getenv("TELEGRAM_DEFAULT_VOICE", DEFAULT_VOICE)
    TELEGRAM_DEFAULT_RATE = os.getenv("TELEGRAM_DEFAULT_RATE", "+0%")
    TELEGRAM_DEFAULT_PITCH = os.getenv("TELEGRAM_DEFAULT_PITCH", "+0Hz")
    TELEGRAM_DEFAULT_SHOW_SUBTITLES = os.getenv("TELEGRAM_DEFAULT_SHOW_SUBTITLES", "true").lower() != "false"
    TELEGRAM_DEFAULT_SUBTITLE_STYLE = os.getenv("TELEGRAM_DEFAULT_SUBTITLE_STYLE", "classic")


@app.get("/api/voices")
def voices():
    return get_available_voices()


@app.post("/api/preview-voice")
def preview_voice(req: VoicePreviewRequest):
    """Generate and return a short audio preview for a specific voice setting."""
    text = req.text.strip()
    if not text:
        text = "Hola, esta es una prueba de cómo suena esta voz en tu generador de videos."
    
    preview_id = str(uuid.uuid4())
    preview_path = str(TEMP_DIR / f"preview_{preview_id}.mp3")
    
    try:
        generate_audio_sync(
            text=text,
            output_path=preview_path,
            voice=req.voice,
            rate=req.rate,
            pitch=req.pitch
        )
        return FileResponse(preview_path, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error previewing voice: {str(e)}")


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    if not PEXELS_API_KEY and not PIXABAY_API_KEY:
        raise HTTPException(status_code=500, detail="No video provider configured: set PEXELS_API_KEY or PIXABAY_API_KEY")

    if not req.script.strip():
        raise HTTPException(status_code=400, detail="Script cannot be empty")

    # Parse the script into segments
    segments = parse_script(req.script)
    if not segments:
        raise HTTPException(status_code=400, detail="Could not parse any segments from the script")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "message": "En cola...",
        "segments": segments,
        "error": None,
        "output_path": None,
    }

    # Run generation in background
    background_tasks.add_task(
        run_generation,
        job_id=job_id,
        segments=segments,
        voice=req.voice,
        rate=req.rate,
        pitch=req.pitch,
        show_subtitles=req.show_subtitles,
        subtitle_style=req.subtitle_style,
        selected_videos=req.selected_videos,
    )

    return GenerateResponse(
        job_id=job_id,
        segments=segments,
        message=f"Job iniciado con {len(segments)} segmento(s)"
    )


@app.post("/api/parse")
def parse(req: ParseRequest):
    if not req.script.strip():
        return {"segments": []}
    segments = parse_script(req.script)
    return {"segments": segments}


@app.post("/api/video-options")
def video_options(req: VideoOptionsRequest):
    if not PEXELS_API_KEY and not PIXABAY_API_KEY:
        raise HTTPException(status_code=500, detail="No video provider configured")

    options = search_video_options(
        keywords=req.keywords,
        pexels_api_key=PEXELS_API_KEY,
        pixabay_api_key=PIXABAY_API_KEY,
        context_text=req.context_text,
        min_duration=max(3, int(req.min_duration)),
        limit=max(1, min(50, int(req.limit))),
        global_search=bool(req.global_search),
        page=max(1, int(req.page)),
        exclude_urls=set(req.exclude_urls or []),
    )
    return {"options": options}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/stream/{job_id}")
async def stream_status(job_id: str):
    """Server-Sent Events endpoint for real-time progress."""
    async def event_generator():
        import json
        while True:
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            yield f"data: {json.dumps(job)}\n\n"

            if job["status"] in ("done", "error"):
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/download/{job_id}")
def download(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail=f"Job not done yet: {job['status']}")

    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"reel_{job_id[:8]}.mp4",
    )


# ─────────────────────────────────────────────
# Generation Worker
# ─────────────────────────────────────────────

def run_generation(job_id: str, segments: list, voice: str, rate: str, pitch: str, show_subtitles: bool, subtitle_style: str = "classic", selected_videos: Optional[Dict[str, str]] = None):
    """Background task: TTS + video search + composition."""
    job = jobs[job_id]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        job["status"] = "running"
        total = len(segments)
        composed_segments = []
        used_video_urls: set[str] = set()

        selected_videos = selected_videos or {}

        for i, seg in enumerate(segments):
            # Update progress
            prog_base = int((i / total) * 80)
            job["progress"] = prog_base
            job["message"] = f"Segmento {i + 1}/{total}: generando voz..."

            # 1. Generate TTS audio
            audio_path = str(job_dir / f"audio_{i:03d}.mp3")
            tts_result = generate_audio_sync(
                text=seg["text"],
                output_path=audio_path,
                voice=voice,
                rate=rate,
                pitch=pitch,
            )

            # 2. Measure actual audio duration
            audio_duration = get_audio_duration(tts_result["audio_path"])

            # 3. Download stock video
            job["message"] = f"Segmento {i + 1}/{total}: buscando video..."
            manual_url = selected_videos.get(str(seg.get("id", i)), "").strip()
            if manual_url:
                manual_provider = infer_provider_from_url(manual_url)
                video_path = download_video_from_url(manual_url, provider_hint=manual_provider)
                video_provider = manual_provider
            else:
                selected_video = search_and_download_video_info(
                    keywords=seg["keywords"],
                    output_path=str(job_dir / f"video_{i:03d}.mp4"),
                    pexels_api_key=PEXELS_API_KEY,
                    pixabay_api_key=PIXABAY_API_KEY,
                    context_text=seg["text"],
                    min_duration=max(3, int(audio_duration)),
                    exclude_urls=used_video_urls,
                )
                video_path = selected_video["path"]
                video_provider = selected_video.get("provider", "manual")

            # Track selected clip to avoid repetition in next segments
            used_video_urls.add(Path(video_path).name)
            used_video_urls.add(Path(video_path).stem)

            composed_segments.append({
                **seg,
                "audio_path": tts_result["audio_path"],
                "video_path": video_path,
                "video_provider": video_provider,
                "audio_duration": audio_duration,
            })

        # 4. Compose final video
        job["progress"] = 85
        job["message"] = "Componiendo video final..."

        output_path = str(OUTPUT_DIR / f"{job_id}.mp4")

        def progress_cb(pct: int, msg: str):
            job["progress"] = pct
            job["message"] = msg

        compose_video(
            composed_segments,
            output_path,
            progress_callback=progress_cb,
            show_subtitles=show_subtitles,
            subtitle_style=subtitle_style,
        )

        job["status"] = "done"
        job["progress"] = 100
        job["message"] = "¡Video generado con éxito!"
        job["output_path"] = output_path

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["message"] = f"Error: {str(e)}"
        import traceback
        traceback.print_exc()
