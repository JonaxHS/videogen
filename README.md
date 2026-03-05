# VideoGen 🎬

Generador de Reels con IA: pega tu guion, genera voz real, busca videos de stock (Pexels + Pixabay) con matching inteligente por contexto y sincroniza todo automáticamente.

## Stack
- **Backend**: Python 3.11 + FastAPI + FFmpeg
- **TTS**: [edge-tts](https://github.com/rany2/edge-tts) (voces neurales Microsoft, sin API key)
- **Video Stock**: Pexels API + Pixabay API (gratis)
- **Frontend**: React + Vite (TypeScript)
- **Contenedores**: Docker + Docker Compose

## Quick Start

```bash
# 1. Clonar y entrar al proyecto
cd Videogen

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env y agregar al menos una key de video: PEXELS_API_KEY o PIXABAY_API_KEY

# 3. Levantar con Docker
docker compose up --build

# 4. Abrir en el navegador
# http://localhost:5173
```

## Cómo usar

1. **Pega tu guion** en el textarea — separa los segmentos con una línea en blanco
2. **Elige la voz** (Dalia MX, Jorge MX, Elvira ES, etc.)
3. **Ajusta la velocidad** con el slider
4. **Clic en "Generar Reel"** y espera a que el progreso llegue al 100%
5. **Reproduce y descarga** tu video en formato 9:16 MP4

### Matching inteligente de video

- El buscador usa `keywords` y texto completo del párrafo para elegir clips más relevantes.
- Combina resultados de Pexels y Pixabay y selecciona el mejor por relevancia + duración + resolución.
- El compositor adapta automáticamente videos horizontales o verticales al formato final 9:16.

## Variables de Entorno (.env)

| Variable | Descripción |
|---|---|
| `PEXELS_API_KEY` | API Key de Pexels (gratis en pexels.com/api) |
| `PIXABAY_API_KEY` | API Key de Pixabay (gratis en pixabay.com/api/docs) |
| `ELEVENLABS_API_KEY` | (Opcional) API Key para voces premium de ElevenLabs |
| `DEEPGRAM_API_KEY` | (Opcional) API Key para voces premium de Deepgram |
| `CORS_ORIGINS` | (Opcional) Orígenes permitidos por CORS, separados por coma |

## Voces disponibles

| ID | Nombre |
|---|---|
| `es-MX-DaliaNeural` | Dalia (Mujer · México) |
| `es-MX-JorgeNeural` | Jorge (Hombre · México) |
| `es-ES-ElviraNeural` | Elvira (Mujer · España) |
| `es-ES-AlvaroNeural` | Álvaro (Hombre · España) |
| `es-AR-ElenaNeural` | Elena (Mujer · Argentina) |
| `es-CO-SalomeNeural` | Salomé (Mujer · Colombia) |

## Puertos

| Servicio | Puerto |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
