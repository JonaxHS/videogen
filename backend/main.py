"""
VideoGen Backend — FastAPI Main
Handles script parsing, TTS generation, video search, and composition.
"""
import os
import uuid
import asyncio
import threading
import time
import requests
import shutil
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
from modules import video_search as video_search_module
from modules import script_analyzer
from modules.video_search import (
    search_and_download_video,
    search_and_download_video_info,
    search_and_download_video_info_intelligent,
    search_video_options,
    search_video_options_intelligent,
    download_video_from_url,
    infer_provider_from_url,
)
from modules.composer import compose_video, get_audio_duration, generate_attribution_text

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
MAX_CACHE_SIZE_MB = int(os.getenv("MAX_CACHE_SIZE_MB", "800"))
MAX_FILE_AGE_DAYS = int(os.getenv("MAX_FILE_AGE_DAYS", "1"))
MAX_FILE_AGE_HOURS = int(os.getenv("MAX_FILE_AGE_HOURS", "12"))
CACHE_CLEANUP_INTERVAL_SECONDS = int(os.getenv("CACHE_CLEANUP_INTERVAL_SECONDS", "30"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.22"))
MIN_RELEVANCE_SCORE_GLOBAL = float(os.getenv("MIN_RELEVANCE_SCORE_GLOBAL", "0.16"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_SCRIPT_MODEL = os.getenv("OLLAMA_SCRIPT_MODEL", "qwen2.5:7b-instruct")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

OUTPUT_DIR = Path("/app/output")
CACHE_DIR = Path("/app/cache")
TEMP_DIR = Path("/app/cache/temp")
JOB_RETENTION_SECONDS = max(10, int(os.getenv("JOB_RETENTION_SECONDS", "120")))

for d in [OUTPUT_DIR, CACHE_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def _cleanup_temp_workspace(active_job_id: Optional[str] = None) -> Dict[str, int]:
    """Cleanup stale temp files/folders under /app/cache/temp.

    Why this exists:
    - If the process is killed by OOM (signal 9), `finally` blocks may not run.
    - Stale per-job folders can accumulate quickly and consume tens of GB.
    """
    temp_max_age_hours = int(os.getenv("TEMP_JOB_MAX_AGE_HOURS", "6"))
    temp_max_size_gb = float(os.getenv("TEMP_DIR_MAX_SIZE_GB", "10"))

    removed_dirs = 0
    removed_files = 0
    reclaimed_bytes = 0

    if not TEMP_DIR.exists():
        return {
            "removed_dirs": removed_dirs,
            "removed_files": removed_files,
            "reclaimed_mb": 0,
        }

    import time as _time
    cutoff_ts = _time.time() - (max(1, temp_max_age_hours) * 3600)

    # Pass 1: delete stale entries (except active job dir)
    for child in TEMP_DIR.iterdir():
        if active_job_id and child.name == active_job_id:
            continue
        try:
            stat = child.stat()
            if stat.st_mtime >= cutoff_ts:
                continue
            entry_size = 0
            if child.is_dir():
                for p in child.rglob("*"):
                    try:
                        if p.is_file():
                            entry_size += p.stat().st_size
                    except Exception:
                        continue
                shutil.rmtree(child, ignore_errors=True)
                removed_dirs += 1
            else:
                entry_size = stat.st_size
                child.unlink(missing_ok=True)
                removed_files += 1
            reclaimed_bytes += entry_size
        except Exception:
            continue

    # Pass 2: if still too large, remove oldest entries first (except active)
    max_bytes = int(max(1.0, temp_max_size_gb) * 1024 * 1024 * 1024)
    current_bytes = 0
    entries = []
    for child in TEMP_DIR.iterdir():
        if active_job_id and child.name == active_job_id:
            continue
        try:
            if child.is_dir():
                size = 0
                for p in child.rglob("*"):
                    try:
                        if p.is_file():
                            size += p.stat().st_size
                    except Exception:
                        continue
            else:
                size = child.stat().st_size
            current_bytes += size
            entries.append((child, size, child.stat().st_mtime))
        except Exception:
            continue

    if current_bytes > max_bytes:
        entries.sort(key=lambda item: item[2])
        for child, size, _ in entries:
            if current_bytes <= max_bytes:
                break
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                    removed_dirs += 1
                else:
                    child.unlink(missing_ok=True)
                    removed_files += 1
                reclaimed_bytes += size
                current_bytes -= size
            except Exception:
                continue

    reclaimed_mb = int(reclaimed_bytes / (1024 * 1024))
    if removed_dirs or removed_files:
        print(
            f"[TempCleanup] removed_dirs={removed_dirs}, removed_files={removed_files}, reclaimed={reclaimed_mb}MB",
            flush=True,
        )

    return {
        "removed_dirs": removed_dirs,
        "removed_files": removed_files,
        "reclaimed_mb": reclaimed_mb,
    }


# Startup sweep: remove stale temp workspace left by previous crashed runs.
try:
    _cleanup_temp_workspace(active_job_id=None)
except Exception as startup_cleanup_err:
    print(f"[TempCleanup] Startup sweep failed: {startup_cleanup_err}", flush=True)

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


def _expire_job_artifacts(job_id: str) -> None:
    """Delete finished job output and remove job metadata after retention window."""
    job = jobs.get(job_id)
    if not job:
        return

    # Only expire completed jobs; keep queued/running/error for troubleshooting.
    if job.get("status") != "done":
        return

    output_path = job.get("output_path")
    try:
        if output_path and Path(output_path).exists():
            Path(output_path).unlink(missing_ok=True)
    except Exception as cleanup_err:
        print(f"[JobExpiry] Could not delete output for {job_id}: {cleanup_err}", flush=True)

    jobs.pop(job_id, None)
    print(f"[JobExpiry] Expired job {job_id} and removed artifacts", flush=True)


def _schedule_job_expiry(job_id: str) -> None:
    """Schedule automatic cleanup for a completed job."""
    timer = threading.Timer(JOB_RETENTION_SECONDS, _expire_job_artifacts, args=(job_id,))
    timer.daemon = True
    timer.start()

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


class PreviewRequest(BaseModel):
    script: str
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


class CacheSettingsRequest(BaseModel):
    max_cache_size_mb: int = 800
    max_file_age_days: int = 1
    max_file_age_hours: int = 12
    cleanup_interval_seconds: int = 30
    min_relevance_score: float = 0.22
    min_relevance_score_global: float = 0.16
    job_retention_seconds: int = 120


class ParseRequest(BaseModel):
    script: str


class ScriptGenerationRequest(BaseModel):
    topic: str
    tone: str = "educativo viral"
    duration_seconds: int = 60
    language: str = "es"


class VideoOptionsRequest(BaseModel):
    keywords: str
    context_text: str = ""
    min_duration: int = 5
    limit: int = 8
    global_search: bool = False
    prefer_nasa: bool = False
    page: int = 1
    exclude_urls: list[str] = Field(default_factory=list)
    include_providers: list[str] = Field(default_factory=list)
    search_seed: str = ""


class VideoOptionsIntelligentRequest(BaseModel):
    """Request for intelligent video search using script analysis"""
    keywords: str
    context_text: str = ""
    script_text: str = ""  # Full script for intelligent theme analysis
    min_duration: int = 5
    limit: int = 8
    page: int = 1
    exclude_urls: list[str] = Field(default_factory=list)
    search_seed: str = ""


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


@app.get("/api/cache-settings")
def get_cache_settings():
    return {
        "max_cache_size_mb": MAX_CACHE_SIZE_MB,
        "max_file_age_days": MAX_FILE_AGE_DAYS,
        "max_file_age_hours": MAX_FILE_AGE_HOURS,
        "cleanup_interval_seconds": CACHE_CLEANUP_INTERVAL_SECONDS,
        "min_relevance_score": MIN_RELEVANCE_SCORE,
        "min_relevance_score_global": MIN_RELEVANCE_SCORE_GLOBAL,
        "job_retention_seconds": JOB_RETENTION_SECONDS,
    }


@app.post("/api/cache-settings")
def save_cache_settings(req: CacheSettingsRequest):
    max_cache_size_mb = max(200, int(req.max_cache_size_mb))
    max_file_age_days = max(0, int(req.max_file_age_days))
    max_file_age_hours = max(0, int(req.max_file_age_hours))
    cleanup_interval_seconds = max(10, int(req.cleanup_interval_seconds))
    min_relevance_score = min(1.0, max(0.0, float(req.min_relevance_score)))
    min_relevance_score_global = min(1.0, max(0.0, float(req.min_relevance_score_global)))
    job_retention_seconds = max(10, int(req.job_retention_seconds))

    if max_file_age_days == 0 and max_file_age_hours == 0:
        raise HTTPException(status_code=400, detail="Debes definir antigüedad por días u horas")

    _write_env({
        "MAX_CACHE_SIZE_MB": str(max_cache_size_mb),
        "MAX_FILE_AGE_DAYS": str(max_file_age_days),
        "MAX_FILE_AGE_HOURS": str(max_file_age_hours),
        "CACHE_CLEANUP_INTERVAL_SECONDS": str(cleanup_interval_seconds),
        "MIN_RELEVANCE_SCORE": str(min_relevance_score),
        "MIN_RELEVANCE_SCORE_GLOBAL": str(min_relevance_score_global),
        "JOB_RETENTION_SECONDS": str(job_retention_seconds),
    })
    _reload_env_globals()
    _apply_cache_settings_to_video_search(force_cleanup=True)

    return {
        "success": True,
        "message": "Parámetros de limpieza automática guardados",
        "settings": {
            "max_cache_size_mb": MAX_CACHE_SIZE_MB,
            "max_file_age_days": MAX_FILE_AGE_DAYS,
            "max_file_age_hours": MAX_FILE_AGE_HOURS,
            "cleanup_interval_seconds": CACHE_CLEANUP_INTERVAL_SECONDS,
            "min_relevance_score": MIN_RELEVANCE_SCORE,
            "min_relevance_score_global": MIN_RELEVANCE_SCORE_GLOBAL,
            "job_retention_seconds": JOB_RETENTION_SECONDS,
        },
    }


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except Exception:
            continue
    return total


def _bytes_to_human(num_bytes: int) -> str:
    value = float(max(0, int(num_bytes)))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    return f"{value:.1f}{units[idx]}"


@app.get("/api/storage-stats")
def storage_stats():
    cache_videos_dir = CACHE_DIR / "videos"
    cache_temp_dir = CACHE_DIR / "temp"

    output_bytes = _dir_size_bytes(OUTPUT_DIR)
    cache_total_bytes = _dir_size_bytes(CACHE_DIR)
    cache_videos_bytes = _dir_size_bytes(cache_videos_dir)
    cache_temp_bytes = _dir_size_bytes(cache_temp_dir)

    folders = [
        {
            "key": "output",
            "path": str(OUTPUT_DIR),
            "bytes": output_bytes,
            "human": _bytes_to_human(output_bytes),
        },
        {
            "key": "cache_total",
            "path": str(CACHE_DIR),
            "bytes": cache_total_bytes,
            "human": _bytes_to_human(cache_total_bytes),
        },
        {
            "key": "cache_videos",
            "path": str(cache_videos_dir),
            "bytes": cache_videos_bytes,
            "human": _bytes_to_human(cache_videos_bytes),
        },
        {
            "key": "cache_temp",
            "path": str(cache_temp_dir),
            "bytes": cache_temp_bytes,
            "human": _bytes_to_human(cache_temp_bytes),
        },
    ]

    folders.sort(key=lambda item: item["bytes"], reverse=True)
    return {"folders": folders}


@app.post("/api/temp-purge")
def purge_temp_workspace():
    active_jobs = [j for j in jobs.values() if j.get("status") in {"queued", "running"}]
    if active_jobs:
        raise HTTPException(
            status_code=409,
            detail="Hay una generación en curso. Espera a que termine para borrar todo cache/temp.",
        )

    before_bytes = _dir_size_bytes(TEMP_DIR)
    removed_dirs = 0
    removed_files = 0

    if TEMP_DIR.exists():
        for child in TEMP_DIR.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                    removed_dirs += 1
                else:
                    child.unlink(missing_ok=True)
                    removed_files += 1
            except Exception:
                continue

    after_bytes = _dir_size_bytes(TEMP_DIR)
    freed_bytes = max(0, before_bytes - after_bytes)

    return {
        "success": True,
        "message": "Se borró por completo cache/temp",
        "removed_dirs": removed_dirs,
        "removed_files": removed_files,
        "before": _bytes_to_human(before_bytes),
        "after": _bytes_to_human(after_bytes),
        "freed": _bytes_to_human(freed_bytes),
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


def _apply_cache_settings_to_video_search(force_cleanup: bool = False):
    video_search_module.MAX_CACHE_SIZE_MB = MAX_CACHE_SIZE_MB
    video_search_module.MAX_FILE_AGE_DAYS = MAX_FILE_AGE_DAYS
    video_search_module.MAX_FILE_AGE_HOURS = MAX_FILE_AGE_HOURS
    video_search_module.CACHE_CLEANUP_INTERVAL_SECONDS = CACHE_CLEANUP_INTERVAL_SECONDS
    video_search_module.MIN_RELEVANCE_SCORE = MIN_RELEVANCE_SCORE
    video_search_module.MIN_RELEVANCE_SCORE_GLOBAL = MIN_RELEVANCE_SCORE_GLOBAL
    if force_cleanup:
        try:
            video_search_module._cleanup_cache_if_needed(force=True)
        except Exception:
            pass


def _reload_env_globals():
    global PEXELS_API_KEY, PIXABAY_API_KEY, ELEVENLABS_API_KEY, DEEPGRAM_API_KEY, TELEGRAM_BOT_TOKEN
    global TELEGRAM_DEFAULT_VOICE, TELEGRAM_DEFAULT_RATE, TELEGRAM_DEFAULT_PITCH
    global TELEGRAM_DEFAULT_SHOW_SUBTITLES, TELEGRAM_DEFAULT_SUBTITLE_STYLE
    global JOB_RETENTION_SECONDS
    global MAX_CACHE_SIZE_MB, MAX_FILE_AGE_DAYS, MAX_FILE_AGE_HOURS, CACHE_CLEANUP_INTERVAL_SECONDS
    global MIN_RELEVANCE_SCORE, MIN_RELEVANCE_SCORE_GLOBAL

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
    MAX_CACHE_SIZE_MB = int(os.getenv("MAX_CACHE_SIZE_MB", "800"))
    MAX_FILE_AGE_DAYS = int(os.getenv("MAX_FILE_AGE_DAYS", "1"))
    MAX_FILE_AGE_HOURS = int(os.getenv("MAX_FILE_AGE_HOURS", "12"))
    CACHE_CLEANUP_INTERVAL_SECONDS = int(os.getenv("CACHE_CLEANUP_INTERVAL_SECONDS", "30"))
    MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.22"))
    MIN_RELEVANCE_SCORE_GLOBAL = float(os.getenv("MIN_RELEVANCE_SCORE_GLOBAL", "0.16"))
    JOB_RETENTION_SECONDS = max(10, int(os.getenv("JOB_RETENTION_SECONDS", "120")))
    _apply_cache_settings_to_video_search(force_cleanup=False)


@app.post("/api/cleanup")
def cleanup_cache():
    """Clean up old cache files."""
    try:
        from modules.video_search import _cleanup_old_files, _cleanup_cache_if_needed, CACHE_DIR

        active_jobs = [j for j in jobs.values() if j.get("status") in {"queued", "running"}]
        if active_jobs:
            raise HTTPException(
                status_code=409,
                detail="Hay una generación en curso. Intenta limpiar cache cuando termine para evitar borrar archivos en uso.",
            )
        
        # Get cache size before
        cache_size_before = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file()) / (1024*1024) if CACHE_DIR.exists() else 0
        temp_size_before = sum(f.stat().st_size for f in TEMP_DIR.rglob("*") if f.is_file()) / (1024*1024) if TEMP_DIR.exists() else 0
        
        # Clean up old files using configured target
        target_mb = max(200, float(MAX_CACHE_SIZE_MB) * 0.8)
        protect_recent_seconds = int(os.getenv("PROTECT_RECENT_CACHE_SECONDS", "1800"))
        _cleanup_old_files(target_mb=target_mb, protect_recent_seconds=protect_recent_seconds)
        _cleanup_cache_if_needed(force=True)

        # Also cleanup stale temp job folders (cache/temp/*) older than configured threshold
        temp_max_age_hours = int(os.getenv("TEMP_JOB_MAX_AGE_HOURS", "6"))
        temp_cutoff_ts = (Path(".").stat().st_mtime)  # fallback init
        try:
            import time as _time
            temp_cutoff_ts = _time.time() - (temp_max_age_hours * 3600)
        except Exception:
            pass

        removed_temp_dirs = 0
        if TEMP_DIR.exists():
            for child in TEMP_DIR.iterdir():
                if not child.is_dir():
                    continue
                try:
                    if child.stat().st_mtime < temp_cutoff_ts:
                        shutil.rmtree(child, ignore_errors=True)
                        removed_temp_dirs += 1
                except Exception:
                    continue
        
        # Get cache size after
        cache_size_after = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file()) / (1024*1024) if CACHE_DIR.exists() else 0
        temp_size_after = sum(f.stat().st_size for f in TEMP_DIR.rglob("*") if f.is_file()) / (1024*1024) if TEMP_DIR.exists() else 0
        freed_mb = cache_size_before - cache_size_after
        freed_temp_mb = temp_size_before - temp_size_after
        
        return {
            "success": True,
            "message": f"Limpieza completada. Cache liberado: {freed_mb:.1f}MB, Temp liberado: {freed_temp_mb:.1f}MB",
            "cache_size_before": f"{cache_size_before:.1f}MB",
            "cache_size_after": f"{cache_size_after:.1f}MB",
            "temp_size_before": f"{temp_size_before:.1f}MB",
            "temp_size_after": f"{temp_size_after:.1f}MB",
            "temp_dirs_removed": removed_temp_dirs,
            "freed": f"{freed_mb + freed_temp_mb:.1f}MB"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during cleanup: {str(e)}")


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
        "retention_seconds": JOB_RETENTION_SECONDS,
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
        script_text=req.script,
    )

    return GenerateResponse(
        job_id=job_id,
        segments=segments,
        message=f"Job iniciado con {len(segments)} segmento(s)"
    )


@app.post("/api/generate-preview", response_model=GenerateResponse)
def generate_preview(req: PreviewRequest, background_tasks: BackgroundTasks):
    """Generate a full reel preview without TTS (video-only timeline)."""
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="Script cannot be empty")

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
        "preview_only": True,
        "retention_seconds": JOB_RETENTION_SECONDS,
    }

    background_tasks.add_task(
        run_generation,
        job_id=job_id,
        segments=segments,
        voice=DEFAULT_VOICE,
        rate="+0%",
        pitch="+0Hz",
        show_subtitles=req.show_subtitles,
        subtitle_style=req.subtitle_style,
        selected_videos=req.selected_videos,
        preview_only=True,
        script_text=req.script,
    )

    return GenerateResponse(
        job_id=job_id,
        segments=segments,
        message=f"Previsualización iniciada con {len(segments)} segmento(s)"
    )


@app.post("/api/parse")
def parse(req: ParseRequest):
    if not req.script.strip():
        return {"segments": []}
    segments = parse_script(req.script)
    return {"segments": segments}


@app.post("/api/generate-script")
def generate_script(req: ScriptGenerationRequest):
    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="El tema no puede estar vacío")

    duration_seconds = max(15, min(180, int(req.duration_seconds or 60)))
    tone = (req.tone or "educativo viral").strip()
    language = (req.language or "es").strip().lower()

    script_text = _generate_script_with_ollama(
        topic=topic,
        tone=tone,
        duration_seconds=duration_seconds,
        language=language,
    )

    return {
        "script": script_text,
        "model": OLLAMA_SCRIPT_MODEL,
        "duration_seconds": duration_seconds,
        "tone": tone,
    }


@app.post("/api/generate-detailed-reel")
def generate_detailed_reel(req: ScriptGenerationRequest):
    """
    Generate a complete reel with title, description, script, visuals, hashtags, etc.
    Uses advanced prompt engineering to get structured output from Qwen.
    """
    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="El tema no puede estar vacío")

    duration_seconds = max(15, min(180, int(req.duration_seconds or 60)))
    tone = (req.tone or "educativo viral").strip()
    language = (req.language or "es").strip().lower()
    reel_number = int(req.reel_number or 1) if hasattr(req, 'reel_number') else 1

    try:
        reel_data = _generate_detailed_reel_with_ollama(
            topic=topic,
            tone=tone,
            duration_seconds=duration_seconds,
            language=language,
            reel_number=reel_number
        )
        
        return {
            "reel": reel_data,
            "model": OLLAMA_SCRIPT_MODEL,
            "duration_seconds": duration_seconds,
            "tone": tone,
            "status": "success"
        }
    except Exception as e:
        print(f"[DetailedReel] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error al generar reel: {str(e)}")


