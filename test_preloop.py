import subprocess
import glob

print("Testing pre-loop via raw copy stream_loop first...")
videos = glob.glob("/app/cache/videos/*.mp4")
if not videos: exit(1)

v = videos[0]
preloop_out = "/app/preloop.mp4"

res1 = subprocess.run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", v, "-c", "copy", "-t", "7.5", preloop_out], capture_output=True, text=True)
print("Preloop pass:", res1.stderr[-500:])

cmd = [
    "ffmpeg", "-y",
    "-i", preloop_out,
    "-i", "/app/dummy.mp3",
    "-filter_complex", "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop='min(iw,1080)':'min(ih,1920)':'(iw-min(iw,1080))/2':'(ih-min(ih,1920))/2',setsar=1,fps=30[out]",
    "-map", "[out]",
    "-map", "1:a",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-c:a", "aac",
    "-b:a", "128k",
    "/app/test_final.mp4"
]
print("\nFinal pass:")
res2 = subprocess.run(cmd, capture_output=True, text=True)
print(res2.stderr[-1000:])
