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

TERM_MAP = {
    # Astronomy/Space
    "estrella": "star",
    "estrellas": "stars",
    "galaxia": "galaxy",
    "universo": "universe",
    "planeta": "planet",
    "espacio": "space",
    "lunar": "moon",
    "luna": "moon",
    "sol": "sun",
    "meteorito": "meteor",
    "cometa": "comet",
    
    # Science/Physics
    "átomo": "atom",
    "atomo": "atom",
    "energía": "energy",
    "energia": "energy",
    "tiempo": "time",
    "ciencia": "science",
    "ley": "law",
    "leyes": "laws",
    "terminámica": "thermodynamics",
    "termodinamica": "thermodynamics",
    "física": "physics",
    "fisica": "physics",
    "caos": "chaos",
    "orden": "order",
    
    # Technology
    "tecnología": "technology",
    "tecnologia": "technology",
    "inteligencia": "intelligence",
    "artificial": "artificial",
    "robot": "robot",
    "digital": "digital",
    "computadora": "computer",
    "máquina": "machine",
    "maquina": "machine",
    
    # Nature
    "naturaleza": "nature",
    "océano": "ocean",
    "oceano": "ocean",
    "bosque": "forest",
    "árbol": "tree",
    "arbol": "tree",
    "árboles": "trees",
    "arboles": "trees",
    "montaña": "mountain",
    "montana": "mountain",
    "río": "river",
    "rio": "river",
    "lluvia": "rain",
    "agua": "water",
    "fuego": "fire",
    "tierra": "earth",
    "suelo": "ground",
    "paisaje": "landscape",
    "planta": "plant",
    "flores": "flowers",
    "flor": "flower",
    
    # Human/Society
    "humano": "human",
    "humanidad": "humanity",
    "personas": "people",
    "persona": "person",
    "sociedad": "society",
    "cultura": "culture",
    "familia": "family",
    "comunidad": "community",
    "población": "population",
    "poblacion": "population",
    
    # Conflict/Peace
    "guerra": "war",
    "paz": "peace",
    "conflicto": "conflict",
    "batalla": "battle",
    "violencia": "violence",
    
    # Economy/Money
    "economía": "economy",
    "economia": "economy",
    "dinero": "money",
    "dineros": "money",
    "riqueza": "wealth",
    "pobreza": "poverty",
    "comercio": "commerce",
    
    # Health/Medicine
    "salud": "health",
    "médico": "medical",
    "medico": "medical",
    "medicina": "medicine",
    "hospital": "hospital",
    "enfermedad": "disease",
    "dolencia": "ailment",
    "cura": "cure",
    
    # Time/History
    "futuro": "future",
    "pasado": "past",
    "presente": "present",
    "historia": "history",
    "tiempo": "time",
    "era": "era",
    "época": "epoch",
    "epuca": "epoch",
    
    # Abstract Concepts
    "caos": "chaos",
    "orden": "order",
    "libertad": "freedom",
    "justicia": "justice",
    "verdad": "truth",
    "mentira": "lie",
    "amor": "love",
    "miedo": "fear",
    "esperanza": "hope",
    "alegría": "joy",
    "alegria": "joy",
    "tristeza": "sadness",
    "belleza": "beauty",
    "fealdad": "ugliness",
    
    # Geography/Places
    "ciudad": "city",
    "campo": "countryside",
    "rural": "rural",
    "isla": "island",
    "desierto": "desert",
    "glaciar": "glacier",
    "volcán": "volcano",
    "volcan": "volcano",
    "cueva": "cave",
    "playa": "beach",
    "costa": "coast",
    
    # Action/Movement
    "movimiento": "movement",
    "movimiento": "movement",
    "velocidad": "speed",
    "correr": "run",
    "saltar": "jump",
    "volar": "fly",
    "nadar": "swim",
    "caer": "fall",
    "subir": "climb",
    
    # Color/Light
    "luz": "light",
    "oscuridad": "darkness",
    "color": "color",
    "rojo": "red",
    "azul": "blue",
    "verde": "green",
    "amarillo": "yellow",
    "blanco": "white",
    "negro": "black",
}


