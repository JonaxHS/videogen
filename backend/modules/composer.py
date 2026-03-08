"""
Video Composer Module
Assembles final reel video from segments: clips + TTS audio + subtitles.
Output format: 9:16 vertical (1080x1920) at 30fps.
"""
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Dict, Callable, Optional


# Output video settings
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FPS = 30
OUTPUT_FORMAT = "mp4"
NASA_INTRO_SKIP_SECONDS = float(os.getenv("NASA_INTRO_SKIP_SECONDS", "2.0"))
ESA_INTRO_SKIP_SECONDS = float(os.getenv("ESA_INTRO_SKIP_SECONDS", "2.0"))
FFMPEG_THREADS = max(1, int(os.getenv("FFMPEG_THREADS", "2")))
LOWMEM_WIDTH = int(os.getenv("FFMPEG_LOWMEM_WIDTH", "720"))
LOWMEM_HEIGHT = int(os.getenv("FFMPEG_LOWMEM_HEIGHT", "1280"))
LOWMEM_FPS = int(os.getenv("FFMPEG_LOWMEM_FPS", "24"))

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
        "max_steps": 4,  # Limit to 4 progressive steps for VPS stability
        "mode": "progressive",
        "extra": ":shadowx=2:shadowy=2:shadowcolor=black@0.9"
    },
    "reel-impact": {
        "fontsize": 74,
        "fontcolor": "white",
        "boxcolor": "none",
        "position": "bottom",
        "y_offset": 220,
        "line_spacing": -2,
        "boxborderw": 0,
        "borderw": 10,
        "bordercolor": "black",
        "mode": "progressive",
        "max_steps": 30,  # Allow more steps for word-by-word display
        "force_progressive": True,
        "font": "DejaVu Sans Bold",
        "wrap_chars": 20,
        "max_lines": 3,
        "extra": ":shadowx=4:shadowy=4:shadowcolor=black@0.6"
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
        import shutil
        shutil.rmtree(str(temp_dir))
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
        style = SUBTITLE_STYLES.get(subtitle_style, SUBTITLE_STYLES[DEFAULT_SUBTITLE_STYLE])
        wrap_chars = int(style.get("wrap_chars", 40) or 40)
        max_lines = int(style.get("max_lines", 3) or 3)
        force_progressive = bool(style.get("force_progressive", False))

        safe_text = _escape_ffmpeg_text(text, max_chars=wrap_chars, max_lines=max_lines)

        if len(text) > 120:
            words = text.split()
            safe_text = _escape_ffmpeg_text(' '.join(words[:20]) + '...', max_chars=wrap_chars, max_lines=max_lines)

        font_name = str(style.get("font", "Sans"))
        
        # reel-impact and similar heavy fonts look best in uppercase
        if font_name == "DejaVu Sans Bold" or subtitle_style == "reel-impact":
            text = text.upper()
            safe_text = safe_text.upper()

        # Get style config
        fontsize = style["fontsize"]
        fontcolor = style["fontcolor"]
        boxcolor = style["boxcolor"]
        position = style["position"]
        line_spacing = style["line_spacing"]
        boxborderw = style["boxborderw"]
        borderw = int(style.get("borderw", 0) or 0)
        bordercolor = str(style.get("bordercolor", "black"))
        font_name = str(style.get("font", "Sans"))
        mode = str(style.get("mode", "static"))
        max_steps = int(style.get("max_steps", 4) or 4)  # Limit to 4 progressive steps max (VPS stability)
        extra = style["extra"]
        y_offset = int(style.get("y_offset", 120) or 120)

        # Calculate Y position based on position parameter
        if position == "top":
            y_pos = "100"
        elif position == "center":
            y_pos = "(h-text_h)/2"
        else:  # bottom (default)
            y_pos = f"h-text_h-{y_offset}"

        # Build drawtext filter(s)
        use_box = boxborderw > 0 and str(boxcolor).strip().lower() not in {"", "transparent", "none"}

        # For texts with many words, use simple mode to avoid too many drawtext filters
        words = [w for w in (text or "").split() if w.strip()]
        force_progressive = bool(style.get("force_progressive", False))
        use_simple_mode = len(words) > 20 and not force_progressive
        if use_simple_mode:
            print(f"[Composer] Text has {len(words)} words: using simple mode (static subtitle)")
        elif force_progressive:
            print(f"[Composer] Text has {len(words)} words: forcing progressive mode")

        if mode == "progressive" and not use_simple_mode:
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
                font_name=font_name,
                extra=extra,
                max_steps=max_steps,
                wrap_chars=wrap_chars,
                max_lines=max_lines,
            )
        else:
            clean_text = _escape_ffmpeg_text(text, max_chars=wrap_chars, max_lines=max_lines)
            lines = clean_text.split('\n')
            filters = []
            
            for i, line in enumerate(lines):
                if not line.strip(): continue # Skip empty lines
                
                line_y = f"{y_pos} + {i} * (text_h + {line_spacing})"
                
                drawtext_parts = [
                    "drawtext=",
                    f"text='{line}':",
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
                    f"y={line_y}:",
                    f"font={font_name}:",
                    "fix_bounds=true",
                    f"{extra}",
                ])
                filters.append("".join(drawtext_parts))
                
            drawtext_filter = ",".join(filters)

    # loop_filter will be set after video_dur is calculated below - placeholder
    loop_filter = ""  # Will be set after needs_loop is determined

    if show_subtitles and drawtext_filter:
        filter_complex = (
            f"[0:v]"
            f"{loop_filter}"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop='min(iw,{OUTPUT_WIDTH})':'min(ih,{OUTPUT_HEIGHT})':'(iw-min(iw,{OUTPUT_WIDTH}))/2':'(ih-min(ih,{OUTPUT_HEIGHT}))/2',"
            f"setsar=1,"
            f"fps={FPS}"
            f"[scaled];"
            f"[scaled]"
            f"{drawtext_filter}"
            f"[out]"
        )
    else:
        filter_complex = (
            f"[0:v]"
            f"{loop_filter}"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop='min(iw,{OUTPUT_WIDTH})':'min(ih,{OUTPUT_HEIGHT})':'(iw-min(iw,{OUTPUT_WIDTH}))/2':'(ih-min(ih,{OUTPUT_HEIGHT}))/2',"
            f"setsar=1,"
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

    # Prevent ffmpeg frame=0 bug: if -ss skips past EOF, stream_loop fails immediately
    video_dur = get_audio_duration(video_path)  # Gets container duration
    if skip_seconds >= video_dur - 0.5:
        skip_seconds = 0.0  # Don't skip if video is too short to survive the trim

    # Determine if video needs looping (shorter than what we need to output)
    needs_loop = (video_dur <= 0) or (video_dur < (audio_duration + skip_seconds))

    # Two-pass approach: if looping is needed, pre-render the looped stream first.
    # This prevents the known FFmpeg bug where `-stream_loop -1` combined with H264 MP4s
    # and a second audio stream silently outputs 0 frames.
    if needs_loop:
        import math
        temp_dir_local = os.path.dirname(output_path)
        preloop_path = os.path.join(temp_dir_local, f"preloop_{os.path.basename(video_path)}")
        list_txt_path = os.path.join(temp_dir_local, f"list_{os.path.basename(video_path)}.txt")
        
        target_len = audio_duration + skip_seconds
        
        # Calculate how many times we need to loop the video
        safe_dur = video_dur if video_dur > 0 else 1.0
        repeat_count = math.ceil(target_len / safe_dur) + 1
        
        # Create a concat list file
        with open(list_txt_path, "w") as f:
            for _ in range(repeat_count):
                f.write(f"file '{os.path.abspath(video_path)}'\n")
                
        # Use concat demuxer which is much more robust than stream_loop
        preloop_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_txt_path,
            "-c", "copy",
            "-t", str(target_len),
            preloop_path
        ]
        print(f"[Composer] Pre-looping short video to {target_len}s via concat ({repeat_count}x)...", flush=True)
        res_preloop = subprocess.run(preloop_cmd, capture_output=True, text=True)
        if res_preloop.returncode != 0:
            print(f"[Composer] WARNING: Preloop failed. FFmpeg command: {' '.join(preloop_cmd)}", flush=True)
            print(f"[Composer] WARNING: Preloop failed. FFmpeg output:\n{res_preloop.stderr[-1000:]}", flush=True)
            # Fallback to original path if preloop fails (will likely 0-frame but avoids crash)
        else:
            video_path = preloop_path  # Use the pre-looped file for the main composition
        
        # Cleanup the list text file
        try:
            os.remove(list_txt_path)
        except OSError:
            pass

    def _build_filter_chain(width: int, height: int, fps_value: int, subtitle_filter: str) -> str:
        if show_subtitles and subtitle_filter:
            return (
                f"[0:v]"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop='min(iw,{width})':'min(ih,{height})':'(iw-min(iw,{width}))/2':'(ih-min(ih,{height}))/2',"
                f"setsar=1,"
                f"fps={fps_value}"
                f"[scaled];"
                f"[scaled]"
                f"{subtitle_filter}"
                f"[out]"
            )
        return (
            f"[0:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop='min(iw,{width})':'min(ih,{height})':'(iw-min(iw,{width}))/2':'(ih-min(ih,{height}))/2',"
            f"setsar=1,"
            f"fps={fps_value}"
            f"[out]"
        )

    drawtext_filter_local = drawtext_filter if show_subtitles else ""
    filter_complex = _build_filter_chain(OUTPUT_WIDTH, OUTPUT_HEIGHT, FPS, drawtext_filter_local)

    # Input options: no more early inputs needed
    video_input_options = []

    skip_opts = [] if skip_seconds <= 0.0 else ["-ss", str(skip_seconds)]  # Output-side seek


    def _build_ffmpeg_cmd(filter_chain: str, lowmem: bool = False) -> list[str]:
        if lowmem:
            video_codec_args = [
                "-c:v", "libx264",
                "-threads", "1",
                "-preset", "ultrafast",
                "-crf", "30",
                "-pix_fmt", "yuv420p",
                "-x264-params", "rc-lookahead=0:sync-lookahead=0:ref=1:bframes=0:subme=1:me=dia:trellis=0:aq-mode=0",
            ]
            audio_bitrate = "96k"
        else:
            video_codec_args = [
                "-c:v", "libx264",
                "-threads", str(FFMPEG_THREADS),
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
            ]
            audio_bitrate = "128k"

        if audio_path:
            return [
                "ffmpeg", "-y",
                *skip_opts,
                *video_input_options,
                "-i", video_path,
                "-i", audio_path,
                "-filter_complex", filter_chain,
                "-map", "[out]",
                "-map", "1:a",
                *video_codec_args,
                "-c:a", "aac",
                "-b:a", audio_bitrate,
                "-t", str(audio_duration),
                output_path
            ]

        return [
            "ffmpeg", "-y",
            *skip_opts,
            *video_input_options,
            "-i", video_path,
            "-filter_complex", filter_chain,
            "-map", "[out]",
            *video_codec_args,
            "-an",
            "-t", str(audio_duration),
            output_path
        ]

    cmd = _build_ffmpeg_cmd(filter_complex, lowmem=False)

    try:
        print(f"[Composer] Composing segment: {output_path}", flush=True)
        print(f"[Composer] Audio duration: {audio_duration}s, Skip: {skip_seconds}s, Subtitles: {show_subtitles}", flush=True)
        print(f"[Composer] FFmpeg preset: fast, threads: {FFMPEG_THREADS}", flush=True)
        if show_subtitles and "drawtext" in filter_complex:
            print(f"[Composer] Filter chain: video scale/crop/fps + drawtext subtitles", flush=True)
        
        print(f"[Composer] CMD: {' '.join(cmd)}", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 min timeout
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-1500:]
            stdout_tail = (result.stdout or "")[-600:]
            if result.returncode < 0:
                signal_num = abs(result.returncode)
                exit_info = f"terminated by signal {signal_num} (likely OOM/KILL if signal=9)"
            else:
                exit_info = f"exit code {result.returncode}"
            error_msg = (
                f"FFmpeg failed with {exit_info}.\n"
                f"stderr (tail):\n{stderr_tail}\n"
                f"stdout (tail):\n{stdout_tail}"
            )
            print(f"[Composer] FFmpeg error: {error_msg}", flush=True)
            
            # Fallback A: retry in low-memory mode when killed by OOM (signal 9)
            if "signal 9" in exit_info:
                print("[Composer] Retrying in low-memory mode (720x1280@24fps, ultrafast, single-thread)...", flush=True)
                lowmem_filter = _build_filter_chain(LOWMEM_WIDTH, LOWMEM_HEIGHT, LOWMEM_FPS, drawtext_filter_local)
                lowmem_cmd = _build_ffmpeg_cmd(lowmem_filter, lowmem=True)
                lowmem_result = subprocess.run(lowmem_cmd, capture_output=True, text=True, timeout=300)
                if lowmem_result.returncode == 0:
                    print("[Composer] ✓ Low-memory fallback succeeded", flush=True)
                    return

            # Fallback B: retry without subtitles if drawtext filter is in use
            if show_subtitles and "drawtext" in filter_complex and "-shortest" not in str(cmd):
                print(f"[Composer] Retrying without subtitles (fallback)...", flush=True)
                # Rebuild command without subtitles
                fallback_filter = _build_filter_chain(OUTPUT_WIDTH, OUTPUT_HEIGHT, FPS, "")
                fallback_cmd = _build_ffmpeg_cmd(fallback_filter, lowmem=False)
                result = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    print(f"[Composer] ✓ Fallback (no subtitles) succeeded")
                    return
            
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
    font_name: str,
    extra: str,
    max_steps: int,
    wrap_chars: int,
    max_lines: int,
    output_path: str = "",
) -> str:
    import uuid
    import os
    temp_dir_local = os.path.dirname(output_path) or "."
    words = [w for w in (text or "").split() if w.strip()]
    if len(words) <= 1 or audio_duration <= 0.2:
        clean_text = _escape_ffmpeg_text(text, max_chars=9999, max_lines=0)
        lines = clean_text.split('\n')
        filters = []
        for i, line in enumerate(lines):
            # Calculate Y offset for this line
            # Base Y position + (line index * (line height + spacing))
            # Rough estimate: text_h is height of one line.
            line_y = f"{y_pos} + {i} * (text_h + {line_spacing})"
            
            parts = [
                "drawtext=",
                f"text='{line}':",
                f"fontcolor={fontcolor}:",
                f"fontsize={fontsize}:",
                "box=0:",
                f"borderw={max(0, int(borderw))}:",
                f"bordercolor={bordercolor}:",
                "x=(w-text_w)/2:",
                f"y={line_y}:",
                f"font={font_name}:",
                "fix_bounds=true",
                f"{extra}",
            ]
            filters.append("".join(parts))
        return ",".join(filters)

    # Strategy: Show words progressively (accumulating), word by word
    # When accumulated text exceeds max_lines, use sliding window (show only last words that fit)
    
    # Calculate time per word for synchronization
    time_per_word = audio_duration / len(words)
    
    phrases = []
    
    for word_idx in range(1, len(words) + 1):
        # Get words up to this point
        accumulated_words = words[:word_idx]
        accumulated_text = ' '.join(accumulated_words)
        
        # Estimate if text fits in screen width based on character count
        # For fontsize 62, roughly 24 chars per line for 1080px width
        # Max 2 lines = ~48 chars total
        max_chars_display = wrap_chars * max_lines  # e.g., 24 * 2 = 48 chars
        
        if len(accumulated_text) <= max_chars_display:
            # Fits comfortably, show all accumulated words
            display_text = accumulated_text
        else:
            # Too long, use sliding window: show only recent words that fit
            chars_so_far = 0
            words_to_show = []
            
            # Go backwards from current word, adding words until we hit the limit
            for i in range(len(accumulated_words) - 1, -1, -1):
                word = accumulated_words[i]
                if chars_so_far + len(word) + 1 <= max_chars_display:
                    words_to_show.insert(0, word)
                    chars_so_far += len(word) + 1
                else:
                    break
            
            display_text = ' '.join(words_to_show) if words_to_show else accumulated_words[-1]
        
        # Manually wrap text to max_lines by inserting newlines
        wrapped_text = _manual_wrap_text(display_text, wrap_chars, max_lines)
        
        # Clean text
        clean_text = _escape_ffmpeg_text(wrapped_text, max_chars=9999, max_lines=0)
        
        phrases.append({
            'lines': clean_text.split('\n'),
            'start': (word_idx - 1) * time_per_word,
            'end': word_idx * time_per_word if word_idx < len(words) else audio_duration + 0.02
        })
    
    # Limit to max_steps by sampling evenly if needed
    if len(phrases) > max_steps:
        step = max(1, len(phrases) // max_steps)
        sampled_phrases = []
        for i in range(0, len(phrases), step):
            sampled_phrases.append(phrases[i])
        # Always include the last phrase (complete text)
        if sampled_phrases[-1] != phrases[-1]:
            sampled_phrases.append(phrases[-1])
        phrases = sampled_phrases[:max_steps]
    
    if not phrases:
        phrases = [{'text': safe_text, 'start': 0, 'end': audio_duration}]

    filters = []

    for phrase_data in phrases:
        for i, line in enumerate(phrase_data['lines']):
            if not line.strip(): continue # Skip empty lines
            
            line_y = f"{y_pos} + {i} * (text_h + {line_spacing})"
            
            parts = [
                "drawtext=",
                f"text='{line}':",
                f"fontcolor={fontcolor}:",
                f"fontsize={fontsize}:",
                "box=0:",
                f"borderw={max(0, int(borderw))}:",
                f"bordercolor={bordercolor}:",
                "x=(w-text_w)/2:",
                f"y={line_y}:",
                f"font={font_name}:",
                "fix_bounds=true:",
                f"enable='between(t,{phrase_data['start']:.2f},{phrase_data['end']:.2f})'",
                f"{extra}",
            ]
            filters.append("".join(parts))

    return ",".join(filters)


def _manual_wrap_text(text: str, wrap_chars: int, max_lines: int) -> str:
    """
    Manually wrap text by inserting newlines at word boundaries.
    Returns text with newlines inserted to fit within wrap_chars per line.
    """
    words = text.split(' ')
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        word_len = len(word)
        # Check if adding this word would exceed wrap_chars
        space_needed = 1 if current_line else 0
        if current_length + space_needed + word_len <= wrap_chars:
            current_line.append(word)
            current_length += space_needed + word_len
        else:
            # Start new line
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
            current_length = word_len
            
            # Stop if we've reached max_lines
            if max_lines and len(lines) >= max_lines:
                break
    
    # Add last line if not at limit
    if current_line and (not max_lines or len(lines) < max_lines):
        lines.append(' '.join(current_line))
    
    return '\n'.join(lines)


def _escape_ffmpeg_text(text: str, max_chars: int = 40, max_lines: int = 3, for_textfile: bool = False) -> str:
    """Escape text for FFmpeg drawtext filter."""
    text = unicodedata.normalize("NFKC", text or "")
    
    # Remove ALL box/block drawing characters (U+2500-U+257F)
    # and geometric shapes (U+25A0-U+25FF)
    for code in range(0x2500, 0x2600):
        text = text.replace(chr(code), " ")
    
    # Remove specific problematic characters
    text = text.replace("□", " ").replace("�", " ")
    text = text.replace("■", " ").replace("▪", " ").replace("▫", " ")
    text = text.replace("\u200b", " ").replace("\ufeff", " ")
    text = text.replace("\u2018", "'").replace("\u2019", "'")  # Smart quotes
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")  # En/em dashes
    text = text.replace("\u2026", "...")  # Ellipsis
    
    # Remove categories: So (Other Symbols), Co (Private Use), Cs (Surrogates), Cf (Format)
    # Keep Spanish punctuation ¿¡ and basic letters/numbers/punctuation and newlines
    text = "".join(
        ch for ch in text 
        if (unicodedata.category(ch)[0] in {"L", "N", "P", "Z", "M", "C"} or ch in {"¿", "¡", "\n"})
    )
    
    # Keep only printable characters and newlines
    text = "".join(ch for ch in text if (ch.isprintable() or ch == "\n") and ch != "\r")
    
    # Collapse multiple spaces on same line (preserve newlines)
    lines = text.split('\n')
    lines = [re.sub(r' +', ' ', line).strip() for line in lines]
    text = '\n'.join(lines)
    
    # Order matters: handle newlines FIRST before other escaping
    # For FFmpeg drawtext in shell, newline needs special handling
    if for_textfile:
        return text
    
    text = text.replace('\n', '<<<NL>>>')  # Temporary placeholder
    
    # Now escape other special chars
    text = text.replace('\\', '\\\\')    # Must be first
    text = text.replace("'", "'\\''")    # Escape single quotes for shell
    text = text.replace(':', '\\:')      # FFmpeg drawtext uses : as separator
    text = text.replace('%', '\\%')
    text = text.replace('[', '\\[')
    text = text.replace(']', '\\]')
    
    # Replace newline placeholder with actual newline (will be preserved in single quotes)
    text = text.replace('<<<NL>>>', '\n')
    
    return text


def _word_wrap(text: str, max_chars: int, max_lines: int = 0) -> str:
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

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            last = lines[-1].rstrip()
            if not last.endswith('...'):
                lines[-1] = (last[:-3].rstrip() + '...') if len(last) > 3 else (last + '...')

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
