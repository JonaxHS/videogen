"""
TTS Module
Supports both:
- ElevenLabs API (Premium HQ Audio, requires API key)
- edge-tts / gTTS (Free, no API key required)
"""
import asyncio
import os
import requests
import edge_tts
from gtts import gTTS
from pathlib import Path


# ─── ElevenLabs Voices (Premium) ──────────────────────────────────────────

ELEVENLABS_VOICES = {
    "pNInz6obbfDQGcgMyIGb": "Adam (Hombre · Narrador Épico) ✦",
    "ErXwobaYiN019PkySvjV": "Antoni (Hombre · Casual/Noticias) ✦",
    "EXAVITQu4vr4xnSDxMaL": "Bella (Mujer · Dulce/Relajada) ✦",
    "XrExE9yKIg1WjnnlVkGX": "Matilda (Mujer · Narradora/Cálida) ✦",
    "TxGEqnHWrfWFTfGW9XjX": "Josh (Hombre · Energético/Joven) ✦",
    "VR6AewLTigWG4xSOukaG": "Rachel (Mujer · Calma/Noticias) ✦"
}

# ─── Free Voices (edge-tts / gTTS) ────────────────────────────────────────

FREE_VOICES = {
    "es-MX-DaliaNeural":  "Dalia (Mujer · México)",
    "es-MX-JorgeNeural":  "Jorge (Hombre · México)",
    "es-ES-ElviraNeural": "Elvira (Mujer · España)",
    "es-ES-AlvaroNeural": "Álvaro (Hombre · España)",
    "es-AR-ElenaNeural":  "Elena (Mujer · Argentina)",
    "es-AR-TomasNeural":  "Tomás (Hombre · Argentina)",
    "es-CO-SalomeNeural": "Salomé (Mujer · Colombia)",
    "es-CO-GonzaloNeural":"Gonzalo (Hombre · Colombia)",
}

DEFAULT_VOICE = "es-MX-DaliaNeural"

GTTS_LANG_MAP = {
    "es-MX": ("es", "com.mx"),
    "es-ES": ("es", "es"),
    "es-AR": ("es", "com.ar"),
    "es-CO": ("es", "com.co"),
}


# ─── ElevenLabs Logic ───────────────────────────────────────────────────

def _elevenlabs_generate_sync(text: str, output_path: str, voice_id: str) -> dict:
    """Generate audio and timestamps using ElevenLabs API sync call."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY no está configurada")

    text = text.strip() or "..."

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    headers = {
        "Accept": "application/json",
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }

    response = requests.post(url, json=data, headers=headers)
    if not response.ok:
        raise Exception(f"ElevenLabs API error: {response.text}")
        
    res_json = response.json()
    audio_b64 = res_json.get("audio_base64")
    alignment = res_json.get("alignment")
    
    import base64
    audio_bytes = base64.b64decode(audio_b64)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
        
    subtitle_path = output_path.replace('.mp3', '.srt')
    _generate_srt(alignment, subtitle_path)
    
    return {"audio_path": output_path, "subtitle_path": subtitle_path, "engine": "elevenlabs"}

def _format_srt_time(seconds: float) -> str:
    ms = int((seconds % 1) * 1000)
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _generate_srt(alignment: dict, filepath: str):
    if not alignment or not alignment.get("characters"):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("")
        return

    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    
    words = []
    current_word = ""
    current_start = -1
    
    for i in range(len(chars)):
        char = chars[i]
        if char == " " and not current_word:
            continue
        if current_start == -1:
            current_start = starts[i]
        if char == " ":
            if current_word:
                words.append({"text": current_word, "start": current_start, "end": ends[i-1]})
                current_word = ""
                current_start = -1
        else:
            current_word += char
            
    if current_word:
        words.append({"text": current_word, "start": current_start, "end": ends[-1]})

    srt_content = []
    chunk_idx = 1
    WORDS_PER_CHUNK = 4
    
    for i in range(0, len(words), WORDS_PER_CHUNK):
        chunk_words = words[i:i+WORDS_PER_CHUNK]
        start_time = _format_srt_time(chunk_words[0]["start"])
        end_time = _format_srt_time(chunk_words[-1]["end"])
        text = " ".join([w["text"] for w in chunk_words])
        
        srt_content.append(f"{chunk_idx}")
        srt_content.append(f"{start_time} --> {end_time}")
        srt_content.append(text)
        srt_content.append("")
        chunk_idx += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_content))


# ─── Free Logic (edge-tts / gTTS) ─────────────────────────────────────

async def _edge_tts_generate(text: str, output_path: str, voice: str, rate: str, pitch: str) -> dict:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    submaker = edge_tts.SubMaker()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])
    subtitle_path = output_path.replace('.mp3', '.srt')
    with open(subtitle_path, "w", encoding="utf-8") as srt_file:
        srt_file.write(submaker.generate_subs())
    return {"audio_path": output_path, "subtitle_path": subtitle_path, "engine": "edge-tts"}

def _gtts_generate(text: str, output_path: str, voice: str) -> dict:
    prefix = voice[:5]
    lang, tld = GTTS_LANG_MAP.get(prefix, ("es", "com"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
    tts.save(output_path)
    subtitle_path = output_path.replace('.mp3', '.srt')
    with open(subtitle_path, "w", encoding="utf-8") as srt_file:
        srt_file.write("") # Emptysrt
    return {"audio_path": output_path, "subtitle_path": subtitle_path, "engine": "gtts"}


# ─── Main Interface ───────────────────────────────────────────────────

async def generate_audio(
    text: str, output_path: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz"
) -> dict:
    
    if voice in ELEVENLABS_VOICES:
        print(f"[TTS] Utilizando ElevenLabs (Voz Premium)...")
        return await asyncio.to_thread(_elevenlabs_generate_sync, text, output_path, voice)
    
    # Fallback to free edge-tts / gTTS
    try:
        print(f"[TTS] Utilizando edge-tts (Gratis)...")
        return await _edge_tts_generate(text, output_path, voice, rate, pitch)
    except Exception as e:
        print(f"[TTS] edge-tts falló ({e}), usando gTTS como respaldo...")
        return _gtts_generate(text, output_path, voice)


def generate_audio_sync(
    text: str, output_path: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz"
) -> dict:
    """Synchronous wrapper."""
    return asyncio.run(generate_audio(text, output_path, voice, rate, pitch))


def get_available_voices() -> dict:
    """Devuelve las voces agrupadas entre premium y gratis."""
    eleven = [{"id": k, "name": v} for k, v in ELEVENLABS_VOICES.items()]
    free = [{"id": k, "name": v} for k, v in FREE_VOICES.items()]
    return {
        "elevenlabs": eleven,
        "free": free
    }
