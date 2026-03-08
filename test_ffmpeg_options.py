import subprocess
import glob
print("Starting script...")
videos = glob.glob("/app/cache/videos/*.mp4")
if not videos: exit(1)

v = videos[0]
print(f"Testing {v}")

cmd = [
    "ffmpeg", "-y",
    "-stream_loop", "-1",
    "-i", v,
    "-i", "/app/dummy.mp3",
    "-filter_complex", "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop='min(iw,1080)':'min(ih,1920)':'(iw-min(iw,1080))/2':'(ih-min(ih,1920))/2',setsar=1,fps=30[out]",
    "-map", "[out]",
    "-map", "1:a",
    "-vsync", "1",
    "-async", "1",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-c:a", "aac",
    "-b:a", "128k",
    "-t", "7.5",
    "/app/test_streamloop.mp4"
]

print("Running Stream Loop with vsync/async:")
res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stderr[-1500:])

cmd2 = [
    "ffmpeg", "-y",
    "-stream_loop", "-1",
    "-fflags", "+genpts",
    "-i", v,
    "-i", "/app/dummy.mp3",
    "-filter_complex", "[0:v]setpts=N/FRAME_RATE/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop='min(iw,1080)':'min(ih,1920)':'(iw-min(iw,1080))/2':'(ih-min(ih,1920))/2',setsar=1,fps=30[out]",
    "-map", "[out]",
    "-map", "1:a",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-c:a", "aac",
    "-b:a", "128k",
    "-t", "7.5",
    "/app/test_streamloop2.mp4"
]

print("\nRunning Stream Loop with setpts filter:")
res2 = subprocess.run(cmd2, capture_output=True, text=True)
print(res2.stderr[-1500:])

cmd_vfilter = [
    "ffmpeg", "-y",
    "-i", v,
    "-i", "/app/dummy.mp3",
    "-filter_complex", "[0:v]loop=loop=-1:size=250:start=0,setpts=N/FRAME_RATE/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop='min(iw,1080)':'min(ih,1920)':'(iw-min(iw,1080))/2':'(ih-min(ih,1920))/2',setsar=1,fps=30[out]",
    "-map", "[out]",
    "-map", "1:a",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-c:a", "aac",
    "-b:a", "128k",
    "-t", "7.5",
    "/app/test_vfilter.mp4"
]

print("\nRunning Video Loop Filter with size=250:")
res3 = subprocess.run(cmd_vfilter, capture_output=True, text=True)
print(res3.stderr[-1500:])
