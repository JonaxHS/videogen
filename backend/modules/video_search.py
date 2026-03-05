"""
Video Search Module — Pexels + Pixabay APIs
Searches and downloads stock video clips matching a keyword query.
"""
import hashlib
import re
import requests
from pathlib import Path

PEXELS_API_BASE = "https://api.pexels.com/videos"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"
CACHE_DIR = Path("/app/cache/videos")

STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "y", "o",
    "en", "con", "sin", "por", "para", "que", "es", "son", "se", "su", "sus", "como", "más",
    "muy", "ya", "pero", "si", "no", "the", "and", "or", "for", "with", "this", "that", "from",
}


def search_and_download_video(
    keywords: str,
    output_path: str,
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    context_text: str = "",
    min_duration: int = 5,
    fallback_keywords: str = "nature landscape",
) -> str:
    """
    Search Pexels/Pixabay for a video matching keywords and download it.
    Uses local cache to avoid redundant downloads.
    Returns path to downloaded video file.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not pexels_api_key and not pixabay_api_key:
        raise RuntimeError("No video provider API key configured (Pexels or Pixabay)")

    providers = []
    if pexels_api_key:
        providers.append(("pexels", pexels_api_key))
    if pixabay_api_key:
        providers.append(("pixabay", pixabay_api_key))

    video_url = None
    provider_name = None
    best_score = float("-inf")
    query_candidates = _build_query_candidates(keywords, context_text, fallback_keywords)

    for query in query_candidates:
        for candidate_provider, candidate_key in providers:
            if candidate_provider == "pexels":
                candidate = _search_pexels(query, candidate_key, min_duration)
            else:
                candidate = _search_pixabay(query, candidate_key, min_duration)

            if candidate and candidate["score"] > best_score:
                best_score = candidate["score"]
                video_url = candidate["url"]
                provider_name = candidate_provider

    if not video_url or not provider_name:
        raise RuntimeError(f"No video found for keywords: '{keywords}'")

    # Check cache
    cache_key = f"{provider_name}:{video_url}"
    url_hash = hashlib.md5(cache_key.encode()).hexdigest()
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
    min_duration: int,
    per_page: int = 20,
) -> dict | None:
    """
    Search Pexels API and return best candidate with score + URL.
    Scoring balances textual relevance + duration + resolution.
    """
    headers = {"Authorization": api_key}
    params = {
        "query": query,
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

    query_terms = _extract_terms(query)
    best = None

    for video in videos:
        duration = int(video.get("duration", 0) or 0)
        files = video.get("video_files", [])
        if not files:
            continue

        ranked_files = sorted(
            files,
            key=lambda f: (int(f.get("width", 0) or 0) * int(f.get("height", 0) or 0)),
            reverse=True,
        )
        selected = ranked_files[0]
        link = selected.get("link")
        if not link:
            continue

        metadata_text = " ".join([
            str(video.get("url", "")),
            str((video.get("user") or {}).get("name", "")),
            str(video.get("id", "")),
        ])

        relevance = _text_relevance_score(query_terms, metadata_text)
        duration_score = max(0.0, 25.0 - abs(duration - min_duration) * 2.0)
        resolution_score = min(25.0, (int(selected.get("width", 0) or 0) * int(selected.get("height", 0) or 0)) / 150000.0)
        total_score = relevance * 10.0 + duration_score + resolution_score

        if best is None or total_score > best["score"]:
            best = {"url": link, "score": total_score}

    return best


def _search_pixabay(
    query: str,
    api_key: str,
    min_duration: int,
    per_page: int = 25,
) -> dict | None:
    """
    Search Pixabay videos API and return best candidate with score + URL.
    """
    params = {
        "key": api_key,
        "q": query,
        "per_page": per_page,
        "safesearch": "true",
    }

    try:
        resp = requests.get(PIXABAY_VIDEO_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[VideoSearch] Pixabay request failed: {e}")
        return None

    hits = data.get("hits", [])
    if not hits:
        return None

    query_terms = _extract_terms(query)
    best = None

    for hit in hits:
        duration = int(hit.get("duration", 0) or 0)
        videos = hit.get("videos", {})
        variants = []
        for key in ("large", "medium", "small", "tiny"):
            variant = videos.get(key)
            if variant and variant.get("url"):
                variants.append(variant)

        if not variants:
            continue

        variants.sort(
            key=lambda v: (int(v.get("width", 0) or 0) * int(v.get("height", 0) or 0)),
            reverse=True,
        )
        selected = variants[0]

        metadata_text = " ".join([
            str(hit.get("tags", "")),
            str(hit.get("user", "")),
            str(hit.get("type", "")),
        ])
        relevance = _text_relevance_score(query_terms, metadata_text)
        duration_score = max(0.0, 25.0 - abs(duration - min_duration) * 2.0)
        resolution_score = min(25.0, (int(selected.get("width", 0) or 0) * int(selected.get("height", 0) or 0)) / 150000.0)
        total_score = relevance * 12.0 + duration_score + resolution_score

        if best is None or total_score > best["score"]:
            best = {"url": selected.get("url"), "score": total_score}

    return best


def _build_query_candidates(keywords: str, context_text: str, fallback_keywords: str) -> list[str]:
    keyword_terms = _extract_terms(keywords)
    context_terms = _extract_terms(context_text)

    all_terms = []
    for term in keyword_terms + context_terms:
        if term not in all_terms:
            all_terms.append(term)

    candidates = []
    if keyword_terms:
        candidates.append(" ".join(keyword_terms[:3]))
    if all_terms:
        candidates.append(" ".join(all_terms[:2]))
        candidates.append(" ".join(all_terms[:3]))
        candidates.append(" ".join(all_terms[:4]))
    if fallback_keywords:
        candidates.append(fallback_keywords)

    seen = set()
    unique = []
    for candidate in candidates:
        c = re.sub(r"\s+", " ", candidate).strip()
        if not c or c in seen:
            continue
        seen.add(c)
        unique.append(c)

    return unique or [fallback_keywords]


def _extract_terms(text: str, max_terms: int = 12) -> list[str]:
    words = re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{3,}\b", (text or "").lower())
    terms = []
    for word in words:
        if word in STOP_WORDS:
            continue
        if word not in terms:
            terms.append(word)
        if len(terms) >= max_terms:
            break
    return terms


def _text_relevance_score(query_terms: list[str], metadata_text: str) -> float:
    if not query_terms:
        return 0.0

    metadata_terms = set(_extract_terms(metadata_text, max_terms=60))
    if not metadata_terms:
        return 0.0

    hits = sum(1 for term in query_terms if term in metadata_terms)
    return hits / max(1, len(query_terms))
