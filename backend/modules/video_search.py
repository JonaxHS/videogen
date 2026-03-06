"""
Video Search Module — Pexels + Pixabay + NASA APIs
Searches and downloads stock video clips matching a keyword query.
"""
import hashlib
import re
import requests
from pathlib import Path
from typing import Optional

PEXELS_API_BASE = "https://api.pexels.com/videos"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"
NASA_SEARCH_API = "https://images-api.nasa.gov/search"
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

    info = search_and_download_video_info(
        keywords=keywords,
        output_path=output_path,
        pexels_api_key=pexels_api_key,
        pixabay_api_key=pixabay_api_key,
        context_text=context_text,
        min_duration=min_duration,
        fallback_keywords=fallback_keywords,
        exclude_urls=exclude_urls,
    )
    return info["path"]


def search_and_download_video_info(
    keywords: str,
    output_path: str,
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    context_text: str = "",
    min_duration: int = 5,
    fallback_keywords: str = "nature landscape",
    exclude_urls: set[str] | None = None,
) -> dict:
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
    local_path = download_video_from_url(top["url"], provider_hint=top.get("provider", "manual"))
    return {
        "path": local_path,
        "provider": top.get("provider", "manual"),
        "url": top.get("url", ""),
    }


def infer_provider_from_url(url: str) -> str:
    value = (url or "").lower()
    if not value:
        return "manual"
    if "nasa.gov" in value or "images-api.nasa.gov" in value or "images-assets.nasa.gov" in value:
        return "nasa"
    if "pexels.com" in value:
        return "pexels"
    if "pixabay.com" in value:
        return "pixabay"
    return "manual"


def search_video_options(
    keywords: str,
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    context_text: str = "",
    min_duration: int = 5,
    fallback_keywords: str = "nature landscape",
    limit: int = 8,
    global_search: bool = False,
    page: int = 1,
    exclude_urls: set[str] | None = None,
) -> list[dict]:
    """Return ranked video options from configured providers for manual segment replacement."""
    # NASA is public (no API key required), so we always keep it as optional provider.
    # If keys are missing, NASA can still return results.

    providers = []
    if pexels_api_key:
        providers.append(("pexels", pexels_api_key))
    if pixabay_api_key:
        providers.append(("pixabay", pixabay_api_key))
    providers.append(("nasa", ""))

    exclude_urls = exclude_urls or set()
    effective_context = "" if global_search else context_text
    effective_fallback = (
        "cinematic broll nature technology city abstract"
        if global_search and not (fallback_keywords or "").strip()
        else fallback_keywords
    )
    query_candidates = _build_query_candidates(keywords, effective_context, effective_fallback)
    translated_terms_for_nasa = _translate_terms(_extract_terms(f"{keywords} {context_text}"))

    if global_search:
        extra_global = [
            "cinematic broll",
            "abstract background",
            "nature landscape",
            "city night",
            "technology future",
        ]
        for query in extra_global:
            if query not in query_candidates:
                query_candidates.append(query)

    pexels_per_page = 40 if global_search else 20
    pixabay_per_page = 50 if global_search else 25
    nasa_per_page = 14 if global_search else 8

    all_candidates = []
    nasa_query_candidates = []

    for candidate in query_candidates:
        if candidate and candidate not in nasa_query_candidates:
            nasa_query_candidates.append(candidate)

    if translated_terms_for_nasa:
        for size in (2, 3, 4, 6):
            phrase = " ".join(translated_terms_for_nasa[:size]).strip()
            if phrase and phrase not in nasa_query_candidates:
                nasa_query_candidates.append(phrase)

    astronomy_defaults = [
        "nasa space telescope",
        "galaxy nebula stars",
        "moon mars earth orbit",
        "astronaut spacewalk iss",
        "cosmos universe deep space",
    ]
    for phrase in astronomy_defaults:
        if phrase not in nasa_query_candidates:
            nasa_query_candidates.append(phrase)

    # Query NASA first to maximize astronomy relevance.
    for query_index, query in enumerate(nasa_query_candidates):
        if query_index >= (8 if global_search else 5):
            break
        all_candidates.extend(
            _search_nasa_candidates(
                query,
                min_duration,
                per_page=nasa_per_page,
                page=page,
            )
        )

    for query_index, query in enumerate(query_candidates):
        for provider_name, provider_key in providers:
            if provider_name == "nasa":
                continue
            if provider_name == "pexels":
                all_candidates.extend(
                    _search_pexels_candidates(
                        query,
                        provider_key,
                        min_duration,
                        per_page=pexels_per_page,
                        page=page,
                    )
                )
            elif provider_name == "pixabay":
                all_candidates.extend(
                    _search_pixabay_candidates(
                        query,
                        provider_key,
                        min_duration,
                        per_page=pixabay_per_page,
                        page=page,
                    )
                )
            else:
                all_candidates.extend(
                    _search_pixabay_candidates(
                        query,
                        provider_key,
                        min_duration,
                        per_page=pixabay_per_page,
                        page=page,
                    )
                )

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

    ranked = sorted(
        best_by_url.values(),
        key=lambda c: (
            1 if c.get("provider") == "nasa" else 0,
            c.get("score", 0),
        ),
        reverse=True,
    )
    limited = ranked[: max(1, limit)]

    # Ensure NASA appears in global searches when available (useful for astronomy-focused reels)
    if global_search and limited:
        nasa_in_limited = any((c.get("provider") == "nasa") for c in limited)
        if not nasa_in_limited:
            nasa_candidates = [c for c in ranked if c.get("provider") == "nasa"]
            if nasa_candidates:
                # Replace the last item with the best NASA candidate for provider diversity
                limited[-1] = nasa_candidates[0]

    # Last fallback: if NASA still didn't yield anything and result set is empty, run a broad NASA query.
    if not limited:
        fallback_nasa = _search_nasa_candidates(
            "nasa astronomy deep space",
            min_duration=min_duration,
            per_page=max(6, nasa_per_page),
            page=1,
        )
        if fallback_nasa:
            return fallback_nasa[: max(1, limit)]

    return limited


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
    page: int = 1,
) -> list[dict]:
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "size": "medium",
        "per_page": per_page,
        "page": max(1, int(page)),
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
    page: int = 1,
) -> list[dict]:
    params = {
        "key": api_key,
        "q": query,
        "per_page": per_page,
        "page": max(1, int(page)),
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

        # Use Pixabay's previewURL for thumbnail (it's a valid image URL)
        thumbnail = hit.get("previewURL", "")

        candidates.append({
            "provider": "pixabay",
            "url": selected_url,
            "thumbnail": thumbnail,
            "score": total_score,
            "duration": duration,
        })

    return sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)


