"""
TTS Module using edge-tts (Microsoft Edge Neural Voices)
No API key required — uses the same engine as Microsoft Edge browser.
"""
import asyncio
import os
import edge_tts
from pathlib import Path


# Available Spanish voices with friendly names
VOICES = {
    "es-MX-DaliaNeural": "Dalia (Mujer · México)",
    "es-MX-JorgeNeural": "Jorge (Hombre · México)",
    "es-ES-ElviraNeural": "Elvira (Mujer · España)",
    "es-ES-AlvaroNeural": "Álvaro (Hombre · España)",
    "es-AR-ElenaNeural": "Elena (Mujer · Argentina)",
    "es-AR-TomasNeural": "Tomás (Hombre · Argentina)",
    "es-CO-SalomeNeural": "Salomé (Mujer · Colombia)",
    "es-CO-GonzaloNeural": "Gonzalo (Hombre · Colombia)",
}

DEFAULT_VOICE = "es-MX-DaliaNeural"


async def generate_audio(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> dict:
    """
    Generate TTS audio from text using edge-tts.
    Returns dict with output_path and word boundaries for subtitle sync.
    """
    output_path = str(output_path)
    # Also generate subtitle timing file
    subtitle_path = output_path.replace('.mp3', '.srt')

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

    # Write SRT subtitle file
    with open(subtitle_path, "w", encoding="utf-8") as srt_file:
        srt_file.write(submaker.generate_subs())

    return {
        "audio_path": output_path,
        "subtitle_path": subtitle_path,
    }


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
    """Return list of available voices with their IDs and display names."""
    return [
        {"id": voice_id, "name": name}
        for voice_id, name in VOICES.items()
    ]
