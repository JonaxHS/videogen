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
NASA_INTRO_SKIP_SECONDS = float(os.getenv("NASA_INTRO_SKIP_SECONDS", "2.0"))
ESA_INTRO_SKIP_SECONDS = float(os.getenv("ESA_INTRO_SKIP_SECONDS", "2.0"))

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
    "karaoke": {
        "fontsize": 58,
        "fontcolor": "white",
        "boxcolor": "none",
        "position": "bottom",
        "line_spacing": 8,
        "boxborderw": 0,
        "borderw": 4,
        "bordercolor": "black",
        "max_steps": 16,
        "mode": "progressive",
        "extra": ":shadowx=2:shadowy=2:shadowcolor=black@0.9"
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
    add_attribution: bool = True,
) -> tuple:
    """
    Compose all segments into a final reel video using FFmpeg.
    Automatically adds attribution watermark for NASA/ESA sources.

    Each segment dict must have:
        - video_path: str
        - text: str
        - audio_duration: float (seconds)
    Optional:
        - audio_path: str (if omitted, segment will be rendered without audio)
        - video_provider: str (nasa, esa, pexels, pixabay, manual)

    Args:
      subtitle_style: one of the keys in SUBTITLE_STYLES
      add_attribution: if True, add watermark with source credits
    
    Returns:
        tuple: (output_path, sources_dict)
        sources_dict = {'nasa': 1, 'esa': 0, 'pexels': 2, 'pixabay': 0}
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Validate subtitle style
    if subtitle_style not in SUBTITLE_STYLES:
        subtitle_style = DEFAULT_SUBTITLE_STYLE

    # Extract sources used
    sources_used = get_sources_from_segments(segments)

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
            video_source_url=seg.get("video_source_url", ""),
            video_skip_seconds=seg.get("video_skip_seconds", 0.0),
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

    final_output = str(Path(output_path).parent / "final_concat.mp4")
    
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_path),
        "-c", "copy",
        final_output
    ], check=True, capture_output=True)

    # Add attribution watermark if needed
    if progress_callback:
        progress_callback(90, "Verificando atribuciones...")
    
    if add_attribution and (sources_used['nasa'] > 0 or sources_used['esa'] > 0):
        if progress_callback:
            progress_callback(95, "Agregando créditos...")
        attribution_text = generate_attribution_text(sources_used)
        add_attribution_watermark(
            video_path=final_output,
            output_path=output_path,
            attribution_text=attribution_text,
            font_size=28,
            position="bottom"
        )
    else:
        # No attribution needed, move final to output
        subprocess.run(["mv", final_output, output_path], check=True, capture_output=True)

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

    # Return tuple with sources used
    return output_path, sources_used


def _compose_segment(
    video_path: str,
    audio_path: Optional[str],
    text: str,
    audio_duration: float,
    output_path: str,
    show_subtitles: bool,
    video_provider: str = "manual",
    video_source_url: str = "",
    video_skip_seconds: float = 0.0,
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
        borderw = int(style.get("borderw", 0) or 0)
        bordercolor = str(style.get("bordercolor", "black"))
        mode = str(style.get("mode", "static"))
        max_steps = int(style.get("max_steps", 16) or 16)
        extra = style["extra"]

        # Calculate Y position based on position parameter
        if position == "top":
            y_pos = "100"
        elif position == "center":
            y_pos = "(h-text_h)/2"
        else:  # bottom (default)
            y_pos = "h-text_h-120"

        # Build drawtext filter(s)
        use_box = boxborderw > 0 and str(boxcolor).strip().lower() not in {"", "transparent", "none"}

        if mode == "progressive":
            drawtext_filter = _build_progressive_drawtext_filter(
                text=text,
                safe_text=safe_text,
                audio_duration=audio_duration,
                fontcolor=fontcolor,
                fontsize=fontsize,
                y_pos=y_pos,
                line_spacing=line_spacing,
                borderw=borderw,
                bordercolor=bordercolor,
                extra=extra,
                max_steps=max_steps,
            )
        else:
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
            if borderw > 0:
                drawtext_parts.append(f"borderw={borderw}:")
                drawtext_parts.append(f"bordercolor={bordercolor}:")

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

    provider_value = (video_provider or "").lower()
    source_value = (video_source_url or "").lower()
    is_nasa_clip = ("nasa" in provider_value) or ("nasa" in source_value)
    is_esa_clip = ("esa" in provider_value) or ("esa.int" in source_value) or ("esahubble.org" in source_value)
    
    # Determine skip seconds: use detected value or NASA fallback
    skip_seconds = float(video_skip_seconds or 0.0)
    if skip_seconds == 0.0 and is_nasa_clip:
        skip_seconds = NASA_INTRO_SKIP_SECONDS
    if skip_seconds == 0.0 and is_esa_clip:
        skip_seconds = ESA_INTRO_SKIP_SECONDS

    # Put -ss BEFORE -stream_loop for correct intro trimming
    video_input_options = ["-stream_loop", "-1"]
    if skip_seconds > 0.0:
        video_input_options = ["-ss", str(skip_seconds), "-stream_loop", "-1"]

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

    try:
        print(f"[Composer] Composing segment: {output_path}")
        print(f"[Composer] Audio duration: {audio_duration}s, Skip: {skip_seconds}s")
        print(f"[Composer] FFmpeg cmd: {' '.join(cmd[:10])}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 min timeout
        if result.returncode != 0:
            error_msg = result.stderr[-1500:] if result.stderr else "Unknown error"
            print(f"[Composer] FFmpeg stderr: {error_msg}")
            raise RuntimeError(
                f"FFmpeg error composing segment:\n{error_msg}"
            )
        print(f"[Composer] ✓ Segment composed successfully")
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"FFmpeg timeout (>300s) composing segment. Check video/audio duration compatibility."
        )


def _build_progressive_drawtext_filter(
    text: str,
    safe_text: str,
    audio_duration: float,
    fontcolor: str,
    fontsize: int,
    y_pos: str,
    line_spacing: int,
    borderw: int,
    bordercolor: str,
    extra: str,
    max_steps: int,
) -> str:
    words = [w for w in (text or "").split() if w.strip()]
    if len(words) <= 1 or audio_duration <= 0.2:
        parts = [
            "drawtext=",
            f"text='{safe_text}':",
            f"fontcolor={fontcolor}:",
            f"fontsize={fontsize}:",
            "box=0:",
            f"borderw={max(0, int(borderw))}:",
            f"bordercolor={bordercolor}:",
            "x=(w-text_w)/2:",
            f"y={y_pos}:",
            f"line_spacing={line_spacing}:",
            "font=Sans:",
            "fix_bounds=true",
            f"{extra}",
        ]
        return "".join(parts)

    steps = max(2, min(len(words), max_steps))
    group_size = max(1, (len(words) + steps - 1) // steps)
    phrases = []
    for end in range(group_size, len(words) + group_size, group_size):
        phrase = " ".join(words[: min(end, len(words))]).strip()
        if phrase:
            phrases.append(_escape_ffmpeg_text(phrase))
    if not phrases:
        phrases = [safe_text]

    step_duration = max(0.08, audio_duration / max(1, len(phrases)))
    filters = []

    for idx, phrase in enumerate(phrases):
        start_t = idx * step_duration
        end_t = audio_duration + 0.02 if idx == len(phrases) - 1 else (idx + 1) * step_duration
        parts = [
            "drawtext=",
            f"text='{phrase}':",
            f"fontcolor={fontcolor}:",
            f"fontsize={fontsize}:",
            "box=0:",
            f"borderw={max(0, int(borderw))}:",
            f"bordercolor={bordercolor}:",
            "x=(w-text_w)/2:",
            f"y={y_pos}:",
            f"line_spacing={line_spacing}:",
            "font=Sans:",
            "fix_bounds=true:",
            f"enable='between(t,{start_t:.2f},{end_t:.2f})'",
            f"{extra}",
        ]
        filters.append("".join(parts))

    return ",".join(filters)


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


def get_sources_from_segments(segments: List[Dict]) -> Dict[str, int]:
    """
    Extract providers used from segments.
    Returns dict with count: {'nasa': 2, 'pexels': 1, 'esa': 0, 'pixabay': 0}
    """
    sources = {
        'nasa': 0,
        'esa': 0,
        'pexels': 0,
        'pixabay': 0,
        'manual': 0
    }
    
    for segment in segments:
        provider = segment.get('video_provider', 'manual').lower()
        if provider in sources:
            sources[provider] += 1
    
    return sources


def generate_attribution_text(sources: Dict[str, int]) -> str:
    """
    Generate credit text based on sources used.
    
    Examples:
    "Sources: NASA, Pexels" 
    "Credit: ESA, Pixabay"
    """
    credits = []
    
    if sources.get('nasa', 0) > 0:
        credits.append("NASA")
    if sources.get('esa', 0) > 0:
        credits.append("ESA")
    if sources.get('pexels', 0) > 0:
        credits.append("Pexels")
    if sources.get('pixabay', 0) > 0:
        credits.append("Pixabay")
    
    if not credits:
        return ""
    
    # If contains NASA/ESA, specify more details
    if 'NASA' in credits or 'ESA' in credits:
        return f"Sources: {', '.join(credits)} | nasa.gov | esa.int"
    else:
        return f"Sources: {', '.join(credits)}"


def add_attribution_watermark(
    video_path: str,
    output_path: str,
    attribution_text: str,
    font_size: int = 28,
    position: str = "bottom"
) -> str:
    """
    Add attribution credit watermark to final 3 seconds of video.
    
    Args:
        video_path: original video path
        output_path: where to save with watermark
        attribution_text: credit text to display
        font_size: font size (default 28)
        position: "bottom" or "top"
    
    Returns:
        path to video with watermark
    """
    if not attribution_text:
        # No credits, copy original
        subprocess.run(["cp", video_path, output_path], check=True, capture_output=True)
        return output_path
    
    try:
        # Get video duration
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10
        )
        duration = float(result.stdout.strip())
    except Exception as e:
        print(f"[Attribution] Error getting duration: {e}, using fallback 60s")
        duration = 60.0
    
    # Show credit in last 3 seconds
    start_time = max(0, duration - 3)
    
    # Configure position
    y_pos = "h-50" if position == "bottom" else "50"
    
    # Escape quotes in attribution text
    escaped_text = attribution_text.replace("'", "\\'")
    
    # FFmpeg filter to add text
    filter_complex = (
        f"drawtext=text='{escaped_text}':"
        f"fontsize={font_size}:"
        f"fontcolor=white:"
        f"shadowx=2:shadowy=2:shadowcolor=black@0.8:"
        f"x='(w-text_w)/2':"
        f"y={y_pos}:"
        f"enable='between(t,{start_time},{duration})'"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", filter_complex,
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "fast",
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 min timeout
        if result.returncode != 0:
            print(f"[Attribution] FFmpeg error: {result.stderr[-500:]}")
            # Fallback: copy without watermark
            subprocess.run(["cp", video_path, output_path], check=True, capture_output=True)
        return output_path
    except subprocess.TimeoutExpired:
        print(f"[Attribution] FFmpeg timeout (>300s), using fallback copy")
        subprocess.run(["cp", video_path, output_path], check=True, capture_output=True)
        return output_path
    except Exception as e:
        print(f"[Attribution] Error adding watermark: {e}, using fallback")
        # Fallback: copy without watermark
        subprocess.run(["cp", video_path, output_path], check=True, capture_output=True)
        return output_path


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
