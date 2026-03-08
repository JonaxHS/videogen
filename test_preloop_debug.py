import subprocess
import glob
import os

print("Testing preloop logic exactly as in composer.py")
videos = glob.glob("/app/cache/videos/*.mp4")
if not videos: exit(1)

v = videos[0]
preloop_path = "/app/preloop.mp4"
target_len = 7.5

# Test 1: stream_loop with -c copy
cmd1 = [
    "ffmpeg", "-y",
    "-stream_loop", "-1",
    "-i", v,
    "-c", "copy",
    "-t", str(target_len),
    preloop_path
]
print("\nRunning stream_loop with -c copy:")
res1 = subprocess.run(cmd1, capture_output=True, text=True)
print(res1.stderr[-1000:])
if os.path.exists(preloop_path):
    print("preloop.mp4 size:", os.path.getsize(preloop_path))
else:
    print("preloop.mp4 NOT CREATED")

# Test 2: stream_loop with re-encoding instead of copy
preloop_path2 = "/app/preloop2.mp4"
cmd2 = [
    "ffmpeg", "-y",
    "-stream_loop", "-1",
    "-i", v,
    "-c:v", "libx264", "-preset", "ultrafast",  # re-encode just in case copy loses timestamps
    "-t", str(target_len),
    preloop_path2
]
print("\nRunning stream_loop with ultrafast re-encode:")
res2 = subprocess.run(cmd2, capture_output=True, text=True)
print(res2.stderr[-1000:])
if os.path.exists(preloop_path2):
    print("preloop2.mp4 size:", os.path.getsize(preloop_path2))

# Test 3: loop video filter directly in preloop
preloop_path3 = "/app/preloop3.mp4"
cmd3 = [
    "ffmpeg", "-y",
    "-i", v,
    "-filter_complex", "[0:v]loop=loop=-1:size=32767:start=0[out]",
    "-map", "[out]",
    "-c:v", "libx264", "-preset", "ultrafast",
    "-t", str(target_len),
    preloop_path3
]
print("\nRunning loop video filter pre-render:")
res3 = subprocess.run(cmd3, capture_output=True, text=True)
print(res3.stderr[-1000:])
if os.path.exists(preloop_path3):
    print("preloop3.mp4 size:", os.path.getsize(preloop_path3))