def _search_nasa_candidates(
    query: str,
    min_duration: int,
    per_page: int = 10,
    page: int = 1,
) -> list[dict]:
    params = {
        "q": query,
        "media_type": "video",
        "page": max(1, int(page)),
    }

    try:
        resp = requests.get(NASA_SEARCH_API, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json() or {}
    except Exception as e:
        print(f"[VideoSearch] NASA search request failed: {e}")
        return []

    items = (((payload.get("collection") or {}).get("items")) or [])
    if not items:
        return []

    query_terms = _extract_terms(query)
    candidates = []

    for item in items[: max(1, per_page)]:
        data_list = item.get("data") or []
        data = data_list[0] if data_list else {}
        nasa_id = str(data.get("nasa_id", "")).strip()
        if not nasa_id:
            continue

        asset_url = _resolve_nasa_asset_video_url(nasa_id)
        if not asset_url:
            continue

        links = item.get("links") or []
        thumbnail = ""
        for link in links:
            href = str(link.get("href", ""))
            if href and href.startswith("http"):
                thumbnail = href
                break

        metadata_text = " ".join([
            str(data.get("title", "")),
            str(data.get("description", "")),
            " ".join([str(k) for k in (data.get("keywords") or [])]),
            query,
        ])

        relevance = _text_relevance_score(query_terms, metadata_text)
        quality_bonus = 0.0
        lower_url = asset_url.lower()
        if "1080" in lower_url or "4k" in lower_url or "2160" in lower_url:
            quality_bonus += 12.0
        elif "720" in lower_url:
            quality_bonus += 8.0
        elif "480" in lower_url:
            quality_bonus += 4.0

        # NASA API doesn't reliably provide duration in search payload.
        estimated_duration = max(min_duration, 8)
        total_score = relevance * 14.0 + quality_bonus

        candidates.append({
            "provider": "nasa",
            "url": asset_url,
            "thumbnail": thumbnail,
            "score": total_score,
            "duration": estimated_duration,
        })

    return sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)


def _resolve_nasa_asset_video_url(nasa_id: str) -> Optional[str]:
    if not nasa_id:
        return None

    asset_endpoint = f"https://images-api.nasa.gov/asset/{nasa_id}"
    try:
        resp = requests.get(asset_endpoint, timeout=20)
        resp.raise_for_status()
        payload = resp.json() or {}
    except Exception as e:
        print(f"[VideoSearch] NASA asset request failed for {nasa_id}: {e}")
        return None

    items = (((payload.get("collection") or {}).get("items")) or [])
    if not items:
        return None

    urls = []
    for it in items:
        href = str((it or {}).get("href", ""))
        if href.startswith("http") and ".mp4" in href.lower():
            urls.append(href)

    if not urls:
        return None

    def quality_key(url: str) -> tuple[int, int]:
        value = url.lower()
        score = 0
        if "orig" in value:
            score += 50
        if "4k" in value or "2160" in value:
            score += 40
        if "1080" in value:
            score += 30
        if "720" in value:
            score += 20
        if "480" in value:
            score += 10
        return score, len(url)

    urls.sort(key=quality_key, reverse=True)
    return urls[0]


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