def search_and_download_video(
    keywords: str,
    output_path: str,
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    context_text: str = "",
    min_duration: int = 5,
    fallback_keywords: str = "nature landscape",
    exclude_urls: set[str] | None = None,
) -> str:
    """
    Search Pexels/Pixabay for a video matching keywords and download it.
    Uses local cache to avoid redundant downloads.
    Returns path to downloaded video file.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not pexels_api_key and not pixabay_api_key:
        raise RuntimeError("No video provider API key configured (Pexels or Pixabay)")

    options = search_video_options(
        keywords=keywords,
        pexels_api_key=pexels_api_key,
        pixabay_api_key=pixabay_api_key,
        context_text=context_text,
        min_duration=min_duration,
        fallback_keywords=fallback_keywords,
        limit=1,
        exclude_urls=exclude_urls,
    )

    if not options:
        raise RuntimeError(f"No video found for keywords: '{keywords}'")
    top = options[0]
    return download_video_from_url(top["url"], provider_hint=top.get("provider", "manual"))


def search_video_options(
    keywords: str,
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    context_text: str = "",
    min_duration: int = 5,
    fallback_keywords: str = "nature landscape",
    limit: int = 8,
    exclude_urls: set[str] | None = None,
) -> list[dict]:
    """Return ranked video options from configured providers for manual segment replacement."""
    if not pexels_api_key and not pixabay_api_key:
        raise RuntimeError("No video provider API key configured (Pexels or Pixabay)")

    providers = []
    if pexels_api_key:
        providers.append(("pexels", pexels_api_key))
    if pixabay_api_key:
        providers.append(("pixabay", pixabay_api_key))

    exclude_urls = exclude_urls or set()
    query_candidates = _build_query_candidates(keywords, context_text, fallback_keywords)

    all_candidates = []
    for query in query_candidates:
        for provider_name, provider_key in providers:
            if provider_name == "pexels":
                all_candidates.extend(_search_pexels_candidates(query, provider_key, min_duration))
            else:
                all_candidates.extend(_search_pixabay_candidates(query, provider_key, min_duration))

    best_by_url: dict[str, dict] = {}
    for candidate in all_candidates:
        url = candidate.get("url")
        provider = candidate.get("provider", "manual")
        if not url:
            continue

        cache_hash = hashlib.md5(f"{provider}:{url}".encode()).hexdigest()
        if (
            url in exclude_urls
            or cache_hash in exclude_urls
            or f"{cache_hash}.mp4" in exclude_urls
        ):
            continue

        prev = best_by_url.get(url)
        if prev is None or candidate.get("score", 0) > prev.get("score", 0):
            best_by_url[url] = candidate

    ranked = sorted(best_by_url.values(), key=lambda c: c.get("score", 0), reverse=True)
    return ranked[: max(1, limit)]


def download_video_from_url(video_url: str, provider_hint: str = "manual") -> str:
    """Download and cache a video by URL, returning local path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = f"{provider_hint}:{video_url}"
    url_hash = hashlib.md5(cache_key.encode()).hexdigest()
    cached_path = CACHE_DIR / f"{url_hash}.mp4"

    if cached_path.exists():
        return str(cached_path)

    try:
        # Add headers to avoid blocking by CDNs
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(video_url, stream=True, timeout=60, headers=headers)
        response.raise_for_status()

        with open(cached_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = cached_path.stat().st_size
        if file_size < 1000:  # Less than 1KB is likely an error page
            cached_path.unlink()
            raise RuntimeError(f"Downloaded file too small ({file_size} bytes), likely error page")

        return str(cached_path)
    except Exception as e:
        # Clean up failed download
        if cached_path.exists():
            try:
                cached_path.unlink()
            except Exception:
                pass
        print(f"[VideoSearch] Failed to download video from {provider_hint}: {e}")
        raise


def _search_pexels(
    query: str,
    api_key: str,
    min_duration: int,
    per_page: int = 20,
    exclude_urls: set[str] | None = None,
) -> dict | None:
    """
    Search Pexels API and return best candidate with score + URL.
    Scoring balances textual relevance + duration + resolution.
    """
    candidates = _search_pexels_candidates(query, api_key, min_duration, per_page=per_page)
    exclude_urls = exclude_urls or set()
    for candidate in candidates:
        if candidate.get("url") not in exclude_urls:
            return {"url": candidate["url"], "score": candidate.get("score", 0)}
    return None


def _search_pexels_candidates(
    query: str,
    api_key: str,
    min_duration: int,
    per_page: int = 20,
) -> list[dict]:
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
        return []

    videos = data.get("videos", [])
    if not videos:
        return []

    query_terms = _extract_terms(query)
    candidates = []

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

        pictures = video.get("video_pictures", []) or []
        thumbnail = pictures[0].get("picture") if pictures and isinstance(pictures[0], dict) else ""

        metadata_text = " ".join([
            str(video.get("url", "")),
            str((video.get("user") or {}).get("name", "")),
            str(video.get("id", "")),
            query,
        ])

        relevance = _text_relevance_score(query_terms, metadata_text)
        duration_score = max(0.0, 25.0 - abs(duration - min_duration) * 2.0)
        resolution_score = min(25.0, (int(selected.get("width", 0) or 0) * int(selected.get("height", 0) or 0)) / 150000.0)
        total_score = relevance * 10.0 + duration_score + resolution_score

        candidates.append({
            "provider": "pexels",
            "url": link,
            "thumbnail": thumbnail,
            "score": total_score,
            "duration": duration,
        })

    return sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)


