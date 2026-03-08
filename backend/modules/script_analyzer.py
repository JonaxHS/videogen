"""
Script Analyzer — Intelligent theme detection and keyword expansion for astronomy/science scripts
"""
import re
from typing import Optional
from collections import defaultdict

# Scientific domain mappings for astronomy/physics scripts
SCIENTIFIC_DOMAINS = {
    "relatividad": {
        "keywords": ["relativity", "spacetime", "einstein", "velocity light", "time dilation"],
        "related_concepts": ["twin paradox", "muons", "atomic clocks", "special relativity", "general relativity"],
        "providers_priority": ["nasa", "esa"],  # Science authority
    },
    "relatividad especial": {
        "keywords": ["special relativity", "spacetime", "velocity of light", "time dilation", "mass energy"],
        "related_concepts": ["einstein", "moving clocks", "simultaneity", "reference frames"],
        "providers_priority": ["nasa", "esa"],
    },
    "agujero negro": {
        "keywords": ["black hole", "event horizon", "gravity", "spacetime curvature", "singularity"],
        "related_concepts": ["accretion disk", "gravitational waves", "hawking radiation", "neutron star"],
        "providers_priority": ["nasa", "esa"],
    },
    "gravedad": {
        "keywords": ["gravity", "gravitational field", "mass", "curvature", "newton"],
        "related_concepts": ["orbit", "attraction", "acceleration", "weight"],
        "providers_priority": ["nasa"],
    },
    "universo": {
        "keywords": ["universe", "cosmos", "space", "expansion", "big bang"],
        "related_concepts": ["galaxy", "galaxy cluster", "universe expansion", "cosmic microwave"],
        "providers_priority": ["nasa", "esa"],
    },
    "galaxia": {
        "keywords": ["galaxy", "milky way", "andromeda", "spiral", "elliptical"],
        "related_concepts": ["stars", "dust clouds", "galactic center", "dark matter"],
        "providers_priority": ["nasa", "esa"],
    },
    "estrellas": {
        "keywords": ["star", "stars", "stellar", "nebula", "formation"],
        "related_concepts": ["supernova", "white dwarf", "neutron star", "pulsar", "birth"],
        "providers_priority": ["nasa", "esa"],
    },
    "telescopio": {
        "keywords": ["telescope", "observatory", "space telescope", "webbtelescope", "hubble"],
        "related_concepts": ["infrared", "detection", "visualization", "observation"],
        "providers_priority": ["nasa", "esa"],
    },
    "partículas": {
        "keywords": ["particles", "subatomic", "muons", "electrons", "quarks"],
        "related_concepts": ["physics", "quantum", "detector", "collision"],
        "providers_priority": ["nasa"],
    },
    "tiempo": {
        "keywords": ["time", "clock", "duration", "measurement", "flow"],
        "related_concepts": ["relativity", "perception", "physics"],
        "providers_priority": ["nasa"],
    },
    "luz": {
        "keywords": ["light", "photon", "wavelength", "speed", "electromagnetic"],
        "related_concepts": ["radiation", "infrared", "ultraviolet", "spectrum"],
        "providers_priority": ["nasa"],
    },
    "órbita": {
        "keywords": ["orbit", "orbital", "rotation", "revolution", "trajectory"],
        "related_concepts": ["gravity", "satellite", "ellipse"],
        "providers_priority": ["nasa"],
    },
}

# Concept-to-keywords mapping (deeper semantic understanding)
CONCEPT_EXPANSION = {
    # Relatividad
    "dilatación del tiempo": ["time dilation", "moving clocks", "relativity", "velocity"],
    "paradoja de los gemelos": ["twin paradox", "relativity", "space travel", "aging", "time"],
    "aceleración": ["acceleration", "force", "motion", "speed change"],
    
    # Física de partículas
    "muones": ["muons", "subatomic particles", "atmosphere", "cosmic rays", "lifespan"],
    "relatividad especial": ["special relativity", "einstein", "velocity", "spacetime"],
    
    # Astronomía visual
    "hermanos idénticos": ["identical twins", "people", "siblings", "genetics"],
    "nave espacial": ["spacecraft", "spaceship", "rocket", "launch", "travel"],
    "velocidad de la luz": ["speed of light", "light speed", "c constant", "velocity"],
    
    # Conceptos de distancia/tiempo
    "35 años luz": ["distance", "light-year", "space", "stars", "cosmic distance"],
    
    # Conceptos de comprobación empírica
    "relojes atómicos": ["atomic clocks", "precision measurement", "time", "aircraft"],
    "partículas atmósfera": ["atmosphere", "air", "particles", "cosmic"],
    
    # Einstein/contexto histórico
    "einstein": ["einstein", "physicist", "portrait", "genius", "theories"],
}

