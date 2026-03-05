"""
Script Parser Module
Splits a script into segments by paragraphs and generates search keywords.
"""
import re
from typing import List, Dict

# Average reading/speaking speed in words per minute
WORDS_PER_MINUTE = 150


def parse_script(script: str) -> List[Dict]:
    """
    Parse a script into segments split by double newlines (paragraphs).
    Returns a list of dicts with text, keywords, and estimated duration.
    """
    # Normalize line endings
    script = script.replace('\r\n', '\n').replace('\r', '\n')

    # Split by one or more blank lines
    raw_segments = re.split(r'\n{2,}', script.strip())

    segments = []
    for i, text in enumerate(raw_segments):
        text = text.strip()
        if not text:
            continue

        # Clean up text (remove stage directions in brackets if any)
        clean_text = re.sub(r'\[.*?\]', '', text).strip()
        if not clean_text:
            continue

        word_count = len(clean_text.split())
        estimated_duration = (word_count / WORDS_PER_MINUTE) * 60  # in seconds
        # Minimum 3 seconds per segment
        estimated_duration = max(3.0, estimated_duration)

        keywords = extract_keywords(clean_text)

        segments.append({
            "id": i,
            "text": clean_text,
            "keywords": keywords,
            "word_count": word_count,
            "estimated_duration": round(estimated_duration, 2),
        })

    return segments


def extract_keywords(text: str) -> str:
    """
    Extract meaningful keywords from a text segment for stock video search.
    Uses simple heuristics: removes stop words and keeps nouns/significant words.
    """
    # Spanish stop words (common ones)
    stop_words = {
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'y', 'o', 'pero', 'si', 'no', 'que', 'de', 'en', 'a',
        'es', 'son', 'por', 'para', 'con', 'del', 'al', 'lo',
        'se', 'su', 'sus', 'me', 'te', 'le', 'nos', 'les',
        'mi', 'tu', 'como', 'este', 'esta', 'esto', 'ese', 'esa',
        'más', 'muy', 'bien', 'ya', 'hay', 'ser', 'estar', 'tener',
        'hacer', 'también', 'cuando', 'todo', 'toda', 'todos',
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
        'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were',
    }

    # Tokenize: split on spaces and punctuation
    words = re.findall(r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑA-Za-z]{4,}\b', text)
    keywords = [w.lower() for w in words if w.lower() not in stop_words]

    # Deduplicate and take top 3
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
        if len(unique) >= 3:
            break

    # Fallback to first 2 content words if nothing found
    if not unique:
        all_words = text.split()[:3]
        unique = [w.lower() for w in all_words]

    return ' '.join(unique)
