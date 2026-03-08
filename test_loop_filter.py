import urllib.request
import subprocess
import glob

videos = glob.glob("/app/cache/videos/*.mp4")
if not videos:
    print("No videos in cache")
    exit(1)

v = videos[0]

# mock audio
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=7.5", "-c:a", "libmp3lame", "/app/dummy.mp3"], capture_output=True)

# exact command from python code structure:
cmd = [
    "ffmpeg", "-y",
    "-i", v,
    "-i", "/app/dummy.mp3",
    "-filter_complex", "[0:v]loop=loop=-1:size=32767:start=0,scale=1080:1920:force_original_aspect_ratio=increase,crop='min(iw,1080)':'min(ih,1920)':'(iw-min(iw,1080))/2':'(ih-min(ih,1920))/2',setsar=1,fps=30[out]",
    "-map", "[out]",
    "-map", "1:a",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-c:a", "aac",
    "-b:a", "128k",
    "-t", "7.5",
    "/app/test_out.mp4"
]
print("Running:", " ".join(cmd))
res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stderr[-1500:])

cmd_noloop = [
    "ffmpeg", "-y",
    "-i", v,
    "-i", "/app/dummy.mp3",
    "-filter_complex", "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop='min(iw,1080)':'min(ih,1920)':'(iw-min(iw,1080))/2':'(ih-min(ih,1920))/2',setsar=1,fps=30[out]",
    "-map", "[out]",
    "-map", "1:a",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-c:a", "aac",
    "-b:a", "128k",
    "-t", "7.5",
    "/app/test_noloop.mp4"
]
print("\n\nRunning Without Loop Filter:")
res_noloop = subprocess.run(cmd_noloop, capture_output=True, text=True)
print(res_noloop.stderr[-1500:])