# Keyword synonym expansion for better video search
KEYWORD_SYNONYMS = {
    "relatividad": ["relativity", "relativity theory", "relativistic"],
    "tiempo": ["time", "temporal", "duration", "clock"],
    "luz": ["light", "photon", "luminous", "speed of light"],
    "agujero negro": ["black hole", "singularity", "event horizon"],
    "galaxia": ["galaxy", "galaxies", "milky way"],
    "estrella": ["star", "stars", "stellar", "sun"],
    "espacio": ["space", "cosmos", "universe", "outer space"],
    "planeta": ["planet", "terrestrial", "orbital"],
    "universo": ["universe", "cosmos", "existence"],
    "física": ["physics", "quantum", "mechanics"],
    "energía": ["energy", "power", "force"],
    "partículas": ["particles", "atoms", "subatomic"],
    "órbita": ["orbit", "orbital", "circular motion"],
    "gravedad": ["gravity", "gravitational", "attraction"],
}


def detect_scientific_domains(script_text: str) -> list[str]:
    """
    Detect scientific domains mentioned in the script.
    Returns list of domain keys like 'relatividad', 'agujero negro'.
    """
    text_lower = script_text.lower()
    detected_domains = []
    domain_scores = defaultdict(int)
    
    for domain_key, domain_info in SCIENTIFIC_DOMAINS.items():
        # Check main keyword
        if domain_key in text_lower:
            domain_scores[domain_key] += 10
        
        # Check related keywords
        for keyword in domain_info.get("keywords", []):
            if keyword.lower() in text_lower:
                domain_scores[domain_key] += 5
        
        # Check related concepts
        for concept in domain_info.get("related_concepts", []):
            if concept.lower() in text_lower:
                domain_scores[domain_key] += 3
    
    # Sort by detection score and return
    sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
    detected_domains = [domain for domain, score in sorted_domains if score > 0]
    
    return detected_domains[:5]  # Top 5 domains


def expand_segment_keywords(
    segment_text: str,
    script_context: str = "",
    detected_domains: Optional[list[str]] = None,
) -> dict:
    """
    Intelligently expand a segment's keywords with scientific synonyms and concepts.
    
    Returns:
    {
        "primary_keywords": ["primary search terms"],
        "secondary_keywords": ["fallback search terms"],
        "concepts": ["conceptual keywords"],
        "suggested_providers": ["nasa", "esa"],
    }
    """
    if detected_domains is None:
        detected_domains = []
    
    primary = []
    secondary = []
    concepts = []
    providers = set()
    
    # Extract obvious keywords from segment
    words = [w.strip().lower() for w in re.split(r'[\s,.\-:;]+', segment_text) if len(w.strip()) > 3]
    
    # Check for concept matches
    for concept_key, concept_keywords in CONCEPT_EXPANSION.items():
        if concept_key in segment_text.lower():
            concepts.append(concept_key)
            primary.extend(concept_keywords[:2])  # Top 2 keywords for this concept
    
    # Map detected domains to this segment
    for domain in detected_domains:
        if domain in SCIENTIFIC_DOMAINS:
            domain_info = SCIENTIFIC_DOMAINS[domain]
            if any(d in segment_text.lower() for d in domain_info.get("keywords", [domain])):
                primary.extend(domain_info.get("keywords", [])[:2])
                secondary.extend(domain_info.get("related_concepts", [])[:2])
                providers.update(domain_info.get("providers_priority", []))
    
    # Expand individual word matches with synonyms
    for word in words:
        if word in KEYWORD_SYNONYMS:
            primary.append(word)
            secondary.extend(KEYWORD_SYNONYMS[word][:2])
        else:
            # Add word as-is if interesting
            if len(word) > 5:
                primary.append(word)
    
    # De-duplicate and limit
    primary = list(dict.fromkeys(primary))[:8]
    secondary = list(dict.fromkeys(secondary))[:10]
    concepts = list(dict.fromkeys(concepts))[:5]
    
    # Default providers if none detected
    if not providers:
        providers = {"nasa", "esa", "pexels", "pixabay"}
    
    return {
        "primary_keywords": primary,
        "secondary_keywords": secondary,
        "concepts": concepts,
        "suggested_providers": sorted(list(providers)),
    }


def build_multikeyword_queries(
    segment_text: str,
    script_context: str = "",
    num_queries: int = 3,
) -> list[str]:
    """
    Build multiple search queries for a single segment using intelligent expansion.
    For example:
    - "muones partículas relatividad"
    - "muons cosmic rays atmosphere"
    - "time dilation particles expansion"
    
    This allows richer video discovery than a single keyword.
    """
    detected_domains = detect_scientific_domains(script_context or segment_text)
    expansion = expand_segment_keywords(segment_text, script_context, detected_domains)
    
    primary_kw = expansion["primary_keywords"]
    secondary_kw = expansion["secondary_keywords"]
    
    queries = []
    
    # Query 1: Primary + primary
    if len(primary_kw) >= 2:
        queries.append(f"{primary_kw[0]} {primary_kw[1]}")
    elif len(primary_kw) == 1:
        queries.append(primary_kw[0])
    
    # Query 2: Primary + secondary concept
    if len(primary_kw) >= 1 and len(secondary_kw) >= 1:
        queries.append(f"{primary_kw[0]} {secondary_kw[0]}")
    
    # Query 3: Concept-focused query
    if len(secondary_kw) >= 2:
        queries.append(f"{secondary_kw[0]} {secondary_kw[1]}")
    elif len(secondary_kw) >= 1:
        queries.append(secondary_kw[0])
    
    # Remove empty and duplicate queries
    queries = [q.strip() for q in queries if q.strip()]
    queries = list(dict.fromkeys(queries))[:num_queries]
    
    return queries


