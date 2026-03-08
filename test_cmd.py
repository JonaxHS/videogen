import subprocess

def test_cmd(video_path, audio_path, audio_duration, skip_seconds):
    filter_complex = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,fps=30[out]"
    
    video_input_options = []
    if skip_seconds > 0.0:
        video_input_options = ["-stream_loop", "-1", "-ss", str(skip_seconds)]
    else:
        video_input_options = ["-stream_loop", "-1"]

    if audio_path:
        cmd = [
            "ffmpeg", "-y",
            *video_input_options,
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-t", str(audio_duration),
            "output.mp4"
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
            "-an",
            "-t", str(audio_duration),
            "output.mp4"
        ]
    
    print(" ".join(cmd))

test_cmd("input.mp4", "audio.mp3", 5.0, 0.0)
test_cmd("input.mp4", "audio.mp3", 5.0, 3.5)
