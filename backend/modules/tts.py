"""
TTS Module — edge-tts with gTTS fallback
- Tries edge-tts first (Microsoft neural voices, best quality)
- Falls back to gTTS (Google TTS) if edge-tts fails (e.g. VPS 403 block)
Both require zero API keys.
"""
import asyncio
import os
import tempfile
import edge_tts
from gtts import gTTS
from pathlib import Path


# Available Spanish voices (edge-tts IDs)
VOICES = {
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

# Map edge-tts voice → gTTS lang/tld for fallback
GTTS_LANG_MAP = {
    "es-MX": ("es", "com.mx"),
    "es-ES": ("es", "es"),
    "es-AR": ("es", "com.ar"),
    "es-CO": ("es", "com.co"),
}


async def _edge_tts_generate(text: str, output_path: str, voice: str, rate: str, pitch: str) -> dict:
    """Try generating audio with edge-tts."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    submaker = edge_tts.SubMaker()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.create_sub(
                    (chunk["offset"], chunk["duration"]),
                    chunk["text"]
                )

    subtitle_path = output_path.replace('.mp3', '.srt')
    with open(subtitle_path, "w", encoding="utf-8") as srt_file:
        srt_file.write(submaker.generate_subs())

    return {"audio_path": output_path, "subtitle_path": subtitle_path, "engine": "edge-tts"}


def _gtts_generate(text: str, output_path: str, voice: str) -> dict:
    """Fallback: generate audio with gTTS (Google TTS)."""
    # Determine language and TLD from voice prefix
    prefix = voice[:5]  # e.g. "es-MX"
    lang, tld = GTTS_LANG_MAP.get(prefix, ("es", "com"))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
    tts.save(output_path)

    # Create empty SRT (gTTS doesn't provide word boundaries)
    subtitle_path = output_path.replace('.mp3', '.srt')
    with open(subtitle_path, "w", encoding="utf-8") as srt_file:
        srt_file.write("")

    return {"audio_path": output_path, "subtitle_path": subtitle_path, "engine": "gtts"}


async def generate_audio(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> dict:
    """
    Generate TTS audio. Tries edge-tts first, falls back to gTTS on failure.
    Returns dict with audio_path, subtitle_path, and engine used.
    """
    try:
        print(f"[TTS] Trying edge-tts for segment...")
        result = await _edge_tts_generate(text, output_path, voice, rate, pitch)
        print(f"[TTS] edge-tts succeeded ✓")
        return result
    except Exception as e:
        print(f"[TTS] edge-tts failed ({e}), falling back to gTTS...")
        result = _gtts_generate(text, output_path, voice)
        print(f"[TTS] gTTS succeeded ✓")
        return result


def generate_audio_sync(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> dict:
    """Synchronous wrapper for generate_audio."""
    return asyncio.run(generate_audio(text, output_path, voice, rate, pitch))


def get_available_voices() -> list:
    return [
        {"id": voice_id, "name": name}
        for voice_id, name in VOICES.items()
    ]
