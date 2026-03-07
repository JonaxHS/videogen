"""
Video Search Module — Pexels + Pixabay + NASA + ESA APIs
Searches and downloads stock video clips matching a keyword query.
Uses local semantic embeddings for intelligent video matching.
"""
import hashlib
import re
import os
import json
import random
import base64
import subprocess
import shutil
import requests
from pathlib import Path
from typing import Optional
import numpy as np
from datetime import datetime, timedelta

PEXELS_API_BASE = "https://api.pexels.com/videos"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"
NASA_SEARCH_API = "https://images-api.nasa.gov/search"
ESA_SEARCH_API = "https://www.esa.int/ESA_Multimedia/Videos"
CACHE_DIR = Path("/app/cache/videos")

# Semantic embedding model (lazy-loaded)
_EMBEDDING_MODEL = None

def _get_embedding_model():
    """Lazy-load the embedding model on first use."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("[VideoSearch] Loading semantic embedding model...")
            _EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
            print("[VideoSearch] Semantic model loaded successfully")
        except Exception as e:
            print(f"[VideoSearch] Failed to load semantic model: {e}")
            _EMBEDDING_MODEL = False  # Mark as unavailable
    return _EMBEDDING_MODEL if _EMBEDDING_MODEL is not False else None


def _detect_intro_seconds(title: str, description: str) -> float:
    """
    Detect if a video likely has an intro and estimate its duration in seconds.
    Returns skip_seconds (0 if no intro detected, 1-5 if detected).
    """
    text = f"{title} {description}".lower()
    
    # Keyword heuristic check
    keyword_count = sum(1 for kw in INTRO_KEYWORDS if kw in text)
    if keyword_count == 0:
        return 0.0
    
    # Try semantic matching
    model = _get_embedding_model()
    if model:
        try:
            intro_embedding = model.encode("intro opening video start title sequence", convert_to_numpy=True)
            text_embedding = model.encode(text[:500], convert_to_numpy=True)  # First 500 chars
            
            similarity = np.dot(intro_embedding, text_embedding) / (
                np.linalg.norm(intro_embedding) * np.linalg.norm(text_embedding) + 1e-8
            )
            # Normalize to [0, 1]
            similarity_score = (float(similarity) + 1.0) / 2.0
            
            if similarity_score > 0.65:
                # Estimate intro duration based on keywords
                if any(x in text for x in ["long intro", "intro largo", "opening sequence"]):
                    return 5.0
                elif any(x in text for x in ["intro", "opening", "titles", "créditos"]):
                    return 3.0
                else:
                    return 1.5
        except Exception as e:
            print(f"[VideoSearch] Intro detection semantic scoring failed: {e}")
    
    # Fallback: keyword-based estimation
    if keyword_count >= 2:
        return 3.0
    elif keyword_count >= 1:
        return 1.5
    
    return 0.0

_NASA_ASSET_CACHE: dict[str, Optional[str]] = {}
_NASA_QUERY_CACHE: dict[tuple[str, int, int], list[dict]] = {}
_ESA_QUERY_CACHE: dict[tuple[str, int, int], list[dict]] = {}
_ESA_DETAIL_CACHE: dict[str, Optional[dict]] = {}


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# Auto-cleanup configuration (strict defaults for VPS stability)
ENABLE_AUTO_CACHE_CLEANUP = _bool_env("ENABLE_AUTO_CACHE_CLEANUP", False)  # Disabled by default to prevent race conditions
MAX_CACHE_SIZE_MB = int(os.getenv("MAX_CACHE_SIZE_MB", "800"))  # Default 800MB
MAX_FILE_AGE_DAYS = int(os.getenv("MAX_FILE_AGE_DAYS", "1"))  # Default 1 day
MAX_FILE_AGE_HOURS = int(os.getenv("MAX_FILE_AGE_HOURS", "12"))  # If >0, overrides days
CACHE_CLEANUP_INTERVAL_SECONDS = int(os.getenv("CACHE_CLEANUP_INTERVAL_SECONDS", "30"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_VIDEO_RERANK_MODEL = os.getenv("OLLAMA_VIDEO_RERANK_MODEL", "qwen2.5:7b-instruct")
OLLAMA_VIDEO_VISION_MODEL = os.getenv("OLLAMA_VIDEO_VISION_MODEL", "qwen2.5vl:7b")
ENABLE_QWEN_VIDEO_RERANK = _bool_env("ENABLE_QWEN_VIDEO_RERANK", False)  # Default: False (Ollama disabled)
ENABLE_QWEN_VIDEO_VISUAL_RERANK = _bool_env("ENABLE_QWEN_VIDEO_VISUAL_RERANK", False)  # Default: False
QWEN_VIDEO_RERANK_TOP_K = int(os.getenv("QWEN_VIDEO_RERANK_TOP_K", "6"))
QWEN_VIDEO_VISUAL_TOP_K = int(os.getenv("QWEN_VIDEO_VISUAL_TOP_K", "2"))
QWEN_VIDEO_VISUAL_MAX_FRAMES = int(os.getenv("QWEN_VIDEO_VISUAL_MAX_FRAMES", "1"))
QWEN_VIDEO_VISUAL_WEIGHT = float(os.getenv("QWEN_VIDEO_VISUAL_WEIGHT", "18"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.22"))
MIN_RELEVANCE_SCORE_GLOBAL = float(os.getenv("MIN_RELEVANCE_SCORE_GLOBAL", "0.16"))
_LAST_CLEANUP_TIME = datetime.now()
_FFMPEG_AVAILABLE: Optional[bool] = None


def _cleanup_cache_if_needed(force: bool = False):
    """
    Automatically clean up cache if it exceeds size limit or files are too old.
    Runs at most every CACHE_CLEANUP_INTERVAL_SECONDS unless force=True.
    Only runs automatically if ENABLE_AUTO_CACHE_CLEANUP=true (disabled by default).
    """
    global _LAST_CLEANUP_TIME
    
    # Skip automatic cleanup if disabled (manual cleanup via force=True always works)
    if not force and not ENABLE_AUTO_CACHE_CLEANUP:
        return
    
    now = datetime.now()
    if not force and (now - _LAST_CLEANUP_TIME).total_seconds() < CACHE_CLEANUP_INTERVAL_SECONDS:
        return  # Skip if cleanup ran recently
    
    _LAST_CLEANUP_TIME = now
    
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Calculate current cache size
        total_size = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file())
        total_size_mb = total_size / (1024 * 1024)
        
        # Check size limit
        if total_size_mb > MAX_CACHE_SIZE_MB:
            print(f"[Cache] Size {total_size_mb:.1f}MB exceeds limit {MAX_CACHE_SIZE_MB}MB. Cleaning...")
            _cleanup_old_files(target_mb=MAX_CACHE_SIZE_MB * 0.8)  # Clean to 80% of limit
        
        # Check file age (hours override days when configured)
        file_age_delta = timedelta(hours=MAX_FILE_AGE_HOURS) if MAX_FILE_AGE_HOURS > 0 else timedelta(days=MAX_FILE_AGE_DAYS)
        cutoff_time = (now - file_age_delta).timestamp()
        for file_path in CACHE_DIR.rglob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                try:
                    file_path.unlink()
                    print(f"[Cache] Removed old file: {file_path.name}")
                except Exception as e:
                    print(f"[Cache] Error removing {file_path.name}: {e}")
    
    except Exception as e:
        print(f"[Cache] Cleanup error: {e}")


def _cleanup_old_files(target_mb: float):
    """Remove oldest files until cache is below target size."""
    if not CACHE_DIR.exists():
        return
    
    current_size = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file()) / (1024 * 1024)
    if current_size <= target_mb:
        return
    
    # Get files sorted by modification time (oldest first)
    files = sorted(
        (f for f in CACHE_DIR.rglob("*") if f.is_file()),
        key=lambda f: f.stat().st_mtime
    )
    
    for file_path in files:
        if current_size <= target_mb:
            break
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        try:
            file_path.unlink()
            current_size -= file_size_mb
            print(f"[Cache] Removed: {file_path.name} ({file_size_mb:.1f}MB)")
        except Exception as e:
            print(f"[Cache] Error removing {file_path.name}: {e}")

# Intro detection patterns
INTRO_KEYWORDS = {
    "intro", "opening", "títulos", "créditos", "credits", "presentación", "presentation",
    "theme", "music", "soundtrack", "logo", "logotipo", "channel", "canal",
    "watermark", "marca de agua", "subscribe", "suscribirse", "like", "me gusta",
    "disclaimer", "aviso", "warning", "advertencia", "preview", "adelanto",
    "teaser", "preamble", "preámbulo", "bumper", "slate", "countdown"
}

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

# Semantic expansion: related terms for better video discovery
SEMANTIC_EXPANSION = {
    "space": ["cosmos", "universe", "galaxy", "nebula", "stars"],
    "espacio": ["cosmos", "universo", "galaxia", "estrellas"],
    "ocean": ["sea", "water", "waves", "marine", "underwater"],
    "oceano": ["mar", "agua", "olas", "marino"],
    "technology": ["digital", "innovation", "future", "computer", "ai"],
    "tecnologia": ["digital", "innovacion", "futuro", "computadora"],
    "city": ["urban", "downtown", "skyline", "street", "building"],
    "ciudad": ["urbano", "edificios", "calle"],
    "nature": ["forest", "landscape", "wildlife", "environment", "earth"],
    "naturaleza": ["bosque", "paisaje", "ambiente", "tierra"],
    "science": ["research", "laboratory", "experiment", "discovery"],
    "ciencia": ["investigacion", "laboratorio", "experimento"],
    "energy": ["power", "electricity", "solar", "wind", "renewable"],
    "energia": ["poder", "electricidad", "solar", "renovable"],
    "health": ["medical", "wellness", "fitness", "medicine", "care"],
    "salud": ["medico", "bienestar", "medicina", "cuidado"],
    "time": ["clock", "watch", "hour", "moment", "history"],
    "tiempo": ["reloj", "hora", "momento", "historia"],
    "people": ["human", "person", "crowd", "society", "community"],
    "personas": ["humano", "gente", "sociedad", "comunidad"],
}

# Provider routing: which providers work best for specific topics
PROVIDER_PREFERENCES = {
    "nasa": ["space", "espacio", "planet", "planeta", "galaxy", "galaxia", "moon", "luna", 
             "mars", "earth", "tierra", "solar", "star", "estrella", "cosmos", "universe", 
             "universo", "astronaut", "astronauta", "satellite", "satelite", "orbit", "orbita",
             "telescope", "telescopio", "nebula", "hubble"],
    "esa": ["space", "espacio", "planet", "planeta", "galaxy", "galaxia", "earth", "tierra",
            "satellite", "satelite", "orbit", "mars", "telescope", "telescopio", "cosmos",
            "astronaut", "astronauta", "rocket", "cohete"],
    "pexels": ["city", "ciudad", "people", "personas", "business", "negocio", "nature", 
               "naturaleza", "urban", "urbano", "lifestyle", "trabajo", "office", "oficina",
               "food", "comida", "travel", "viaje", "fashion", "moda"],
    "pixabay": ["abstract", "abstracto", "background", "fondo", "animation", "animacion",
                "technology", "tecnologia", "digital", "nature", "naturaleza", "concept",
                "concepto", "graphic", "grafico"],
}

def _get_semantic_expansions(terms: list[str], max_expansions: int = 3) -> list[str]:
    """Expand search terms with related semantic keywords."""
    expansions = []
    for term in terms[:3]:  # Only expand first 3 terms
        related = SEMANTIC_EXPANSION.get(term.lower(), [])
        for rel in related[:max_expansions]:
            if rel not in expansions and rel not in terms:
                expansions.append(rel)
    return expansions

def _get_preferred_provider(keywords: str, context: str) -> str:
    """Determine which provider is likely to have best results for this query."""
    text = f"{keywords} {context}".lower()
    terms = _extract_terms(text)
    
    scores = {}
    for provider, pref_terms in PROVIDER_PREFERENCES.items():
        score = sum(1 for term in terms if any(pref in term or term in pref for pref in pref_terms))
        if score > 0:
            scores[provider] = score
    
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return "pexels"  # Default fallback

def _diversify_providers(candidates: list[dict], target_count: int) -> list[dict]:
    """
    Ensure provider diversity in results while maintaining quality.
    Prevents all results from being from the same source (e.g., all Pexels).
    """
    if len(candidates) < 2 or target_count < 2:
        return candidates
    
    # Group by provider
    by_provider = {}
    for candidate in candidates:
        provider = candidate.get("provider", "unknown")
        if provider not in by_provider:
            by_provider[provider] = []
        by_provider[provider].append(candidate)
    
    # If already diverse (3+ providers), return as-is
    if len(by_provider) >= 3:
        return candidates[:target_count]
    
    # Interleave providers to ensure variety
    diversified = []
    provider_lists = list(by_provider.values())
    max_iterations = max(len(lst) for lst in provider_lists)
    
    for i in range(max_iterations):
        for provider_list in provider_lists:
            if i < len(provider_list) and len(diversified) < target_count:
                diversified.append(provider_list[i])
    
    return diversified[:target_count]


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
    if "esa.int" in value or "esahubble.org" in value:
        return "esa"
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
    prefer_nasa: bool = False,
    page: int = 1,
    exclude_urls: set[str] | None = None,
    include_providers: set[str] | None = None,
    search_seed: str = "",
) -> list[dict]:
    """Return ranked video options from configured providers for manual segment replacement."""
    # Keep cache bounded even when requests reuse cached assets heavily.
    _cleanup_cache_if_needed()

    # NASA is public (no API key required), so we always keep it as optional provider.
    # If keys are missing, NASA can still return results.

    requested_providers = {p.lower().strip() for p in (include_providers or set()) if str(p).strip()}
    allowed_providers = requested_providers or {"pexels", "pixabay", "nasa", "esa"}

    providers = []
    if "pexels" in allowed_providers and pexels_api_key:
        providers.append(("pexels", pexels_api_key))
    if "pixabay" in allowed_providers and pixabay_api_key:
        providers.append(("pixabay", pixabay_api_key))
    if "nasa" in allowed_providers:
        providers.append(("nasa", ""))
    if "esa" in allowed_providers:
        providers.append(("esa", ""))

    use_nasa = "nasa" in allowed_providers
    use_esa = "esa" in allowed_providers

    exclude_urls = exclude_urls or set()
    effective_context = "" if global_search else context_text
    effective_fallback = (
        "cinematic broll nature technology city abstract"
        if global_search and not (fallback_keywords or "").strip()
        else fallback_keywords
    )
    query_candidates = _build_query_candidates(keywords, effective_context, effective_fallback)
    translated_terms_for_nasa = _translate_terms(_extract_terms(f"{keywords} {context_text}"))

    global_fallback_queries = [
        "cinematic broll",
        "abstract background",
        "nature landscape",
        "city night",
        "technology future",
    ] if global_search else []

    quick_mode = (not global_search) and limit <= 2
    pexels_per_page = 20 if quick_mode else (40 if global_search else 20)
    pixabay_per_page = 25 if quick_mode else (50 if global_search else 25)
    nasa_per_page = 6 if quick_mode else (20 if (global_search or prefer_nasa) else 10)

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

    nasa_first = prefer_nasa or global_search
    max_nasa_queries = 3 if quick_mode else (12 if (global_search or prefer_nasa) else 5)
    max_esa_queries = max_nasa_queries  # ESA gets same priority as NASA
    esa_per_page = nasa_per_page  # ESA gets same query volume as NASA

    if nasa_first:
        if use_nasa:
            # Search NASA
            for query_index, query in enumerate(nasa_query_candidates):
                if query_index >= max_nasa_queries:
                    break
                all_candidates.extend(
                    _search_nasa_candidates(
                        query,
                        min_duration,
                        per_page=nasa_per_page,
                        page=page,
                    )
                )
        if use_esa:
            # Search ESA alongside NASA
            for query_index, query in enumerate(nasa_query_candidates):
                if query_index >= max_esa_queries:
                    break
                all_candidates.extend(
                    _search_esa_candidates(
                        query,
                        min_duration,
                        per_page=esa_per_page,
                        page=page,
                    )
                )

    for query_index, query in enumerate(query_candidates):
        for provider_name, provider_key in providers:
            if provider_name == "nasa":
                continue
            if provider_name == "esa":
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

        if quick_mode and len(all_candidates) >= max(6, limit * 3):
            break

    if not nasa_first:
        if use_nasa:
            # Search NASA
            for query_index, query in enumerate(nasa_query_candidates):
                if query_index >= (2 if quick_mode else max_nasa_queries):
                    break
                all_candidates.extend(
                    _search_nasa_candidates(
                        query,
                        min_duration,
                        per_page=nasa_per_page,
                        page=page,
                    )
                )
        if use_esa:
            # Search ESA with same limits as NASA
            for query_index, query in enumerate(nasa_query_candidates):
                if query_index >= (2 if quick_mode else max_esa_queries):
                    break
                all_candidates.extend(
                    _search_esa_candidates(
                        query,
                        min_duration,
                        per_page=esa_per_page,
                        page=page,
                    )
                )

    # Only use broad generic queries as a fallback when the main intent produced too few options.
    if global_search and len(all_candidates) < max(4, limit * 2):
        for query in global_fallback_queries:
            for provider_name, provider_key in providers:
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
                elif provider_name == "nasa":
                    all_candidates.extend(
                        _search_nasa_candidates(
                            query,
                            min_duration,
                            per_page=nasa_per_page,
                            page=page,
                        )
                    )
                elif provider_name == "esa":
                    all_candidates.extend(
                        _search_esa_candidates(
                            query,
                            min_duration,
                            per_page=esa_per_page,
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

    # Intent guard: when relevance is too low, avoid returning arbitrary clips.
    filtered_candidates = []
    for candidate in best_by_url.values():
        relevance = float(candidate.get("relevance", 0.0) or 0.0)
        provider = str(candidate.get("provider", ""))
        threshold = MIN_RELEVANCE_SCORE_GLOBAL if global_search else MIN_RELEVANCE_SCORE
        if provider in {"nasa", "esa"}:
            threshold = max(0.0, threshold - 0.03)
        if relevance >= threshold:
            filtered_candidates.append(candidate)

    ranking_pool = filtered_candidates if filtered_candidates else list(best_by_url.values())
    
    # Smart provider boost: prioritize provider that best matches content type
    preferred_provider = _get_preferred_provider(keywords, context_text)
    for candidate in ranking_pool:
        if candidate.get("provider") == preferred_provider:
            # Boost score by 10% if from preferred provider
            candidate["score"] = candidate.get("score", 0) * 1.10

    ranked = sorted(
        ranking_pool,
        key=lambda c: (
            2 if (prefer_nasa and c.get("provider") in ("nasa", "esa")) else (1 if c.get("provider") in ("nasa", "esa") else 0),
            c.get("score", 0),
        ),
        reverse=True,
    )

    # Optional diversity for manual replacement UI: keep quality but avoid identical top ordering.
    if search_seed and ranked:
        window = min(40, len(ranked))
        top_window = ranked[:window]
        tail = ranked[window:]

        # Stable per request seed so same request is deterministic, different seed yields variety.
        seeded = []
        for candidate in top_window:
            key_raw = f"{search_seed}|{candidate.get('url', '')}".encode()
            key_val = int(hashlib.md5(key_raw).hexdigest()[:8], 16)
            jitter = (key_val % 1000) / 1000.0  # 0..0.999
            seeded.append((candidate, jitter))

        # Mostly preserve score, but break repetition when scores are close.
        seeded.sort(
            key=lambda item: (
                item[0].get("score", 0) + (item[1] * 0.6),
                item[0].get("provider", ""),
            ),
            reverse=True,
        )
        ranked = [item[0] for item in seeded] + tail

    # Optional Qwen reranker: improve final pick quality for low-limit selections
    # (e.g. automatic segment generation where limit=1).
    if ENABLE_QWEN_VIDEO_RERANK and len(ranked) > 1 and limit <= 3:
        query_text = (context_text or keywords or "").strip()
        top_k = max(2, min(QWEN_VIDEO_RERANK_TOP_K, len(ranked)))
        reranked = _qwen_rerank_candidates(query_text, ranked, top_k=top_k)
        if reranked:
            ranked = reranked

    # Optional visual reranker: Qwen evaluates sampled frames from candidate videos
    # against the segment text for better intent fidelity.
    if ENABLE_QWEN_VIDEO_VISUAL_RERANK and len(ranked) > 1 and limit <= 3:
        query_text = (context_text or keywords or "").strip()
        top_k = max(2, min(QWEN_VIDEO_VISUAL_TOP_K, len(ranked)))
        visually_reranked = _qwen_visual_rerank_candidates(query_text, ranked, top_k=top_k)
        if visually_reranked:
            ranked = visually_reranked

    limited = ranked[: max(1, limit)]
    
    # Provider diversification: ensure variety in results (avoid all videos from same source)
    if limit >= 4 and len(limited) >= 4:
        limited = _diversify_providers(limited, limit)

    # Ensure NASA/ESA appears in global searches when available (useful for astronomy-focused reels)
    if global_search and limited:
        space_in_limited = any((c.get("provider") in ("nasa", "esa")) for c in limited)
        if not space_in_limited:
            space_candidates = [
                c for c in ranked
                if (c.get("provider") == "nasa" and use_nasa) or (c.get("provider") == "esa" and use_esa)
            ]
            if space_candidates:
                # Replace the last item with the best NASA/ESA candidate for provider diversity
                limited[-1] = space_candidates[0]

    # Last fallback: if NASA still didn't yield anything and result set is empty, run a broad NASA query.
    if not limited and use_nasa:
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
    _cleanup_cache_if_needed()

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

        # Trigger automatic cache cleanup after successful download
        _cleanup_cache_if_needed()

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
        ])

        relevance = _text_relevance_score(query_terms, metadata_text)
        duration_score = max(0.0, 25.0 - abs(duration - min_duration) * 2.0)
        resolution_score = min(25.0, (int(selected.get("width", 0) or 0) * int(selected.get("height", 0) or 0)) / 150000.0)
        total_score = relevance * 10.0 + duration_score + resolution_score

        video_title = f"{selected.get('user', {}).get('name', '')} {selected.get('image', '')}"
        skip_seconds = _detect_intro_seconds(video_title, "")

        candidates.append({
            "provider": "pexels",
            "url": link,
            "thumbnail": thumbnail,
            "score": total_score,
            "relevance": relevance,
            "duration": duration,
            "title": str(video.get("url", "")),
            "description": str((video.get("user") or {}).get("name", "")),
            "skip_seconds": skip_seconds,
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
        ])
        relevance = _text_relevance_score(query_terms, metadata_text)
        duration_score = max(0.0, 25.0 - abs(duration - min_duration) * 2.0)
        resolution_score = min(25.0, (int(selected.get("width", 0) or 0) * int(selected.get("height", 0) or 0)) / 150000.0)
        total_score = relevance * 12.0 + duration_score + resolution_score

        # Use Pixabay's previewURL for thumbnail (it's a valid image URL)
        thumbnail = hit.get("previewURL", "")
        
        pixabay_title = str(hit.get("tags", ""))
        skip_seconds = _detect_intro_seconds(pixabay_title, "")

        candidates.append({
            "provider": "pixabay",
            "url": selected_url,
            "thumbnail": thumbnail,
            "score": total_score,
            "relevance": relevance,
            "duration": duration,
            "title": str(hit.get("tags", "")),
            "description": str(hit.get("type", "")),
            "skip_seconds": skip_seconds,
        })

    return sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)


def _search_nasa_candidates(
    query: str,
    min_duration: int,
    per_page: int = 10,
    page: int = 1,
) -> list[dict]:
    cache_key = (query.lower().strip(), max(1, int(per_page)), max(1, int(page)))
    cached = _NASA_QUERY_CACHE.get(cache_key)
    if cached is not None:
        return [dict(item) for item in cached]

    params = {
        "q": query,
        "media_type": "video",
        "page": max(1, int(page)),
    }

    try:
        resp = requests.get(
            NASA_SEARCH_API,
            params=params,
            timeout=20,
            headers={"User-Agent": "VideoGen/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json() or {}
    except Exception as e:
        print(f"[VideoSearch] NASA search request failed: {e}")
        return []

    items = (((payload.get("collection") or {}).get("items")) or [])
    if not items:
        _NASA_QUERY_CACHE[cache_key] = []
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

        nasa_title = str(data.get("title", ""))
        nasa_desc = str(data.get("description", ""))
        skip_seconds = _detect_intro_seconds(nasa_title, nasa_desc)

        candidates.append({
            "provider": "nasa",
            "url": asset_url,
            "thumbnail": thumbnail,
            "score": total_score,
            "relevance": relevance,
            "duration": estimated_duration,
            "title": nasa_title,
            "description": nasa_desc,
            "skip_seconds": skip_seconds,
        })

    result = sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)
    _NASA_QUERY_CACHE[cache_key] = [dict(item) for item in result]
    return result


def _resolve_nasa_asset_video_url(nasa_id: str) -> Optional[str]:
    if not nasa_id:
        return None

    if nasa_id in _NASA_ASSET_CACHE:
        return _NASA_ASSET_CACHE[nasa_id]

    asset_endpoint = f"https://images-api.nasa.gov/asset/{nasa_id}"
    try:
        resp = requests.get(asset_endpoint, timeout=20, headers={"User-Agent": "VideoGen/1.0"})
        resp.raise_for_status()
        payload = resp.json() or {}
    except Exception as e:
        print(f"[VideoSearch] NASA asset request failed for {nasa_id}: {e}")
        _NASA_ASSET_CACHE[nasa_id] = None
        return None

    items = (((payload.get("collection") or {}).get("items")) or [])
    if not items:
        _NASA_ASSET_CACHE[nasa_id] = None
        return None

    urls = []
    allowed_ext = (".mp4", ".mov", ".m4v", ".webm")
    for it in items:
        href = str((it or {}).get("href", ""))
        if href.startswith("http") and href.lower().split("?")[0].endswith(allowed_ext):
            urls.append(href)

    if not urls:
        _NASA_ASSET_CACHE[nasa_id] = None
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
    chosen = urls[0]
    _NASA_ASSET_CACHE[nasa_id] = chosen
    return chosen


def _build_query_candidates(keywords: str, context_text: str, fallback_keywords: str) -> list[str]:
    keyword_terms = _extract_terms(keywords)
    context_terms = _extract_terms(context_text)
    translated_terms = _translate_terms(keyword_terms + context_terms)
    
    # Semantic expansion: add related terms for better discovery
    expanded_terms = _get_semantic_expansions(keyword_terms + translated_terms, max_expansions=2)

    all_terms = []
    for term in keyword_terms + context_terms:
        if term not in all_terms:
            all_terms.append(term)

    candidates = []
    
    # Primary searches: original keywords (most specific)
    if keyword_terms:
        candidates.append(" ".join(keyword_terms[:2]))  # Best 2 keywords
        candidates.append(" ".join(keyword_terms[:3]))
        candidates.append(" ".join(keyword_terms[:4]))
    
    # Bilingual searches: English translations for broader coverage
    if translated_terms:
        candidates.append(" ".join(translated_terms[:2]))
        candidates.append(" ".join(translated_terms[:3]))
        candidates.append(" ".join(translated_terms[:4]))
    
    # Semantic expansion: add related terms for variety
    if expanded_terms and keyword_terms:
        # Mix original + expanded
        candidates.append(f"{keyword_terms[0]} {expanded_terms[0]}")
        if len(translated_terms) > 0 and len(expanded_terms) > 1:
            candidates.append(f"{translated_terms[0]} {expanded_terms[1]}")
    
    # Context-enriched searches (if context provided)
    if context_terms and keyword_terms:
        candidates.append(f"{keyword_terms[0]} {context_terms[0]}")
        if all_terms:
            candidates.append(" ".join(all_terms[:3]))
    
    # Individual keyword searches (fallback for exact matches)
    for term in translated_terms[:3]:
        if term not in " ".join(candidates):
            candidates.append(term)
    
    # Fallback
    if fallback_keywords:
        candidates.append(fallback_keywords)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for candidate in candidates:
        c = re.sub(r"\s+", " ", candidate).strip()
        if not c or c in seen or len(c) < 2:
            continue
        seen.add(c)
        unique.append(c)

    return unique or [fallback_keywords]


def _search_esa_candidates(
    query: str,
    min_duration: int,
    per_page: int = 10,
    page: int = 1,
) -> list[dict]:
    """Search ESA multimedia website and return video clip candidates."""
    cache_key = (query.lower().strip(), max(1, int(per_page)), max(1, int(page)))
    cached = _ESA_QUERY_CACHE.get(cache_key)
    if cached is not None:
        return [dict(item) for item in cached]

    entries = _fetch_esa_video_entries(page=max(1, int(page)))
    if not entries:
        _ESA_QUERY_CACHE[cache_key] = []
        return []

    query_terms = _extract_terms(query)
    candidates = []

    # Rank rough relevance by title first; then resolve direct media URLs.
    ranked_entries = sorted(
        entries,
        key=lambda entry: _text_relevance_score(query_terms, f"{entry.get('title', '')} {entry.get('url', '')}"),
        reverse=True,
    )

    for entry in ranked_entries[: max(1, per_page * 3)]:
        detail = _resolve_esa_video_detail(entry.get("url", ""))
        if not detail:
            continue

        title = str(detail.get("title") or entry.get("title") or "").strip()
        description = str(detail.get("description") or "").strip()
        video_url = str(detail.get("video_url") or "").strip()
        thumbnail = str(detail.get("thumbnail") or "").strip()

        if not video_url:
            continue

        metadata_text = " ".join([title, description])
        relevance = _text_relevance_score(query_terms, metadata_text)
        
        # Score based on relevance and quality indicators
        quality_bonus = 8.0 if ("4k" in video_url.lower() or "uhd" in title.lower()) else 5.0
        total_score = relevance * 12.0 + quality_bonus

        skip_seconds = _detect_intro_seconds(title, description)

        candidates.append({
            "provider": "esa",
            "url": video_url,
            "thumbnail": thumbnail or "",
            "score": total_score,
            "relevance": relevance,
            "duration": max(min_duration, 10),  # ESA videos are typically longer
            "title": title,
            "description": description,
            "skip_seconds": skip_seconds,
        })

        if len(candidates) >= max(1, per_page):
            break

    result = sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)
    _ESA_QUERY_CACHE[cache_key] = [dict(item) for item in result]
    return result


def _collect_urls_from_esa_item(value) -> list[str]:
    urls: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
            return
        if isinstance(node, list):
            for v in node:
                walk(v)
            return
        if isinstance(node, str):
            s = node.strip()
            if s.startswith("http://") or s.startswith("https://"):
                urls.append(s)

    walk(value)

    # Deduplicate preserving order
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def _fetch_esa_video_entries(page: int = 1) -> list[dict]:
    """Fetch ESA multimedia video list page and extract video detail links."""
    list_url = ESA_SEARCH_API if page <= 1 else f"{ESA_SEARCH_API}/(page)/{page}"

    try:
        resp = requests.get(
            list_url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (VideoGen bot)"},
        )
        resp.raise_for_status()
        html = resp.text or ""
    except Exception as e:
        print(f"[VideoSearch] ESA list request failed: {e}")
        return []

    # ESA links are typically relative and include year/month/slug.
    rel_links = re.findall(r'href="(/ESA_Multimedia/Videos/\d{4}/\d{2}/[^"]+)"', html)
    if not rel_links:
        return []

    entries = []
    seen = set()
    for rel in rel_links:
        full_url = f"https://www.esa.int{rel}"
        if full_url in seen:
            continue
        seen.add(full_url)
        slug = rel.rstrip("/").split("/")[-1]
        title = slug.replace("_", " ")
        entries.append({"url": full_url, "title": title})
    return entries


def _resolve_esa_video_detail(detail_url: str) -> Optional[dict]:
    """Resolve direct video URL from an ESA detail page."""
    if not detail_url:
        return None

    if detail_url in _ESA_DETAIL_CACHE:
        cached = _ESA_DETAIL_CACHE[detail_url]
        return dict(cached) if cached else None

    try:
        resp = requests.get(
            detail_url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (VideoGen bot)"},
        )
        resp.raise_for_status()
        html = resp.text or ""
    except Exception as e:
        print(f"[VideoSearch] ESA detail request failed: {e}")
        _ESA_DETAIL_CACHE[detail_url] = None
        return None

    # Extract candidate URLs from page source.
    urls = re.findall(r'https?://[^"\'\s)]+', html, flags=re.IGNORECASE)
    urls = [u.strip() for u in urls if u.strip()]

    video_url = _pick_best_esa_video_url(urls)
    thumbnail = _pick_best_esa_thumbnail_url(urls)

    title_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, flags=re.IGNORECASE)
    desc_match = re.search(r'<meta\s+property="og:description"\s+content="([^"]+)"', html, flags=re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ""
    description = desc_match.group(1).strip() if desc_match else ""

    if not video_url:
        _ESA_DETAIL_CACHE[detail_url] = None
        return None

    result = {
        "title": title,
        "description": description,
        "video_url": video_url,
        "thumbnail": thumbnail,
    }
    _ESA_DETAIL_CACHE[detail_url] = dict(result)
    return result


def _pick_best_esa_video_url(urls: list[str]) -> Optional[str]:
    if not urls:
        return None

    def base_url(u: str) -> str:
        return u.lower().split("?")[0]

    allowed_ext = (".mp4", ".webm", ".mov", ".m4v", ".m3u8")
    video_candidates = [u for u in urls if base_url(u).endswith(allowed_ext) or "/video" in u.lower()]
    if not video_candidates:
        return None

    def quality_key(u: str) -> tuple[int, int]:
        v = u.lower()
        score = 0
        if "4k" in v or "2160" in v:
            score += 50
        if "1080" in v:
            score += 40
        if "720" in v:
            score += 30
        if "master" in v or "orig" in v:
            score += 20
        if v.split("?")[0].endswith(".m3u8"):
            score -= 5  # prefer direct mp4 when available
        return score, len(u)

    video_candidates.sort(key=quality_key, reverse=True)
    return video_candidates[0]


def _pick_best_esa_thumbnail_url(urls: list[str]) -> str:
    if not urls:
        return ""

    def base_url(u: str) -> str:
        return u.lower().split("?")[0]

    image_candidates = [
        u for u in urls
        if base_url(u).endswith((".jpg", ".jpeg", ".png", ".webp"))
    ]
    if not image_candidates:
        return ""

    def thumb_key(u: str) -> tuple[int, int]:
        v = u.lower()
        score = 0
        if "thumb" in v or "thumbnail" in v or "preview" in v:
            score += 20
        if "small" in v:
            score -= 5
        return score, len(u)

    image_candidates.sort(key=thumb_key, reverse=True)
    return image_candidates[0]


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
    """
    Score relevance using semantic embeddings if available, falls back to keyword matching.
    Returns a score between 0 and 1.
    """
    if not query_terms and not metadata_text:
        return 0.0

    # Try semantic matching first
    model = _get_embedding_model()
    if model:
        try:
            query_text = " ".join(query_terms)
            query_embedding = model.encode(query_text, convert_to_numpy=True)
            metadata_embedding = model.encode(metadata_text, convert_to_numpy=True)
            
            # Cosine similarity: dot product / (norm1 * norm2)
            similarity = np.dot(query_embedding, metadata_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(metadata_embedding) + 1e-8
            )
            # Normalize from [-1, 1] to [0, 1]
            normalized_score = (float(similarity) + 1.0) / 2.0
            return min(1.0, max(0.0, normalized_score))
        except Exception as e:
            print(f"[VideoSearch] Semantic scoring failed: {e}, falling back to keyword matching")

    # Fallback: keyword matching
    metadata_terms = set(_extract_terms(metadata_text, max_terms=60))
    if not metadata_terms:
        return 0.0

    hits = sum(1 for term in query_terms if term in metadata_terms)
    return hits / max(1, len(query_terms))


def _qwen_rerank_candidates(query_text: str, ranked_candidates: list[dict], top_k: int = 8) -> list[dict]:
    """
    Ask Qwen (via Ollama) to pick the best candidate among top_k results.
    Returns reordered full list with selected candidate moved to first position.
    Falls back silently to original ranking on any error.
    """
    if not ranked_candidates or top_k < 2:
        return ranked_candidates

    pool = ranked_candidates[:top_k]
    lines = []
    for i, candidate in enumerate(pool, start=1):
        provider = str(candidate.get("provider", "manual"))
        duration = candidate.get("duration", "?")
        score = round(float(candidate.get("score", 0.0)), 2)
        relevance = round(float(candidate.get("relevance", 0.0)), 3)
        url = str(candidate.get("url", ""))
        title = str(candidate.get("title", "")).strip()
        description = str(candidate.get("description", "")).strip()
        snippet = (f"{title} | {description}").strip(" |")[:240]
        lines.append(
            f"{i}) provider={provider} duration={duration}s score={score} relevance={relevance} "
            f"context={snippet} url={url}"
        )

    options_text = "\n".join(lines)

    user_prompt = (
        "Selecciona el video que mejor encaja con el guion o segmento.\n"
        f"Consulta: {query_text or 'video relevante y coherente'}\n"
        "Opciones:\n"
        f"{options_text}\n\n"
        "Responde SOLO con el número de la mejor opción (ejemplo: 3)."
    )

    try:
        text = _ollama_generate_text(user_prompt)
        if not text:
            return ranked_candidates

        match = re.search(r"\b(\d{1,2})\b", text)
        if not match:
            return ranked_candidates

        picked = int(match.group(1))
        if picked < 1 or picked > len(pool):
            return ranked_candidates

        chosen = pool[picked - 1]
        reordered_top = [chosen] + [c for idx, c in enumerate(pool) if idx != (picked - 1)]
        return reordered_top + ranked_candidates[top_k:]
    except Exception as e:
        print(f"[VideoSearch] Qwen rerank skipped: {e}")
        return ranked_candidates


def _ffmpeg_is_available() -> bool:
    global _FFMPEG_AVAILABLE
    if _FFMPEG_AVAILABLE is None:
        _FFMPEG_AVAILABLE = bool(shutil.which("ffmpeg"))
    return bool(_FFMPEG_AVAILABLE)


def _extract_video_frames_base64(video_url: str, max_frames: int = 3) -> list[str]:
    if not video_url or max_frames <= 0:
        return []
    if not _ffmpeg_is_available():
        return []

    safe_frames = max(1, min(6, int(max_frames)))
    url_hash = hashlib.md5(video_url.encode()).hexdigest()
    frame_dir = CACHE_DIR / "_vision_frames" / url_hash
    frame_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(frame_dir.glob("frame_*.jpg"))
    if len(existing) < safe_frames:
        for old in existing:
            try:
                old.unlink()
            except Exception:
                pass

        output_pattern = str(frame_dir / "frame_%02d.jpg")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video_url,
            "-vf",
            "fps=1/2,scale=640:-1",
            "-frames:v",
            str(safe_frames),
            output_pattern,
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=35)
        except Exception:
            return []

    frames = []
    for path in sorted(frame_dir.glob("frame_*.jpg"))[:safe_frames]:
        try:
            raw = path.read_bytes()
            if not raw:
                continue
            frames.append(base64.b64encode(raw).decode("utf-8"))
        except Exception:
            continue
    return frames


def _ollama_visual_match_score(segment_text: str, candidate: dict, frame_b64_images: list[str]) -> Optional[float]:
    if not frame_b64_images:
        return None

    base_url = OLLAMA_BASE_URL.rstrip("/")
    provider = str(candidate.get("provider", "manual"))
    title = str(candidate.get("title", "")).strip()
    description = str(candidate.get("description", "")).strip()
    duration = candidate.get("duration", "?")

    prompt = (
        "Evalúa cuánto coincide visualmente este video con el segmento objetivo.\n"
        f"Segmento objetivo: {segment_text or 'video coherente con el tema'}\n"
        f"Proveedor: {provider}\n"
        f"Título/meta: {title}\n"
        f"Descripción/meta: {description}\n"
        f"Duración: {duration}s\n\n"
        "Devuelve SOLO un número entero del 0 al 100 (0 = no coincide, 100 = coincide perfecto)."
    )

    payload = {
        "model": OLLAMA_VIDEO_VISION_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Eres un evaluador estricto de coincidencia visual para clips de video.",
            },
            {
                "role": "user",
                "content": prompt,
                "images": frame_b64_images,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
        },
    }

    try:
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=40)
        response.raise_for_status()
        body = response.json() or {}
        text = str(((body.get("message") or {}).get("content") or "")).strip()
        if not text:
            return None

        match = re.search(r"\b(100|[1-9]?\d)\b", text)
        if not match:
            return None

        value = float(int(match.group(1))) / 100.0
        return min(1.0, max(0.0, value))
    except Exception:
        return None


def _qwen_visual_rerank_candidates(query_text: str, ranked_candidates: list[dict], top_k: int = 4) -> list[dict]:
    if not ranked_candidates or top_k < 2:
        return ranked_candidates

    pool = ranked_candidates[:top_k]
    tail = ranked_candidates[top_k:]
    scored = []
    visual_hits = 0

    for candidate in pool:
        url = str(candidate.get("url", ""))
        frames = _extract_video_frames_base64(url, max_frames=QWEN_VIDEO_VISUAL_MAX_FRAMES)
        visual_score = _ollama_visual_match_score(query_text, candidate, frames) if frames else None
        if visual_score is not None:
            visual_hits += 1

        adjusted = float(candidate.get("score", 0.0))
        if visual_score is not None:
            adjusted += visual_score * QWEN_VIDEO_VISUAL_WEIGHT

        enriched = dict(candidate)
        if visual_score is not None:
            enriched["visual_match"] = round(visual_score, 3)
        enriched["score"] = adjusted
        scored.append(enriched)

    if visual_hits == 0:
        return ranked_candidates

    scored.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    return scored + tail


def _ollama_generate_text(user_prompt: str) -> str:
    base_url = OLLAMA_BASE_URL.rstrip("/")

    chat_payload = {
        "model": OLLAMA_VIDEO_RERANK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Eres un selector experto de metraje de stock para videos cortos.",
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }

    generate_payload = {
        "model": OLLAMA_VIDEO_RERANK_MODEL,
        "prompt": (
            "Eres un selector experto de metraje de stock para videos cortos.\n"
            f"{user_prompt}"
        ),
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }

    response = requests.post(f"{base_url}/api/chat", json=chat_payload, timeout=12)  # Reduced from 25s
    if response.status_code == 404:
        response = requests.post(f"{base_url}/api/generate", json=generate_payload, timeout=12)

    response.raise_for_status()
    payload = response.json() or {}
    message_text = ((payload.get("message") or {}).get("content") or "").strip()
    if message_text:
        return message_text
    return str(payload.get("response", "")).strip()

