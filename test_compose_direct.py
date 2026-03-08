import glob
import os
import sys
import subprocess

# Change to the app directory so imports work
os.chdir('/app')
sys.path.append('/app')

from modules.composer import compose_video

videos = glob.glob("/app/cache/videos/*.mp4")
if not videos:
    print("No videos found")
    exit(1)

v = videos[0]
print(f"Testing compose on video: {v}")

# Create dummy audio
audio_path = "/app/dummy_compose.mp3"
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=7.5", "-c:a", "libmp3lame", audio_path], capture_output=True)

test_script = [
    {
        "video_path": v,
        "text": "test subtitles for video generation",
        "audio_path": audio_path,
        "audio_duration": 7.5
    }
]

out_path, _ = compose_video(
    segments=test_script, 
    output_path="/app/output/test_compose_direct.mp4",
    show_subtitles=True
)
print(f"Final output path: {out_path}")
if out_path and os.path.exists(out_path):
    print(f"Size: {os.path.getsize(out_path)} bytes")
else:
    print("Generation failed")
