# VideoGen 🎬

Generador de Reels con IA: pega tu guion, genera voz real, busca videos de stock (Pexels + Pixabay + NASA + ESA) con matching inteligente por contexto y sincroniza todo automáticamente.

## Stack
- **Backend**: Python 3.11 + FastAPI + FFmpeg
- **TTS**: [edge-tts](https://github.com/rany2/edge-tts) (voces neurales Microsoft, sin API key)
- **Video Stock**: Pexels API + Pixabay API + NASA Image and Video Library
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
- Combina resultados de Pexels, Pixabay, NASA e ESA y selecciona el mejor por relevancia + calidad.
- El compositor adapta automáticamente videos horizontales o verticales al formato final 9:16.

## Variables de Entorno (.env)

| Variable | Descripción |
|---|---|
| `PEXELS_API_KEY` | API Key de Pexels (gratis en pexels.com/api) |
| `PIXABAY_API_KEY` | API Key de Pixabay (gratis en pixabay.com/api/docs) |
| `ELEVENLABS_API_KEY` | (Opcional) API Key para voces premium de ElevenLabs |
| `DEEPGRAM_API_KEY` | (Opcional) API Key para voces premium de Deepgram |
| `CORS_ORIGINS` | (Opcional) Orígenes permitidos por CORS, separados por coma |
| `NASA_INTRO_SKIP_SECONDS` | (Opcional) Segundos a saltar en intros de NASA (default: 2.0) |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram (obligatorio para integración) |
| `TELEGRAM_BACKEND_URL` | URL interna del backend usada por el bot (default: `http://backend:8000`) |
| `PUBLIC_BACKEND_URL` | URL pública opcional para mensajes de fallback |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Lista opcional de chat IDs permitidos, separados por coma |
| `TELEGRAM_DEFAULT_VOICE` | Voz por defecto para generar desde Telegram |
| `TELEGRAM_DEFAULT_RATE` | Velocidad por defecto en Telegram (ej: `+0%`) |
| `TELEGRAM_DEFAULT_PITCH` | Pitch por defecto en Telegram (ej: `+0Hz`) |
| `TELEGRAM_DEFAULT_SHOW_SUBTITLES` | `true`/`false` para subtítulos por defecto |
| `TELEGRAM_DEFAULT_SUBTITLE_STYLE` | Estilo por defecto (`classic`, `luminous`, `cinema`, `yellow-subtitle`, `minimal`, `neon`, `karaoke`) |

## Integraciones de video

### Proveedores soportados
- **Pexels**: Stock de video general (requiere API key)
- **Pixabay**: Stock de video general (requiere API key)
- **NASA**: Videos de espacio, astronomía y misiones espaciales (sin API key necesaria)
- **ESA**: Videos del Hubble, satélites y misiones de la European Space Agency (sin API key necesaria)

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

## Bot de Telegram 🤖

Con el servicio `telegram-bot`, puedes mandar un guion por chat y recibir el video terminado.

### 1) Crear bot
- Habla con `@BotFather` en Telegram
- Ejecuta `/newbot`
- Copia el token y pégalo en `.env` en `TELEGRAM_BOT_TOKEN`

### 2) Levantar servicios

```bash
docker compose up -d --build
```

Esto levanta `backend`, `frontend` y `telegram-bot`.

### 3) Usar el bot
- Envíale texto normal con tu guion, o
- Usa `/generate tu guion aquí`

El bot:
1. Crea el job en `/api/generate`
2. Monitorea progreso con `/api/status/{job_id}`
3. Descarga `/api/download/{job_id}`
4. Te envía el MP4 directo al chat