def _generate_script_with_ollama(topic: str, tone: str, duration_seconds: int, language: str = "es") -> str:
    target_words = max(60, int((duration_seconds / 60) * 150))

    if language.startswith("es"):
        language_hint = "Escribe en español neutro."
    else:
        language_hint = "Write in the requested language."

    prompt = (
        f"Genera un guion corto para reel sobre: {topic}.\n"
        f"Tono: {tone}.\n"
        f"Duración objetivo: {duration_seconds} segundos (~{target_words} palabras).\n"
        f"{language_hint}\n"
        "Formato obligatorio:\n"
        "- Solo entrega el guion final, sin explicaciones.\n"
        "- Divide en párrafos cortos (1-2 frases por párrafo).\n"
        "- Mantén ritmo dinámico y claro.\n"
        "- Incluye cierre fuerte o reflexión final.\n"
    )

    chat_payload = {
        "model": OLLAMA_SCRIPT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Eres un guionista experto en contenido corto para redes sociales.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0.8,
            "top_p": 0.9,
        },
    }

    generate_payload = {
        "model": OLLAMA_SCRIPT_MODEL,
        "prompt": (
            "Eres un guionista experto en contenido corto para redes sociales.\n\n"
            f"{prompt}"
        ),
        "stream": False,
        "options": {
            "temperature": 0.8,
            "top_p": 0.9,
        },
    }

    response = requests.post(f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat", json=chat_payload, timeout=12)
    if response.status_code == 404:
        response = requests.post(f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate", json=generate_payload, timeout=12)

    response.raise_for_status()
    payload = response.json() or {}
    message_text = ((payload.get("message") or {}).get("content") or "").strip()
    if message_text:
        return message_text
    return str(payload.get("response", "")).strip()


def _generate_detailed_reel_with_ollama(
    topic: str,
    tone: str,
    duration_seconds: int,
    language: str = "es",
    reel_number: int = 1
) -> dict:
    """
    Generate a detailed reel with title, description, hashtags, script, visuals, etc.
    
    Returns dict with:
    {
        "title": "...",
        "description": "...",
        "script": "...",
        "hashtags": "...",
        "word_count": 0,
        "estimated_duration": "90-95 segundos",
        "tone": "revelador, visual",
        "recommended_voice": "Antoni o Serena",
        "music_suggestion": "...",
        "visual_suggestions": [...],
        "suggested_comment": "...",
        "key_fact": "..."
    }
    """
    
    target_words = max(100, int((duration_seconds / 60) * 150))
    
    if language.startswith("es"):
        language_hint = "Escribe en español neutro y evocador."
    else:
        language_hint = "Write in the requested language with narrative style."
    
    # Prompt avanzado que pide formato complejo
    detailed_prompt = f"""
Eres un guionista experto en reels de divulgación científica para Instagram/TikTok.

TAREA: Genera el REEL #{reel_number} completo con todos estos elementos:

**TEMA:** {topic}
**TONO:** {tone}
**DURACIÓN:** {duration_seconds} segundos (~{target_words} palabras)
**IDIOMA:** {language_hint}

FORMATO EXACTO REQUERIDO (usa estos encabezados):

### 🌌 Título:
[Título atractivo, máximo 10 palabras]

### 📝 Descripción:
[2-3 párrafos que expliquen el tema en forma cautivadora. Incluir contexto histórico o dato impactante]

### Hashtags:
[Lista de 5-8 hashtags relevantes]

### 📜 Guion Fluido:
[Guion con líneas cortas (poético), cada idea en una línea nueva. 
- Ritmo dinámico
- Empieza con analogía cotidiana
- Incluye datos científicos
- Termina con reflexión profunda
- Sin tiempo de lectura >90s en voz natural]

### Métricas:
- Palabras totales: [número]
- Duración estimada: [X-Y segundos]
- Tono narrativo: [adjetivos]
- Voces recomendadas: [opciones españolas]
- Música sugerida: [descripción corta]

### 🎥 Sugerencias Visuales (tabla):
| Momento | Escena sugerida | Nota |
|---------|-----------------|------|
| [Inicio] | [descripción] | [pista] |
| [Medio] | [descripción] | [pista] |
| [Final] | [descripción] | [pista] |

### 💬 Comentario sugerido:
[Un párrafo que invite a comentar. Incluye un dato de impacto al final]

### 🚀 Dato clave:
[Un dato científico, fórmula, o información fascinante relacionada]

IMPORTANTE:
- Usa emojis estratégicos (máximo 3-5)
- Mantén un equilibrio entre ciencia y narrativa
- El guion debe ser memorerable y compartible
- Asegúrate que cada línea sea clara en voz alta
"""
    
    chat_payload = {
        "model": OLLAMA_SCRIPT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Eres un creador de contenido viral de divulgación científica. Especializándote en reels que educan y cautivan. Dominas la estructura narrativa, datos científicos precisos, y humor. Tus reels son compartidos por millones en redes sociales.",
            },
            {
                "role": "user",
                "content": detailed_prompt,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0.85,
            "top_p": 0.95,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json=chat_payload,
            timeout=30  # Longer timeout for complex generation
        )
        response.raise_for_status()
        body = response.json() or {}
        full_text = ((body.get("message") or {}).get("content") or "").strip()
        
        if full_text:
            # Parse the structured response
            return _parse_detailed_reel(full_text)
        else:
            return {"error": "Empty response from Qwen"}
            
    except Exception as e:
        print(f"[DetailedReel] Qwen generation failed: {e}, using fallback basic script")
        # Fallback: generate simple script
        simple_script = _generate_script_with_ollama(topic, tone, duration_seconds, language)
        return {
            "title": topic[:60],
            "script": simple_script,
            "error": f"Detailed generation failed: {str(e)}"
        }


def _parse_detailed_reel(text: str) -> dict:
    """
    Parse structured reel output from Qwen into dict.
    Extracts sections between ### headers.
    """
    result = {}
    
    # Extract title
    if "### 🌌 Título:" in text:
        title_section = text.split("### 🌌 Título:")[1].split("###")[0].strip()
        result["title"] = title_section[:100]
    
    # Extract description
    if "### 📝 Descripción:" in text:
        desc_section = text.split("### 📝 Descripción:")[1].split("###")[0].strip()
        result["description"] = desc_section[:500]
    
    # Extract hashtags
    if "### Hashtags:" in text:
        hashtags_section = text.split("### Hashtags:")[1].split("###")[0].strip()
        result["hashtags"] = hashtags_section
    
    # Extract script
    if "### 📜 Guion Fluido:" in text:
        script_section = text.split("### 📜 Guion Fluido:")[1].split("###")[0].strip()
        result["script"] = script_section
    
    # Extract metrics
    if "### Métricas:" in text:
        metrics_section = text.split("### Métricas:")[1].split("###")[0].strip()
        result["metrics"] = metrics_section
    
    # Extract visuals
    if "### 🎥 Sugerencias Visuales" in text:
        visuals_section = text.split("### 🎥 Sugerencias Visuales")[1].split("###")[0].strip()
        result["visual_suggestions"] = visuals_section
    
    # Extract comment
    if "### 💬 Comentario sugerido:" in text:
        comment_section = text.split("### 💬 Comentario sugerido:")[1].split("###")[0].strip()
        result["suggested_comment"] = comment_section
    
    # Extract key fact
    if "### 🚀 Dato clave:" in text:
        fact_section = text.split("### 🚀 Dato clave:")[1].strip()
        result["key_fact"] = fact_section[:300]
    
    return result

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json=chat_payload,
            timeout=180,
        )
        if response.status_code == 404:
            response = requests.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                json=generate_payload,
                timeout=180,
            )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo generar guion con Qwen local. "
                f"Verifica Ollama ({OLLAMA_BASE_URL}) y el modelo ({OLLAMA_SCRIPT_MODEL}). Error: {e}"
            ),
        )

    text = (((data.get("message") or {}).get("content")) or data.get("response") or "").strip()
    if not text:
        raise HTTPException(status_code=500, detail="El modelo devolvió una respuesta vacía")
    return text


