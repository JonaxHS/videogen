"""
Script Parser Module
Splits a script into segments by paragraphs and generates search keywords.
"""
import re
from typing import List, Dict

# Average reading/speaking speed in words per minute
WORDS_PER_MINUTE = 150


def clean_text(text: str) -> str:
    """
    Remove emojis, markdown formatting, and problematic special characters.
    Keeps basic punctuation and letters.
    """
    # Remove markdown bold/italic
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    text = re.sub(r'\*', '', text)
    text = re.sub(r'_', '', text)
    
    # Remove emojis and unicode symbols
    # Emoji ranges: https://unicode.org/emoji/charts/full-emoji-list.html
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed characters
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    
    # Remove other special unicode symbols (keep basic punctuation)
    text = re.sub(r'[^\w\s.,;:!?¿¡()\-áéíóúüñÁÉÍÓÚÜÑ]', '', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def parse_script(script: str) -> List[Dict]:
    """
    Parse a script into segments split by double newlines (paragraphs).
    Returns a list of dicts with text, keywords, and estimated duration.
    """
    # Normalize line endings
    script = script.replace('\r\n', '\n').replace('\r', '\n')

    # Split by one or more blank lines (preferred)
    raw_segments = re.split(r'\n{2,}', script.strip())

    # Fallback: if user wrote everything in one block, split by sentences
    non_empty = [s for s in raw_segments if s.strip()]
    if len(non_empty) <= 1:
        sentence_parts = re.split(r'(?<=[.!?¿¡])\s+', script.strip())
        sentence_parts = [s.strip() for s in sentence_parts if s.strip()]

        grouped_segments = []
        current_group = []
        current_words = 0

        for sentence in sentence_parts:
            sentence_words = len(sentence.split())

            # Start a new segment around ~28 words to keep reel pacing
            if current_group and (current_words + sentence_words > 28):
                grouped_segments.append(" ".join(current_group).strip())
                current_group = [sentence]
                current_words = sentence_words
            else:
                current_group.append(sentence)
                current_words += sentence_words

        if current_group:
            grouped_segments.append(" ".join(current_group).strip())

        if grouped_segments:
            raw_segments = grouped_segments

    segments = []
    for i, text in enumerate(raw_segments):
        text = text.strip()
        if not text:
            continue

        # Clean up text (remove emojis, markdown, stage directions)
        text = clean_text(text)
        text = re.sub(r'\[.*?\]', '', text).strip()
        
        if not text:
            continue

        word_count = len(text.split())
        estimated_duration = (word_count / WORDS_PER_MINUTE) * 60  # in seconds
        # Minimum 3 seconds per segment
        estimated_duration = max(3.0, estimated_duration)

        keywords = extract_keywords(text)

        segments.append({
            "id": i,
            "text": text,
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

    # Tokenize: split on spaces and punctuation (min 3 chars to avoid articles)
    words = re.findall(r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑA-Za-z]{3,}\b', text)
    keywords = [w.lower() for w in words if w.lower() not in stop_words]

    # Deduplicate while preserving order (keep first 6 for better search coverage)
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
        if len(unique) >= 6:
            break

    # Fallback to first content words if nothing found
    if not unique:
        all_words = [w.lower() for w in text.split()[:5]]
        unique = all_words if all_words else ['video']

    return ' '.join(unique)
