#!/usr/bin/env python3
"""
Test script for intelligent video search using script analysis
Tests with the relativity/special relativity script the user provided
"""

import sys
from pathlib import Path

# Add backend modules to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from modules.script_analyzer import (
    analyze_script_structure,
    expand_segment_keywords,
    detect_scientific_domains,
    build_multikeyword_queries,
    get_preferred_providers_for_segment,
)

# Full relativity script from user
RELATIVITY_SCRIPT = """
Imagina dos hermanos.  
Idénticos.  
Mismos genes.  
Mismo reloj biológico.

Uno se queda en la Tierra.  
El otro aborda una nave  
que viaja a **99% de la velocidad de la luz**  
hacia una estrella a 35 años luz.

Para el viajero,  
el viaje de ida y vuelta  
dura **10 años**.  
Envejece 10 años.

Pero en la Tierra,  
han pasado **71 años**.  
Su hermano tiene 90.  
Él, apenas 35.

¿Paradoja?  
No.  
Es **relatividad especial**.

Durante el viaje constante,  
ambos ven al otro en cámara lenta.  
Parece simétrico.  
Pero hay un detalle clave:  
el viajero **acelera**.  
Al despegar,  
al girar,  
al frenar.

La aceleración rompe la simetría.  
Y solo el viajero  
siente esa fuerza.

Así, su marco de referencia  
no es inercial.  
Y el tiempo,  
en su reloj,  
realmente avanza más lento.

Esto no es teoría.  
Se ha confirmado  
con partículas subatómicas:  
los muones,  
que viven 2.2 microsegundos en reposo,  
llegan a la superficie terrestre  
porque, al moverse a 0.99c,  
su tiempo se dilata  
y "viven" más.

Incluso con relojes atómicos en aviones:  
los que volaron  
regresaron ligeramente más jóvenes.

Así que si algún día  
viajamos a las estrellas,  
no solo cruzaremos el espacio.  
Cruzaremos el tiempo.

Y al regresar,  
el mundo  
habrá seguido sin nosotros.

Porque en el universo,  
el tiempo no es un río común.  
Es un sendero personal.  
Y cada uno  
camina a su ritmo.

Gracias a Einstein,  
sabemos que  
el viajero no envejece menos  
por magia.  
Sino porque  
el espacio y el tiempo  
son una sola tela…  
y él la atravesó  
más rápido.
"""

def test_script_analysis():
    """Test the script analysis system"""
    print("=" * 80)
    print("INTELLIGENT SCRIPT ANALYSIS TEST")
    print("=" * 80)
    
    # Overall script analysis
    print("\n1️⃣  SCRIPT-LEVEL ANALYSIS")
    print("-" * 80)
    analysis = analyze_script_structure(RELATIVITY_SCRIPT)
    print(f"Detected Domains: {analysis['detected_domains']}")
    print(f"Primary Theme: {analysis['primary_theme']}")
    print(f"Tone: {analysis['tone']}")
    print(f"Estimated Segments: {analysis['estimated_segment_count']}")
    print(f"Visual Style: {analysis['recommended_visual_style']}")
    
    # Test key segments
    segments_to_analyze = [
        "Imagina dos hermanos. Idénticos. Mismos genes.",  # People/twins
        "El otro aborda una nave que viaja a 99% de la velocidad de la luz",  # Spaceship
        "Para el viajero, el viaje dura 10 años. Envejece 10 años.",  # Time dilation intro
        "Los muones, que viven 2.2 microsegundos en reposo",  # Particles
        "Incluso con relojes atómicos en aviones",  # Atomic clocks
        "el espacio y el tiempo son una sola tela",  # Einstein/abstract
    ]
    
    print("\n2️⃣  SEGMENT-BY-SEGMENT ANALYSIS")
    print("-" * 80)
    
    for idx, segment in enumerate(segments_to_analyze, 1):
        print(f"\nSegment {idx}: \"{segment[:50]}...\"")
        
        # Domains
        domains = detect_scientific_domains(RELATIVITY_SCRIPT)
        
        # Keyword expansion
        expansion = expand_segment_keywords(segment, RELATIVITY_SCRIPT, domains)
        print(f"  Primary Keywords: {expansion['primary_keywords']}")
        print(f"  Secondary Keywords: {expansion['secondary_keywords']}")
        print(f"  Concepts: {expansion['concepts']}")
        
        # Multi-keyword queries
        queries = build_multikeyword_queries(segment, RELATIVITY_SCRIPT, num_queries=3)
        print(f"  Multi-Queries to Search:")
        for q_idx, query in enumerate(queries, 1):
            print(f"    • Query {q_idx}: '{query}'")
        
        # Provider preferences
        providers = get_preferred_providers_for_segment(segment, RELATIVITY_SCRIPT)
        print(f"  Preferred Providers: {' → '.join(providers)}")
        
        print()
    
    print("\n3️⃣  SEMANTIC ENRICHMENT EXAMPLES")
    print("-" * 80)
    
    examples = [
        ("muones", "Direct particle reference"),
        ("dilatación del tiempo", "Time dilation concept"),
        ("Einstein", "Historical reference"),
        ("nave espacial a alta velocidad", "Complex multi-concept"),
    ]
    
    for example_text, description in examples:
        domains = detect_scientific_domains(RELATIVITY_SCRIPT)
        expansion = expand_segment_keywords(example_text, RELATIVITY_SCRIPT, domains)
        print(f"\n📌 {description}: '{example_text}'")
        print(f"   → Keywords: {', '.join(expansion['primary_keywords'][:4])}")
        print(f"   → Search Queries Will Be:")
        queries = build_multikeyword_queries(example_text, RELATIVITY_SCRIPT, num_queries=2)
        for q in queries:
            print(f"      • {q}")
    
    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 80)
    print("\n📋 SUMMARY:")
    print(f"  • Script identified as: {analysis['primary_theme']}")
    print(f"  • Recommended for multi-provider search with:")
    print(f"    - NASA/ESA for authoritative scientific content")
    print(f"    - Pexels/Pixabay for people/ships/visual effects")
    print(f"  • Each segment will use 2-3 semantically related keywords")
    print(f"  • Provider preference will shift based on segment content")
    print(f"  • Result: More relevant, coherent video selections for astronomy reels")

if __name__ == "__main__":
    test_script_analysis()
