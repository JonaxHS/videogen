# VideoGen 🎬

Generador de Reels con IA: pega tu guion, genera voz real, busca videos de stock y sincroniza todo automáticamente.

## Stack
- **Backend**: Python 3.11 + FastAPI + FFmpeg
- **TTS**: [edge-tts](https://github.com/rany2/edge-tts) (voces neurales Microsoft, sin API key)
- **Video Stock**: Pexels API (gratis)
- **Frontend**: React + Vite (TypeScript)
- **Contenedores**: Docker + Docker Compose

## Quick Start

```bash
# 1. Clonar y entrar al proyecto
cd Videogen

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env y agregar tu PEXELS_API_KEY

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

## Variables de Entorno (.env)

| Variable | Descripción |
|---|---|
| `PEXELS_API_KEY` | API Key de Pexels (gratis en pexels.com/api) |

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
