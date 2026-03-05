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
from pydantic import BaseModel
from dotenv import load_dotenv, dotenv_values

from modules.script_parser import parse_script
from modules.tts import generate_audio_sync, get_available_voices, DEFAULT_VOICE
from modules.video_search import search_and_download_video
from modules.composer import compose_video, get_audio_duration

ENV_FILE = Path("/app/.env") if Path("/app/.env").exists() else Path(".env")
load_dotenv(dotenv_path=ENV_FILE, override=True)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

OUTPUT_DIR = Path("output")
CACHE_DIR = Path("backend/cache")
TEMP_DIR = Path("backend/cache/temp")

for d in [OUTPUT_DIR, CACHE_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="VideoGen API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


class GenerateResponse(BaseModel):
    job_id: str
    segments: list
    message: str


class SetupRequest(BaseModel):
    pexels_api_key: str
    elevenlabs_api_key: str
    deepgram_api_key: str

class VoicePreviewRequest(BaseModel):
    text: str
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "configured": bool(PEXELS_API_KEY and (ELEVENLABS_API_KEY or DEEPGRAM_API_KEY)),
        "pexels_configured": bool(PEXELS_API_KEY),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "deepgram_configured": bool(DEEPGRAM_API_KEY),
    }


@app.get("/api/config")
def get_config():
    """Return current configuration (keys are masked for security)."""
    return {
        "configured": bool(PEXELS_API_KEY and (ELEVENLABS_API_KEY or DEEPGRAM_API_KEY)),
        "pexels_key_preview": f"...{PEXELS_API_KEY[-4:]}" if PEXELS_API_KEY else "",
        "elevenlabs_key_preview": f"...{ELEVENLABS_API_KEY[-4:]}" if ELEVENLABS_API_KEY else "",
        "deepgram_key_preview": f"...{DEEPGRAM_API_KEY[-4:]}" if DEEPGRAM_API_KEY else ""
    }


@app.post("/api/setup")
def setup(req: SetupRequest):
    """Save configuration to .env file and reload env vars."""
    global PEXELS_API_KEY, ELEVENLABS_API_KEY, DEEPGRAM_API_KEY

    pexels_key = req.pexels_api_key.strip()
    elevenlabs_key = req.elevenlabs_api_key.strip()
    deepgram_key = req.deepgram_api_key.strip()

    if not pexels_key:
        raise HTTPException(status_code=400, detail="La API key de Pexels no puede estar vacía")
    
    if not elevenlabs_key and not deepgram_key:
        # At least one premium TTS or Pexels for fallback is good, but let's just make Pexels strict
        pass

    # Validate keys look reasonable
    if len(pexels_key) < 20:
        raise HTTPException(status_code=400, detail="La API key de Pexels parece inválida (muy corta)")

    # Write to .env file
    _write_env({
        "PEXELS_API_KEY": pexels_key, 
        "ELEVENLABS_API_KEY": elevenlabs_key,
        "DEEPGRAM_API_KEY": deepgram_key
    })

    # Reload in-process
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

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
    if not PEXELS_API_KEY:
        raise HTTPException(status_code=500, detail="PEXELS_API_KEY not configured")

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
    )

    return GenerateResponse(
        job_id=job_id,
        segments=segments,
        message=f"Job iniciado con {len(segments)} segmento(s)"
    )


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

def run_generation(job_id: str, segments: list, voice: str, rate: str, pitch: str):
    """Background task: TTS + video search + composition."""
    job = jobs[job_id]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        job["status"] = "running"
        total = len(segments)
        composed_segments = []

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
            video_path = search_and_download_video(
                keywords=seg["keywords"],
                output_path=str(job_dir / f"video_{i:03d}.mp4"),
                pexels_api_key=PEXELS_API_KEY,
                min_duration=max(3, int(audio_duration)),
            )

            composed_segments.append({
                **seg,
                "audio_path": tts_result["audio_path"],
                "video_path": video_path,
                "audio_duration": audio_duration,
            })

        # 4. Compose final video
        job["progress"] = 85
        job["message"] = "Componiendo video final..."

        output_path = str(OUTPUT_DIR / f"{job_id}.mp4")

        def progress_cb(pct: int, msg: str):
            job["progress"] = pct
            job["message"] = msg

        compose_video(composed_segments, output_path, progress_callback=progress_cb)

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