def get_preferred_providers_for_segment(
    segment_text: str,
    script_context: str = "",
) -> list[str]:
    """
    Determine which video providers are best for this segment.
    
    Returns ordered list: primary providers first (nasa/esa for science),
    then fallback providers (pexels/pixabay for stock footage).
    """
    detected_domains = detect_scientific_domains(script_context or segment_text)
    expansion = expand_segment_keywords(segment_text, script_context, detected_domains)
    
    # Check if this is hard science (needs NASA/ESA) or visual effects (Pexels/Pixabay)
    hard_science_indicators = [
        "muon", "relatividad", "relativit", "tiempo dilation", "einstein",
        "telescope", "nasa", "esa", "atom", "physics", "quantum",
        "black hole", "galaxy", "nebula", "space",
    ]
    
    is_hard_science = any(
        indicator in segment_text.lower() 
        for indicator in hard_science_indicators
    )
    
    visual_effects_indicators = [
        "hermano", "gem", "nave", "spaceship", "persona", "person",
        "reloj", "clock", "airplane", "avión", "efectos", "visual",
    ]
    
    is_visual_effects = any(
        indicator in segment_text.lower() 
        for indicator in visual_effects_indicators
    )
    
    # Prefer NASA/ESA for hard science
    if is_hard_science:
        return ["nasa", "esa", "pexels", "pixabay"]
    # Prefer Pexels/Pixabay for visual/people content
    elif is_visual_effects:
        return ["pexels", "pixabay", "nasa", "esa"]
    # Default: balanced
    else:
        return ["nasa", "esa", "pexels", "pixabay"]


def analyze_script_structure(script_text: str) -> dict:
    """
    Analyze overall script structure and themes.
    
    Returns:
    {
        "detected_domains": ["relatividad", "partículas", ...],
        "primary_theme": "relatividad especial",
        "tone": "educational_scientific",
        "estimated_segment_count": 8,
        "recommended_visual_style": "cinematic_documentary",
    }
    """
    # Detect domains
    detected_domains = detect_scientific_domains(script_text)
    primary_theme = detected_domains[0] if detected_domains else "general"
    
    # Detect tone
    tone_indicators = {
        "educational_scientific": ["paradoja", "contradicción", "explicación", "ley", "ecuación"],
        "narrative_story": ["imaginemos", "hermanos", "viaje", "historia"],
        "documentary": ["observación", "estudio", "demostración"],
    }
    
    detected_tone = "educational_scientific"  # Default
    for tone, indicators in tone_indicators.items():
        if any(ind in script_text.lower() for ind in indicators):
            detected_tone = tone
            break
    
    # Estimate segment count (rough heuristic: paragraph count)
    segments = [p.strip() for p in script_text.split('\n\n') if p.strip()]
    estimated_segments = len(segments)
    
    # Recommended visual style
    if primary_theme in ["relatividad", "relatividad especial", "gravedad", "agujero negro"]:
        visual_style = "cinematic_documentary_scientific"
    else:
        visual_style = "cinematic_documentary"
    
    return {
        "detected_domains": detected_domains,
        "primary_theme": primary_theme,
        "tone": detected_tone,
        "estimated_segment_count": estimated_segments,
        "recommended_visual_style": visual_style,
        "script_length_chars": len(script_text),
    }


# Relativity-specific enhancements (this script is about special relativity)
RELATIVITY_SPECIAL_KEYWORDS = {
    "gemelos": ["identical twins", "siblings", "family", "genetics"],
    "nave": ["spaceship", "spacecraft", "rocket", "launch", "propulsion"],
    "viaje": ["space travel", "journey", "voyage", "travel", "motion"],
    "años luz": ["light-years", "cosmic distance", "space distance"],
    "velocidad": ["speed", "velocity", "motion", "acceleration"],
    "dilatación": ["dilation", "expansion", "stretch", "time dilation"],
    "envejece": ["aging", "age", "grow older", "time passing"],
    "aceleración": ["acceleration", "speed increase", "force"],
    "muones": ["muons", "particles", "atmosphere", "cosmic rays", "decay"],
    "microsegundos": ["microseconds", "time measurement", "precision"],
    "relojes atómicos": ["atomic clocks", "precision clocks", "time measurement"],
    "Einstein": ["Einstein", "physicist", "portrait", "theory"],
    "espacio-tiempo": ["spacetime", "space-time", "fabric", "curvature"],
}
