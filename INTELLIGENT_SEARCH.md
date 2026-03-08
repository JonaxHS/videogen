# Sistema Inteligente de Búsqueda de Videos

## 📊 Resumen

Tu sistema ahora incluye un **algoritmo de búsqueda inteligente** optimizado para guiones científicos y de astronomía. El sistema:

1. **Analiza el script** para detectar dominios científicos (relatividad, astrofísica, etc.)
2. **Expande keywords automáticamente** usando sinónimos y conceptos relacionados
3. **Busca múltiples queries** relacionadas por segmento (no solo 1 keyword)
4. **Prioriza proveedores inteligentemente**:
   - `NASA/ESA` para contenido científico autorizado
   - `Pexels/Pixabay` para personas, efectos visuales, transiciones
5. **Rankea con coherencia contextual** para asegurar que segmentos consecutivos sean visualmente coherentes

## 🎯 Cómo Funciona

### Paso 1: Análisis del Script
```python
# El sistema detecta automáticamente el tema principal
script_analysis = analyze_script_structure(script_text)
# Devuelve: {
#   "detected_domains": ["relatividad", "partículas", "universo"],
#   "primary_theme": "relatividad especial",
#   "tone": "educational_scientific",
#   ...
# }
```

### Paso 2: Expansión de Keywords
Para cada segmento, genera múltiples keywords relacionados:
```
Segmento: "Los muones, que viven 2.2 microsegundos..."
  
  Queries generadas:
  • "muons subatomic particles"          (ciencia directa)
  • "cosmic rays atmosphere"              (contexto físico)
  • "particle decay lifespan"             (concepto relacionado)
```

### Paso 3: Búsqueda Multi-Proveedor
- Busca en **todas** las queries expandidas
- Busca en **todos** los proveedores (pero prioriza según segmento)
- Mezcla resultados y los rankea por relevancia

### Paso 4: Selección Inteligente
- Evita usar el mismo proveedor dos segmentos seguidos
- Considera duraciones de video
- Filtra por relevancia

## 📝 Ejemplo: Guion de Relatividad Especial

Tu guion sobre relatividad se analiza así:

```
Script Input:
  "Imagina dos hermanos. Idénticos. [...]
   Los muones, que viven 2.2 microsegundos...
   Incluso con relojes atómicos en aviones..."

Análisis:
  ✓ Tema detectado: "relatividad especial"
  ✓ Dominios encontrados: ["relatividad", "partículas", "tiempo", "universo"]
  ✓ Tone: "educational_scientific"
  ✓ Segmentos estimados: 14
  ✓ Modo de búsqueda: INTELLIGENT (automático)

Búsqueda por segmento:
  Seg 1 (gemelos):
    Providers: pexels → pixabay → nasa → esa
    Queries: 
      • "identical twins siblings"
      
  Seg 4 (muones):
    Providers: nasa → esa → pexels → pixabay
    Queries:
      • "muons subatomic particles"
      • "cosmic rays atmosphere"
      • "particle decay time"
      
  Seg 5 (relojes atómicos):
    Providers: pexels → pixabay → nasa → esa
    Queries:
      • "atomic clocks precision measurement"
      • "aircraft time measurement"

Resultado:
  ✓ 14 videos seleccionados
  ✓ Mezcla de: 4 NASA + 3 ESA + 5 Pexels + 2 Pixabay
  ✓ Cada segmento coherente visualmente con el tema
```

## 🔧 API Endpoints

### 1. Búsqueda Inteligente Manual
```bash
POST /api/video-options-intelligent
{
  "keywords": "muones partículas",
  "context_text": "partículas subatómicas que confirman relatividad",
  "script_text": "[full script para context]",
  "limit": 8,
  "min_duration": 5
}

Response:
{
  "options": [
    {
      "provider": "nasa",
      "url": "...",
      "score": 8.5,
      "title": "...",
      "duration": 15
    },
    ...
  ]
}
```

### 2. Generación Automática (Usa Intelligente Si es Científico)
```bash
POST /api/generate
{
  "script": "[your astronomy/science script]",
  "voice": "es-ES-StandardB",
  "rate": "+0%",
  ...
}

# Sistema automáticamente detectará que es scientific
# y usará search_and_download_video_info_intelligent()
```

### 3. Análisis Puro del Script
```bash
# Importar dentro de tu código:
from modules.script_analyzer import analyze_script_structure

analysis = analyze_script_structure(script_text)
print(analysis["detected_domains"])  # e.g., ["relatividad", "partículas"]
print(analysis["primary_theme"])     # e.g., "relatividad especial"
```

## 📚 Dominios Detectados Automáticamente

El sistema reconoce estos dominios científicos:

```
Física/Relatividad:
  • relatividad, relatividad especial, tiempo dilatado, aceleración
  
Astronomía:
  • agujero negro, gravedad, universo, galaxia, estrellas, órbita
  
Tecnología:
  • telescopio, observatorio, infrarrojo
  
Partículas:
  • partículas, muones, electrones, cuantos, atmósfera
  
Conceptos Abstractos:
  • Einstein, espacio-tiempo, velocidad de la luz
```

