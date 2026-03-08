import sys

def test_filter(text, mode, audio_duration, fontsize=50, fontcolor="white", boxcolor="black", position="bottom", line_spacing=10, boxborderw=10, borderw=0, bordercolor="black", max_steps=4, extra=""):
    show_subtitles = True
    drawtext_filter = "NOT_ASSIGNED"
    
    if show_subtitles:
        safe_text = text
        
        use_box = boxborderw > 0 and str(boxcolor).strip().lower() not in {"", "transparent", "none"}

        # For texts with many words, use simple mode to avoid too many drawtext filters
        words = [w for w in (text or "").split() if w.strip()]
        use_simple_mode = len(words) > 12
        if use_simple_mode:
            print(f"[Composer] Text has {len(words)} words: using simple mode (static subtitle)")

        if mode == "progressive" and not use_simple_mode:
            drawtext_filter = "PROGRESSIVE_FILTER_OUTPUT"
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

            y_pos = "100"
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
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
            f"fps=30"
            f"[scaled];"
            f"[scaled]"
            f"{drawtext_filter}"
            f"[out]"
        )
        return filter_complex

print(test_filter("This is a short text.", "progressive", 5.0))
print(test_filter("This is a very long text that actually has more than twelve words so it should trigger the simple mode branch but we need to see if drawtext\_filter gets correctly assigned in this case or if it crashes because of scoping issues.", "progressive", 5.0))
print(test_filter("This is a short text.", "static", 5.0))