def _search_pixabay(
    query: str,
    api_key: str,
    min_duration: int,
    per_page: int = 25,
    exclude_urls: set[str] | None = None,
) -> dict | None:
    """
    Search Pixabay videos API and return best candidate with score + URL.
    """
    candidates = _search_pixabay_candidates(query, api_key, min_duration, per_page=per_page)
    exclude_urls = exclude_urls or set()
    for candidate in candidates:
        if candidate.get("url") not in exclude_urls:
            return {"url": candidate["url"], "score": candidate.get("score", 0)}
    return None


def _search_pixabay_candidates(
    query: str,
    api_key: str,
    min_duration: int,
    per_page: int = 25,
) -> list[dict]:
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
        return []

    hits = data.get("hits", [])
    if not hits:
        return []

    query_terms = _extract_terms(query)
    candidates = []

    for hit in hits:
        duration = int(hit.get("duration", 0) or 0)
        if duration < min_duration:
            continue
            
        videos = hit.get("videos", {})
        variants = []
        
        # Prefer larger video sizes in order
        for key in ("large", "medium", "small", "tiny"):
            variant = videos.get(key)
            if variant and variant.get("url"):
                variants.append(variant)

        if not variants:
            continue

        # Sort by resolution
        variants.sort(
            key=lambda v: (int(v.get("width", 0) or 0) * int(v.get("height", 0) or 0)),
            reverse=True,
        )
        selected = variants[0]
        selected_url = selected.get("url")
        
        if not selected_url or not selected_url.startswith("http"):
            continue

        metadata_text = " ".join([
            str(hit.get("tags", "")),
            str(hit.get("user", "")),
            str(hit.get("type", "")),
            query,
        ])
        relevance = _text_relevance_score(query_terms, metadata_text)
        duration_score = max(0.0, 25.0 - abs(duration - min_duration) * 2.0)
        resolution_score = min(25.0, (int(selected.get("width", 0) or 0) * int(selected.get("height", 0) or 0)) / 150000.0)
        total_score = relevance * 12.0 + duration_score + resolution_score

        # Use Pixabay's preview image if available
        thumbnail = hit.get("previewURL", "")
        if not thumbnail:
            thumbnail = f"https://i.vimeocdn.com/video/{hit.get('picture_id', '')}_640x360.jpg"

        candidates.append({
            "provider": "pixabay",
            "url": selected_url,
            "thumbnail": thumbnail,
            "score": total_score,
            "duration": duration,
        })

    return sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)


def _build_query_candidates(keywords: str, context_text: str, fallback_keywords: str) -> list[str]:
    keyword_terms = _extract_terms(keywords)
    context_terms = _extract_terms(context_text)
    translated_terms = _translate_terms(keyword_terms + context_terms)

    all_terms = []
    for term in keyword_terms + context_terms:
        if term not in all_terms:
            all_terms.append(term)

    candidates = []
    
    # Multi-keyword searches first (best results)
    if keyword_terms:
        candidates.append(" ".join(keyword_terms[:3]))
        candidates.append(" ".join(keyword_terms[:4]))
        candidates.append(" ".join(keyword_terms[:6]))  # Increased to use all 6 primary keywords
    
    # Combined keyword + context searches
    if all_terms:
        candidates.append(" ".join(all_terms[:3]))
        candidates.append(" ".join(all_terms[:4]))
        candidates.append(" ".join(all_terms[:5]))
    
    # Translated (English) searches for broader results
    if translated_terms:
        candidates.append(" ".join(translated_terms[:3]))
        candidates.append(" ".join(translated_terms[:4]))
        candidates.append(" ".join(translated_terms[:6]))
    
    # Individual keyword searches (fallback for exact matches)
    for i, term in enumerate(keyword_terms[:4]):
        if term not in [c for candidate in candidates for c in candidate.split()]:
            candidates.append(term)
    
    # Fallback
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


def _translate_terms(terms: list[str]) -> list[str]:
    translated = []
    for term in terms:
        mapped = TERM_MAP.get(term.lower())
        if mapped and mapped not in translated:
            translated.append(mapped)
    return translated


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