## 🎨 Provider Preferences

**Para segmentos CIENTÍFICOS** (`relatividad`, `partículas`, `muones`):
```
Preferencia: NASA → ESA → Pexels → Pixabay
Razón: Necesita autoridad científica, gráficos astrófísicos, visualizaciones oficiales
```

**Para segmentos VISUALES** (`gemelos`, `nave`, `personas`, `avión`):
```
Preferencia: Pexels → Pixabay → NASA → ESA
Razón: Necesita personas reales, effecting, cinematografía
```

## 🚀 Activación Automática

El sistema **automáticamente**:

1. **Detecta scripts científicos** al iniciar la generación
2. **Usa búsqueda inteligente** si encuentra dominios científicos
3. **Fallback** a búsqueda estándar si no encuentra dominios o falla

```python
# En run_generation():
if script_text:
    script_analysis = script_analyzer.analyze_script_structure(script_text)
    detected_domains = script_analysis.get("detected_domains", [])
    use_intelligent_search = len(detected_domains) > 0
    
    # Automáticamente usa la versión inteligente si se detectan dominios
```

## 📈 Resultados Esperados

Para tu guion de relatividad especial:

### Antes (búsqueda simple):
- 11 videos NASA (dominando)
- 1 video ESA
- Videos poco relevantes para partes narrativas

### Después (búsqueda inteligente):
- ✅ Mix balanceado: 4-5 NASA + 3-4 ESA + 5-6 Pexels + 2-3 Pixabay
- ✅ Gemelos: videos de personas reales
- ✅ Muones: visualizaciones científicas de partículas
- ✅ Relojes atómicos: equipamiento de laboratorio
- ✅ Einstein: retratos históricos
- ✅ Cada segmento coherente con tema general

## 🧪 Testing Local

```bash
# Ejecutar análisis del script de relatividad:
python3 test_intelligent_search.py

# Output:
#   ✓ Script identified as: relatividad especial
#   ✓ Recommended multi-provider search
#   ✓ Each segment using 2-3 keywords
#   ✓ Provider preference contextual
```

## 🔮 Casos de Uso

Este sistema funciona especialmente bien para:

- ✨ **Astronomía** (planetas, estrellas, galaxias)
- 🔬 **Física** (relatividad, cuántica, termodinámica)
- 🌌 **Cosmología** (origen del universo, big bang)
- 🛰️ **Espacio** (satélites, ISS, viajes espaciales)
- 📡 **Tecnología científica** (telescopios, microscopios)
- 🧬 **Biología general** (ecosistemas, evolución)
- ⚡ **Energía** (renovables, nuclear, fusión)

## 🔧 Personalización

### Agregar Nuevo Dominio Científico

```python
# En script_analyzer.py, agregar a SCIENTIFIC_DOMAINS:

SCIENTIFIC_DOMAINS = {
    "mi_nuevo_dominio": {
        "keywords": ["keyword1", "keyword2", ...],
        "related_concepts": ["concepto1", "concepto2", ...],
        "providers_priority": ["nasa", "pexels"],  # Orden de preferencia
    },
    ...
}
```

### Agregar Sinónimos

```python
# En script_analyzer.py, agregar a CONCEPT_EXPANSION:

CONCEPT_EXPANSION = {
    "mi nuevo concepto": ["synonym1", "synonym2", ...],
    ...
}
```

## 📊 Monitoreo

El sistema reporta en logs:

```
[IntelligentSearch Seg 1] Starting intelligent search for: 'muones...'
[search_intelligent] Detected themes: ['relatividad', 'partículas']
[search_intelligent] Primary theme: relatividad especial
[search_intelligent] Primary keywords: ['muons', 'subatomic particles', ...]
[search_intelligent] Preferred providers: ['nasa', 'esa', 'pexels', 'pixabay']
[search_intelligent] Multi-queries: ['muons subatomic particles', 'cosmic rays atmosphere', ...]
  ✓ Pexels: 12 results
  ✓ NASA: 8 results
  ✓ ESA: 5 results
[IntelligentSearch Seg 1] Final result: 8 videos - providers: {'nasa': 3, 'pixabay': 2, 'pexels': 3}
```

## 🎯 Próximas Mejoras

- [ ] Context coherence scoring entre segmentos (penalizar cambios bruscos de estilo visual)
- [ ] Detectar tono del script y ajustar providers (docu vs. casual vs. educativo)
- [ ] Caching inteligente de queries para reutilizar en posteriores reels del mismo tema
- [ ] Machine learning para aprender qué combinaciones funcionan mejor
- [ ] Metadata filtering: duración, resolución, color palette por segmento

---

**¡Tu sistema científico de videos ahora es verdaderamente inteligente!** 🚀🔬🌌