@app.post("/api/video-options")
def video_options(req: VideoOptionsRequest):
    options = search_video_options(
        keywords=req.keywords,
        pexels_api_key=PEXELS_API_KEY,
        pixabay_api_key=PIXABAY_API_KEY,
        context_text=req.context_text,
        min_duration=max(3, int(req.min_duration)),
        limit=max(1, min(50, int(req.limit))),
        global_search=bool(req.global_search),
        prefer_nasa=bool(req.prefer_nasa),
        page=max(1, int(req.page)),
        exclude_urls=set(req.exclude_urls or []),
        include_providers=set(req.include_providers or []),
        search_seed=(req.search_seed or "").strip(),
    )
    return {"options": options}


@app.post("/api/video-options-intelligent")
def video_options_intelligent(req: VideoOptionsIntelligentRequest):
    """
    Intelligent video search for science/astronomy scripts.
    Uses script analysis to generate contextually relevant multi-keyword searches
    and intelligently prioritize providers (NASA/ESA for science content).
    """
    options = search_video_options_intelligent(
        keywords=req.keywords,
        pexels_api_key=PEXELS_API_KEY,
        pixabay_api_key=PIXABAY_API_KEY,
        context_text=req.context_text,
        script_text=req.script_text,
        min_duration=max(3, int(req.min_duration)),
        limit=max(1, min(50, int(req.limit))),
        page=max(1, int(req.page)),
        exclude_urls=set(req.exclude_urls or []),
        search_seed=(req.search_seed or "").strip(),
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

def run_generation(job_id: str, segments: list, voice: str, rate: str, pitch: str, show_subtitles: bool, subtitle_style: str = "classic", selected_videos: Optional[Dict[str, str]] = None, preview_only: bool = False, script_text: str = ""):
    """Background task: TTS + video search + composition."""
    # Pre-flight sweep to keep /app/cache/temp bounded even after crash/OOM leftovers.
    try:
        _cleanup_temp_workspace(active_job_id=job_id)
    except Exception as preflight_cleanup_err:
        print(f"[TempCleanup] Pre-flight sweep failed: {preflight_cleanup_err}", flush=True)

    # Pre-flight sweep for /app/cache/videos size/age policy.
    try:
        _apply_cache_settings_to_video_search(force_cleanup=True)
    except Exception as cache_preflight_err:
        print(f"[CacheCleanup] Pre-flight sweep failed: {cache_preflight_err}", flush=True)

    job = jobs[job_id]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Detect if script is scientific/astronomy-focused for intelligent search
    use_intelligent_search = False
    if script_text:
        try:
            script_analysis = script_analyzer.analyze_script_structure(script_text)
            detected_domains = script_analysis.get("detected_domains", [])
            use_intelligent_search = len(detected_domains) > 0
            print(f"[Generation {job_id}] Script analysis: domains={detected_domains}, intelligent_search={use_intelligent_search}", flush=True)
        except Exception as e:
            print(f"[Generation {job_id}] Script analysis failed: {e}, using standard search", flush=True)

    try:
        def _copy_video_to_job(source_path: str, destination_path: str, source_url: str = "", provider_hint: str = "manual") -> str:
            if source_path == destination_path:
                if not Path(destination_path).exists() and source_url:
                    redownloaded = download_video_from_url(source_url, provider_hint=provider_hint)
                    if redownloaded != destination_path:
                        shutil.copy2(redownloaded, destination_path)
                return destination_path

            try:
                shutil.copy2(source_path, destination_path)
                return destination_path
            except FileNotFoundError:
                if not source_url:
                    raise
                redownloaded = download_video_from_url(source_url, provider_hint=provider_hint)
                if redownloaded != destination_path:
                    shutil.copy2(redownloaded, destination_path)
                return destination_path

        job["status"] = "running"
        total = len(segments)
        composed_segments = []
        used_video_urls: set[str] = set()
        used_providers: list[str] = []  # Track recent providers for diversity

        selected_videos = selected_videos or {}

        for i, seg in enumerate(segments):
            # Update progress
            prog_base = int((i / total) * 80)
            job["progress"] = prog_base
            job["message"] = (
                f"Segmento {i + 1}/{total}: preparando duración de preview..."
                if preview_only
                else f"Segmento {i + 1}/{total}: generando voz..."
            )

            if preview_only:
                audio_duration = max(2.5, float(seg.get("estimated_duration", 5.0) or 5.0))
                audio_file_path = None
            else:
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
                audio_file_path = tts_result["audio_path"]

            # 3. Download stock video
            job["message"] = f"Segmento {i + 1}/{total}: buscando video..."
            manual_url = selected_videos.get(str(seg.get("id", i)), "").strip()
            
            print(f"[DEBUG Segment {i+1}] seg.id = {seg.get('id', 'MISSING')}, using key: {str(seg.get('id', i))}")
            print(f"[DEBUG Segment {i+1}] selected_videos dict: {selected_videos}")
            print(f"[DEBUG Segment {i+1}] manual_url found: {manual_url if manual_url else 'NONE - will auto-search'}")
            
            video_skip_seconds = 0.0
            if manual_url:
                manual_provider = infer_provider_from_url(manual_url)
                source_video_path = download_video_from_url(manual_url, provider_hint=manual_provider)
                video_path = str(job_dir / f"video_{i:03d}.mp4")
                video_path = _copy_video_to_job(
                    source_path=source_video_path,
                    destination_path=video_path,
                    source_url=manual_url,
                    provider_hint=manual_provider,
                )
                video_provider = manual_provider
                selected_video_url = manual_url
            else:
                auto_video_result = search_and_download_video_info_intelligent(
                    keywords=seg["keywords"],
                    output_path=str(job_dir / f"video_{i:03d}.mp4"),
                    pexels_api_key=PEXELS_API_KEY,
                    pixabay_api_key=PIXABAY_API_KEY,
                    context_text=seg["text"],
                    script_text=script_text,
                    min_duration=max(3, int(audio_duration)),
                    exclude_urls=used_video_urls,
                    segment_index=i,
                    used_providers=used_providers,
                    generation_id=job_id,
                ) if use_intelligent_search else search_and_download_video_info(
                    keywords=seg["keywords"],
                    output_path=str(job_dir / f"video_{i:03d}.mp4"),
                    pexels_api_key=PEXELS_API_KEY,
                    pixabay_api_key=PIXABAY_API_KEY,
                    context_text=seg["text"],
                    min_duration=max(3, int(audio_duration)),
                    exclude_urls=used_video_urls,
                    segment_index=i,
                    used_providers=used_providers,
                    generation_id=job_id,
                )
                source_video_path = auto_video_result["path"]
                video_path = str(job_dir / f"video_{i:03d}.mp4")
                video_provider = auto_video_result.get("provider", "manual")
                selected_video_url = auto_video_result.get("url", "")
                video_path = _copy_video_to_job(
                    source_path=source_video_path,
                    destination_path=video_path,
                    source_url=selected_video_url,
                    provider_hint=video_provider,
                )
                video_skip_seconds = float(auto_video_result.get("skip_seconds", 0.0) or 0.0)
                
                # Track provider for diversity in next segments
                used_providers.append(video_provider)
                print(f"[Segment {i+1}] Provider: {video_provider}, Recent: {used_providers[-3:]}")

            # Track selected clip to avoid repetition in next segments
            used_video_urls.add(Path(video_path).name)
            used_video_urls.add(Path(video_path).stem)
            if selected_video_url:
                used_video_urls.add(selected_video_url)

            composed_segments.append({
                **seg,
                "audio_path": audio_file_path,
                "video_path": video_path,
                "video_provider": video_provider,
                "video_source_url": selected_video_url,
                "video_skip_seconds": video_skip_seconds,
                "audio_duration": audio_duration,
            })

        # 4. Compose final video
        job["progress"] = 85
        job["message"] = "Componiendo video final..."

        output_path = str(OUTPUT_DIR / f"{job_id}.mp4")

        def progress_cb(pct: int, msg: str):
            job["progress"] = pct
            job["message"] = msg

        # Compose video with attribution
        output_path, sources_used = compose_video(
            composed_segments,
            output_path,
            progress_callback=progress_cb,
            show_subtitles=show_subtitles,
            subtitle_style=subtitle_style,
            add_attribution=True,  # Always add attribution
        )
        
        # Store sources metadata
        job["sources_used"] = sources_used
        job["attribution"] = generate_attribution_text(sources_used)

        job["status"] = "done"
        job["progress"] = 100
        job["message"] = "¡Previsualización generada!" if preview_only else "¡Video generado con éxito!"
        job["output_path"] = output_path
        job["expires_at"] = int(time.time()) + JOB_RETENTION_SECONDS

        _schedule_job_expiry(job_id)

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["message"] = f"Error: {str(e)}"
        import traceback
        traceback.print_exc()

    finally:
        # Always cleanup per-job temp directory to prevent /app/cache/temp growth.
        try:
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)

            # Keep temp bounded after each generation as well.
            _cleanup_temp_workspace(active_job_id=None)

            # Keep provider video cache bounded after each generation.
            _apply_cache_settings_to_video_search(force_cleanup=True)
        except Exception as cleanup_err:
            print(f"[Cleanup] Could not remove temp dir {job_dir}: {cleanup_err}")
