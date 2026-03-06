# Guía Rápida de Docker

## 📦 Uso Eficiente de Docker Compose

### Cambios SOLO en código (Python/TypeScript)
```bash
# Opción 1: Reiniciar solo el servicio modificado (más rápido, ~5-10 seg)
sudo docker compose restart backend
# o
sudo docker compose restart frontend

# Opción 2: Recrear contenedores sin rebuild (~30 seg)
sudo docker compose up -d
```

### Cambios en dependencias (requirements.txt / package.json)
```bash
# Ahora con los Dockerfiles optimizados, esto es más rápido (~3-5 min)
sudo docker compose up -d --build

# O rebuild solo el servicio específico
sudo docker compose up -d --build backend
```

### Cambios en Dockerfile o docker-compose.yml
```bash
# Rebuild completo necesario
sudo docker compose up -d --build
```

## ⚡ Optimizaciones Implementadas

### Backend Dockerfile
- ✅ Dependencias del sistema en capa separada
- ✅ `requirements.txt` copiado ANTES del código
- ✅ Torch (~800MB) + Sentence-Transformers (~240MB) solo se reinstalan si cambia requirements.txt
- ✅ Cambios en código Python NO invalidan caché de pip install

### Frontend Dockerfile  
- ✅ `package.json` copiado ANTES del código
- ✅ `npm install` en capa separada
- ✅ Cambios en .tsx/.ts/.css NO invalidan caché de node_modules

### .dockerignore
- ✅ Excluye cache/, node_modules, __pycache__ del contexto de build
- ✅ Reduce tamaño del contexto enviado al daemon de Docker

## 🚀 Workflow Recomendado

### Desarrollo Local (Mac)
```bash
# Editar código...
git add .
git commit -m "mensaje"
git push origin main
```

### Despliegue en VPS
```bash
cd /opt/videogen
git pull origin main

# Si solo cambiaste código Python/JS:
sudo docker compose restart backend  # o frontend

# Si cambiaste dependencias:
sudo docker compose up -d --build
```

## 📊 Tiempos Esperados (VPS típico)

| Operación | Tiempo | Cuándo usar |
|-----------|--------|-------------|
| `restart backend` | ~5-10 seg | Cambios en .py |
| `up -d` | ~30 seg | Sin cambios de dependencias |
| `up -d --build` (optimizado) | ~3-5 min | Primera vez o cambio en requirements.txt |
| `up -d --build` (sin optimizar) | ~10-15 min | ❌ Evitar |

## 🔍 Verificar Caché de Docker

```bash
# Ver imágenes y tamaños
sudo docker images

# Ver qué capas se están usando
sudo docker history videogen-backend:latest

# Limpiar caché antiguo (libera espacio)
sudo docker system prune -a
```

## 💡 Tips

1. **Nunca uses `--build` si solo cambias código** - El caché lo hace innecesario
2. **Usa `restart` para cambios rápidos** - Recarga el código sin recrear contenedor  
3. **El primer build siempre es lento** - Posteriores serán rápidos gracias al caché
4. **Mira los logs durante build** - `Using cache` significa que va rápido ✅

## 🐛 Troubleshooting

### Build sigue siendo lento después de optimización
```bash
# Limpiar caché de Docker y rebuild desde cero
sudo docker system prune -a
sudo docker compose up -d --build
```

### Cambios no se reflejan después de restart
```bash
# El código puede estar cacheado por Python/Node
sudo docker compose up -d --force-recreate
```

### Error "no space left on device"
```bash
# Limpiar caché viejo y contenedores detenidos
sudo docker system prune -a
# Ver uso de disco
df -h
```
