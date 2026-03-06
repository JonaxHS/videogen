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
    Captures key phrases, technical terms, and context to differentiate similar topics.
    """
    text_lower = text.lower()
    
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
    
    # Priority key phrases (2-3 words) that should be kept together
    key_phrases = []
    phrase_patterns = [
        # Science/Physics
        r'agujero negro', r'black hole', r'agujero de gusano', r'wormhole',
        r'relatividad (general|especial)', r'general relativity', r'special relativity',
        r'curvas? cerradas? de tiempo', r'closed timelike curve', 
        r'dilatación del tiempo', r'time dilation', r'espacio-?tiempo', r'spacetime',
        r'velocidad de la luz', r'speed of light', r'gravedad extrema',
        r'cilindro cósmico', r'cosmic cylinder', r'universo rotante', r'rotating universe',
        # Time concepts
        r'viajar al (pasado|futuro)', r'time travel', r'viaje en el tiempo',
        r'máquina del tiempo', r'línea temporal', r'timeline',
        # Tech/Science concepts
        r'modelo de gödel', r'hipótesis de consistencia', r'protección cronológica',
        r'paradoja temporal', r'paradox', r'multiverso', r'multiverse',
        r'radiación de vacío', r'vacuum radiation', r'física cuántica', r'quantum',
        r'relojes? atómicos?', r'atomic clock', r'gps', r'muones?',
        # Visual concepts
        r'experimento', r'observación', r'medición', r'measurement',
    ]
    
    for pattern in phrase_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            if isinstance(match, tuple):
                phrase = " ".join([m for m in match if m])
            else:
                phrase = match
            if phrase and phrase not in key_phrases:
                key_phrases.append(phrase)
    
    # Detect temporal direction for better video matching
    temporal_context = []
    if any(word in text_lower for word in ['pasado', 'past', 'atrás', 'regres', 'volver', 'antes']):
        temporal_context.append('pasado')
    if any(word in text_lower for word in ['futuro', 'future', 'adelante', 'avanz', 'próximo', 'después']):
        temporal_context.append('futuro')
    if any(word in text_lower for word in ['paradoja', 'paradox', 'imposible', 'contradicción']):
        temporal_context.append('paradoja')
    
    # Extract individual important technical/scientific terms
    important_terms = []
    technical_patterns = [
        r'\b(einstein|hawking|gödel|minkowski)\b',
        r'\b(relatividad|relativity|cuántica?|quantum)\b',
        r'\b(gravedad|gravity|masa|materia|energía|energy)\b',
        r'(espacio|space|tiempo|time|dimensión|dimension)',
        r'\b(luz|light|velocidad|speed|rápido|fast)\b',
        r'\b(universo|universe|cosmos|cósmico?)\b',
        r'\b(partícula|particle|átomo|atom|muón|muon)\b',
        r'\b(observ|medición|measurement|experimento|experiment)\b',
        r'\b(científico|science|física|physics|teoría|theory)\b',
        r'\b(tecnología|technology|máquina|machine|dispositivo)\b',
    ]
    
    for pattern in technical_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            if match and match not in stop_words:
                important_terms.append(match)
    
    # Extract regular keywords (nouns and significant words)
    words = re.findall(r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑA-Za-z]{3,}\b', text_lower)
    regular_keywords = [w for w in words if w not in stop_words]
    
    # Build final keyword list with priority order:
    # 1. Temporal context (pasado/futuro/paradoja)
    # 2. Key phrases (agujero negro, relatividad general, etc.)
    # 3. Important technical terms
    # 4. Regular keywords
    
    final_keywords = []
    seen = set()
    
    # Add temporal context first (critical for differentiation)
    for term in temporal_context:
        if term not in seen:
            seen.add(term)
            final_keywords.append(term)
    
    # Add key phrases (max 2-3 to avoid over-constraining)
    for phrase in key_phrases[:3]:
        words_in_phrase = phrase.split()
        for word in words_in_phrase:
            if word not in seen and word not in stop_words:
                seen.add(word)
                final_keywords.append(word)
    
    # Add important technical terms
    for term in important_terms:
        if term not in seen:
            seen.add(term)
            final_keywords.append(term)
        if len(final_keywords) >= 10:
            break
    
    # Fill with regular keywords if needed
    for kw in regular_keywords:
        if kw not in seen:
            seen.add(kw)
            final_keywords.append(kw)
        if len(final_keywords) >= 12:
            break
    
    # Fallback to first content words if nothing found
    if not final_keywords:
        all_words = [w.lower() for w in text.split()[:5]]
        final_keywords = all_words if all_words else ['video']
    
    return ' '.join(final_keywords[:12])
