"""
Video Composer Module
Assembles final reel video from segments: clips + TTS audio + subtitles.
Output format: 9:16 vertical (1080x1920) at 30fps.
"""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Callable


# Output video settings
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FPS = 30
OUTPUT_FORMAT = "mp4"

# Subtitle styling
SUBTITLE_FONT_SIZE = 60
SUBTITLE_COLOR = "white"
SUBTITLE_BG_COLOR = "black@0.5"


def compose_video(
    segments: List[Dict],
    output_path: str,
    progress_callback: Callable[[int, str], None] = None,
    show_subtitles: bool = True,
) -> str:
    """
    Compose all segments into a final reel video using FFmpeg.

    Each segment dict must have:
      - video_path: str
      - audio_path: str
      - text: str
      - audio_duration: float (seconds)

    Returns path to the final video file.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    temp_dir = Path(output_path).parent / "temp_segments"
    temp_dir.mkdir(exist_ok=True)

    segment_files = []

    total = len(segments)
    for i, seg in enumerate(segments):
        if progress_callback:
            progress_callback(
                int((i / total) * 80),
                f"Procesando segmento {i + 1} de {total}..."
            )

        seg_path = temp_dir / f"segment_{i:03d}.mp4"
        _compose_segment(
            video_path=seg["video_path"],
            audio_path=seg["audio_path"],
            text=seg["text"],
            audio_duration=seg["audio_duration"],
            output_path=str(seg_path),
            show_subtitles=show_subtitles,
        )
        segment_files.append(str(seg_path))

    if progress_callback:
        progress_callback(85, "Concatenando segmentos...")

    # Concatenate all segment files
    concat_list_path = temp_dir / "concat.txt"
    with open(concat_list_path, "w") as f:
        for sf in segment_files:
            # Use absolute path to ensure FFmpeg finds it reliably regardless of CWD parsing
            f.write(f"file '{Path(sf).resolve().as_posix()}'\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_path),
        "-c", "copy",
        output_path
    ], check=True, capture_output=True)

    if progress_callback:
        progress_callback(100, "¡Video listo!")

    # Cleanup temp files
    for sf in segment_files:
        try:
            os.remove(sf)
        except Exception:
            pass
    try:
        os.remove(str(concat_list_path))
        os.rmdir(str(temp_dir))
    except Exception:
        pass

    return output_path


def _compose_segment(
    video_path: str,
    audio_path: str,
    text: str,
    audio_duration: float,
    output_path: str,
    show_subtitles: bool,
) -> None:
    """
    Compose a single segment:
    1. Crop/scale video to 9:16 (1080x1920)
    2. Trim video to audio duration
    3. Overlay subtitle text at bottom
    4. Mix with TTS audio
    """
    # FFmpeg filter chain:
    # 1. Scale and pad to 9:16 (preserve full content from any orientation)
    # 2. Add subtitle text only if show_subtitles=True
    if show_subtitles:
        safe_text = _escape_ffmpeg_text(text)

        if len(text) > 120:
            words = text.split()
            safe_text = _escape_ffmpeg_text(' '.join(words[:20]) + '...')

        filter_complex = (
            f"[0:v]"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={FPS}"
            f"[scaled];"
            f"[scaled]"
            f"drawtext="
            f"text='{safe_text}':"
            f"fontcolor=white:"
            f"fontsize={SUBTITLE_FONT_SIZE}:"
            f"box=1:"
            f"boxcolor=black@0.55:"
            f"boxborderw=12:"
            f"x=(w-text_w)/2:"
            f"y=h-text_h-120:"
            f"line_spacing=8:"
            f"font=Sans:"
            f"fix_bounds=true"
            f"[out]"
        )
    else:
        filter_complex = (
            f"[0:v]"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={FPS}"
            f"[out]"
        )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",        # Loop video stream
        "-i", video_path,            # Input 0: video
        "-i", audio_path,            # Input 1: TTS audio
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-t", str(audio_duration),   # Trim to audio duration
        "-shortest",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg error composing segment:\n{result.stderr[-1000:]}"
        )


def _escape_ffmpeg_text(text: str) -> str:
    """Escape text for FFmpeg drawtext filter."""
    # Replace special chars that break drawtext
    text = text.replace("'", "\u2019")   # smart apostrophe
    text = text.replace('"', '\\"')
    text = text.replace(':', '\\:')
    text = text.replace('%', '\\%')
    text = text.replace('\\', '\\\\')
    text = re.sub(r'\s+', ' ', text).strip()
    # Word wrap: insert newline every ~40 chars at word boundary
    return _word_wrap(text, 40)


def _word_wrap(text: str, max_chars: int) -> str:
    """Insert '\\n' every max_chars characters at word boundaries."""
    words = text.split(' ')
    lines = []
    current = []
    current_len = 0

    for word in words:
        if current_len + len(word) + (1 if current else 0) > max_chars:
            lines.append(' '.join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + (1 if len(current) > 1 else 0)

    if current:
        lines.append(' '.join(current))

    return '\n'.join(lines)


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ], capture_output=True, text=True)

    try:
        return float(result.stdout.strip())
    except Exception:
        return 5.0
