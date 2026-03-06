"""
Video Composer Module
Assembles final reel video from segments: clips + TTS audio + subtitles.
Output format: 9:16 vertical (1080x1920) at 30fps.
"""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Callable, Optional


# Output video settings
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FPS = 30
OUTPUT_FORMAT = "mp4"
NASA_INTRO_SKIP_SECONDS = 2.0

# Subtitle styles: {name: {fontsize, color, bgcolor, position, extra_params}}
SUBTITLE_STYLES = {
    "classic": {
        "fontsize": 60,
        "fontcolor": "white",
        "boxcolor": "black@0.55",
        "position": "bottom",
        "line_spacing": 8,
        "boxborderw": 12,
        "extra": ""
    },
    "luminous": {
        "fontsize": 58,
        "fontcolor": "white",
        "boxcolor": "black@0.7",
        "position": "bottom",
        "line_spacing": 8,
        "boxborderw": 14,
        "extra": ":shadowx=2:shadowy=2:shadowcolor=black@0.8"
    },
    "cinema": {
        "fontsize": 72,
        "fontcolor": "white",
        "boxcolor": "black@0.0",
        "position": "bottom",
        "line_spacing": 10,
        "boxborderw": 0,
        "extra": ":shadowx=3:shadowy=3:shadowcolor=black@0.9"
    },
    "yellow-subtitle": {
        "fontsize": 54,
        "fontcolor": "yellow",
        "boxcolor": "black@0.6",
        "position": "bottom",
        "line_spacing": 8,
        "boxborderw": 10,
        "extra": ""
    },
    "minimal": {
        "fontsize": 48,
        "fontcolor": "white",
        "boxcolor": "black@0.3",
        "position": "top",
        "line_spacing": 6,
        "boxborderw": 8,
        "extra": ""
    },
    "neon": {
        "fontsize": 64,
        "fontcolor": "cyan",
        "boxcolor": "black@0.8",
        "position": "bottom",
        "line_spacing": 8,
        "boxborderw": 10,
        "extra": ":shadowx=2:shadowy=2:shadowcolor=cyan@0.5"
    },
}

# Default style
DEFAULT_SUBTITLE_STYLE = "classic"


def compose_video(
    segments: List[Dict],
    output_path: str,
    progress_callback: Callable[[int, str], None] = None,
    show_subtitles: bool = True,
    subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
) -> str:
    """
    Compose all segments into a final reel video using FFmpeg.

        Each segment dict must have:
            - video_path: str
            - text: str
            - audio_duration: float (seconds)
        Optional:
            - audio_path: str (if omitted, segment will be rendered without audio)

    Args:
      subtitle_style: one of the keys in SUBTITLE_STYLES
    
    Returns path to the final video file.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Validate subtitle style
    if subtitle_style not in SUBTITLE_STYLES:
        subtitle_style = DEFAULT_SUBTITLE_STYLE

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
            audio_path=seg.get("audio_path"),
            text=seg["text"],
            audio_duration=seg["audio_duration"],
            output_path=str(seg_path),
            show_subtitles=show_subtitles,
            video_provider=seg.get("video_provider", "manual"),
            subtitle_style=subtitle_style,
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

    return output_path


def _compose_segment(
    video_path: str,
    audio_path: Optional[str],
    text: str,
    audio_duration: float,
    output_path: str,
    show_subtitles: bool,
    video_provider: str = "manual",
    subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
) -> None:
    """
    Compose a single segment:
    1. Crop/scale video to 9:16 (1080x1920)
    2. Trim video to target duration
    3. Overlay subtitle text with selected style
    4. Optionally mix with TTS audio if provided
    """
    # FFmpeg filter chain:
    # 1. Scale and crop to 9:16 (cover mode, no black bars)
    # 2. Add subtitle text only if show_subtitles=True
    if show_subtitles:
        safe_text = _escape_ffmpeg_text(text)

        if len(text) > 120:
            words = text.split()
            safe_text = _escape_ffmpeg_text(' '.join(words[:20]) + '...')

        # Get style config
        style = SUBTITLE_STYLES.get(subtitle_style, SUBTITLE_STYLES[DEFAULT_SUBTITLE_STYLE])
        fontsize = style["fontsize"]
        fontcolor = style["fontcolor"]
        boxcolor = style["boxcolor"]
        position = style["position"]
        line_spacing = style["line_spacing"]
        boxborderw = style["boxborderw"]
        extra = style["extra"]

        # Calculate Y position based on position parameter
        if position == "top":
            y_pos = "100"
        elif position == "center":
            y_pos = "(h-text_h)/2"
        else:  # bottom (default)
            y_pos = "h-text_h-120"

        # Build drawtext filter; disable box when style requests transparent/no border
        use_box = boxborderw > 0 and str(boxcolor).strip().lower() not in {"", "transparent", "none"}
        drawtext_parts = [
            "drawtext=",
            f"text='{safe_text}':",
            f"fontcolor={fontcolor}:",
            f"fontsize={fontsize}:",
            f"box={1 if use_box else 0}:",
        ]
        if use_box:
            drawtext_parts.append(f"boxcolor={boxcolor}:")
            drawtext_parts.append(f"boxborderw={boxborderw}:")

        drawtext_parts.extend([
            "x=(w-text_w)/2:",
            f"y={y_pos}:",
            f"line_spacing={line_spacing}:",
            "font=Sans:",
            "fix_bounds=true",
            f"{extra}",
        ])
        drawtext_filter = "".join(drawtext_parts)

        filter_complex = (
            f"[0:v]"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(iw-{OUTPUT_WIDTH})/2:(ih-{OUTPUT_HEIGHT})/2,"
            f"fps={FPS}"
            f"[scaled];"
            f"[scaled]"
            f"{drawtext_filter}"
            f"[out]"
        )
    else:
        filter_complex = (
            f"[0:v]"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(iw-{OUTPUT_WIDTH})/2:(ih-{OUTPUT_HEIGHT})/2,"
            f"fps={FPS}"
            f"[out]"
        )

    video_input_options = ["-stream_loop", "-1"]
    if (video_provider or "").lower() == "nasa":
        video_input_options.extend(["-ss", str(NASA_INTRO_SKIP_SECONDS)])

    if audio_path:
        cmd = [
            "ffmpeg", "-y",
            *video_input_options,          # Loop and optional intro trim for NASA clips
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
            "-t", str(audio_duration),   # Trim to target duration
            "-shortest",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            *video_input_options,
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-an",                       # No audio for preview mode
            "-t", str(audio_duration),
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
    # Order matters: escape backslash first, then other special chars
    text = text.replace('\\', '\\\\')    # Must be first
    text = text.replace("'", "'\\''")    # Escape single quotes for shell
    text = text.replace(':', '\\:')      # FFmpeg drawtext uses : as separator
    text = text.replace('%', '\\%')
    text = text.replace('[', '\\[')
    text = text.replace(']', '\\]')
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
