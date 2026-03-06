#!/usr/bin/env python3
"""
Test script to verify keyword extraction produces different results for different scripts.
"""
import sys
sys.path.insert(0, 'backend')

from modules.script_parser import parse_script

# Script 1: Time travel to the PAST
script_past = """Imagina regresar   a tu infancia.   Hablar con tu yo niño.   Cambiar una decisión.  Según Einstein,   no es imposible.  La **relatividad general**   permite soluciones   donde el tiempo se curva   sobre sí mismo.   Se llaman **curvas cerradas de tiempo**.

¿Cómo crearlas?  🔸 Con un **agujero de gusano traversable**:   si mueves una boca a alta velocidad   y la otra la dejas quieta,   se crea una diferencia temporal.   Entrar por una boca   te lleva al pasado de la otra.

🔸 Con un **cilindro cósmico infinito**   girando a casi la luz:   su rotación arrastra el espacio-tiempo   hasta formar un bucle temporal.

🔸 Incluso en un **universo rotante**,   como el modelo de Gödel,   podrías navegar en círculos   y regresar a tu propio pasado.

Pero hay problemas.  Primero, las **paradojas**:   si matas a tu abuelo,   ¿cómo naciste para viajar?   Algunos proponen   la **hipótesis de consistencia**:   solo puedes hacer   lo que ya ocurrió.   Otros, los **multiversos**:   cada acción crea una nueva línea temporal.

Segundo, la **conjetura de protección cronológica**   de Stephen Hawking:   la física cuántica   —específicamente, la radiación de vacío—   se volvería infinita   al intentar formar una CTC,   destruyendo el túnel antes de usarse."""

# Script 2: Time travel to the FUTURE
script_future = """Imagina que viajas al futuro.  
No con una máquina mágica.  
Sino con velocidad…  
o gravedad.

Y según Einstein,  
ya es posible.

La **relatividad especial** dice:  
mientras más rápido te mueves,  
más lento avanza tu tiempo.  
A 90% de la luz,  
1 año para ti  
son 2.3 años en la Tierra.  
A 99.995%,  
1 año tuyo = 100 años allá.

La **relatividad general** añade:  
cerca de un agujero negro,  
el tiempo se ralentiza.  
Horas tuyas  
pueden ser siglos en casa.

Y esto no es especulación.  
Es **realidad medida**.

🔹 Los **muones** —partículas subatómicas—  
viven 2.2 microsegundos en reposo.  
Pero al moverse a 0.99c,  
llegan a la superficie terrestre  
porque su tiempo se dilata.

🔹 En 1971, los experimentos **Hafele-Keating**  
pusieron relojes atómicos en aviones.  
Al regresar,  
estaban ligeramente más jóvenes  
que los de tierra.

🔹 Hoy, el **GPS** corrige la dilatación  
cada segundo.  
Sin Einstein,  
te perderías 10 km por día."""

def test_keywords():
    print("=" * 80)
    print("TESTING KEYWORD EXTRACTION")
    print("=" * 80)
    
    print("\n" + "─" * 80)
    print("SCRIPT 1: TIME TRAVEL TO THE PAST (CTCs, Wormholes, Paradoxes)")
    print("─" * 80)
    segments_past = parse_script(script_past)
    for i, seg in enumerate(segments_past[:5]):  # First 5 segments
        print(f"\nSegment {i+1}:")
        print(f"  Text: {seg['text'][:100]}...")
        print(f"  Keywords: {seg['keywords']}")
    
    print("\n" + "─" * 80)
    print("SCRIPT 2: TIME TRAVEL TO THE FUTURE (Velocity, Time Dilation, GPS)")
    print("─" * 80)
    segments_future = parse_script(script_future)
    for i, seg in enumerate(segments_future[:5]):  # First 5 segments
        print(f"\nSegment {i+1}:")
        print(f"  Text: {seg['text'][:100]}...")
        print(f"  Keywords: {seg['keywords']}")
    
    print("\n" + "=" * 80)
    print("COMPARISON: Are keywords different?")
    print("=" * 80)
    
    keywords_past_all = " ".join([seg['keywords'] for seg in segments_past])
    keywords_future_all = " ".join([seg['keywords'] for seg in segments_future])
    
    print(f"\nPast script keywords: {sorted(set(keywords_past_all.split()))[:20]}")
    print(f"\nFuture script keywords: {sorted(set(keywords_future_all.split()))[:20]}")
    
    common = set(keywords_past_all.split()) & set(keywords_future_all.split())
    unique_past = set(keywords_past_all.split()) - set(keywords_future_all.split())
    unique_future = set(keywords_future_all.split()) - set(keywords_past_all.split())
    
    print(f"\n✅ Common keywords ({len(common)}): {sorted(common)[:10]}")
    print(f"📍 Unique to PAST ({len(unique_past)}): {sorted(unique_past)[:10]}")
    print(f"📍 Unique to FUTURE ({len(unique_future)}): {sorted(unique_future)[:10]}")
    
    if len(unique_past) > 5 and len(unique_future) > 5:
        print("\n✅ SUCCESS: Scripts generate significantly different keywords!")
    else:
        print("\n⚠️  WARNING: Keywords still too similar between scripts")

if __name__ == "__main__":
    test_keywords()
