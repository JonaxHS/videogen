"""
Video Search Module — Pexels API
Searches and downloads stock video clips matching a keyword query.
"""
import os
import hashlib
import requests
from pathlib import Path

PEXELS_API_BASE = "https://api.pexels.com/videos"
CACHE_DIR = Path("/app/cache/videos")


def search_and_download_video(
    keywords: str,
    output_path: str,
    pexels_api_key: str,
    orientation: str = "portrait",   # portrait = 9:16 vertical
    min_duration: int = 5,
    fallback_keywords: str = "nature landscape",
) -> str:
    """
    Search Pexels for a video matching keywords and download it.
    Uses local cache to avoid redundant downloads.
    Returns path to downloaded video file.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Try portrait first, fallback to landscape if needed
    video_url = _search_pexels(keywords, pexels_api_key, orientation, min_duration)

    if not video_url:
        # Try landscape
        video_url = _search_pexels(keywords, pexels_api_key, "landscape", min_duration)

    if not video_url:
        # Final fallback: generic keyword
        video_url = _search_pexels(fallback_keywords, pexels_api_key, "landscape", min_duration)

    if not video_url:
        raise RuntimeError(f"No video found for keywords: '{keywords}'")

    # Check cache
    url_hash = hashlib.md5(video_url.encode()).hexdigest()
    cached_path = CACHE_DIR / f"{url_hash}.mp4"

    if cached_path.exists():
        return str(cached_path)

    # Download video
    response = requests.get(video_url, stream=True, timeout=60)
    response.raise_for_status()

    with open(cached_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return str(cached_path)


def _search_pexels(
    query: str,
    api_key: str,
    orientation: str,
    min_duration: int,
    per_page: int = 10,
) -> str | None:
    """
    Search Pexels API and return the best matching video file URL.
    Prefers HD (720p) for performance, HD files are smaller.
    """
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "orientation": orientation,
        "size": "medium",
        "per_page": per_page,
    }

    try:
        resp = requests.get(
            f"{PEXELS_API_BASE}/search",
            headers=headers,
            params=params,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[VideoSearch] Pexels request failed: {e}")
        return None

    videos = data.get("videos", [])
    if not videos:
        return None

    # Filter by min duration
    valid = [v for v in videos if v.get("duration", 0) >= min_duration]
    if not valid:
        valid = videos  # relax constraint

    # Pick first valid video; prefer HD file (720p)
    for video in valid:
        files = video.get("video_files", [])
        # Sort by quality: prefer 720p
        hd_files = [f for f in files if f.get("quality") in ("hd", "sd")]
        hd_files.sort(key=lambda f: f.get("height", 0), reverse=True)
        if hd_files:
            return hd_files[0]["link"]

    return None
