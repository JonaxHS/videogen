#!/bin/bash
# Monitor VPS Memory and Disk Usage
# Usage: ./monitor_vps.sh

echo "================================================"
echo "📊 VPS Memory & Disk Monitor - VideoGen"
echo "================================================"
echo ""

# System Memory
echo "💾 RAM Usage:"
free -h
echo ""

# Disk Usage
echo "💿 Disk Usage:"
df -h | grep -E '^Filesystem|/$|/app'
echo ""

# Docker Container Stats
echo "🐳 Docker Container Memory:"
if command -v docker &> /dev/null; then
    if [ "$(docker ps -q)" ]; then
        docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}\t{{.CPUPerc}}\t{{.Name}}" | head -10
    else
        echo "No running containers"
    fi
else
    echo "Docker not available"
fi
echo ""

# Cache Directory Size
echo "📦 Video Cache Size:"
if [ -d "/app/cache/videos" ]; then
    CACHE_SIZE=$(du -sh /app/cache/videos 2>/dev/null | cut -f1)
    FILE_COUNT=$(find /app/cache/videos -type f 2>/dev/null | wc -l)
    echo "Location: /app/cache/videos"
    echo "Size: $CACHE_SIZE"
    echo "Files: $FILE_COUNT"
elif [ -d "./backend/cache/videos" ]; then
    CACHE_SIZE=$(du -sh ./backend/cache/videos 2>/dev/null | cut -f1)
    FILE_COUNT=$(find ./backend/cache/videos -type f 2>/dev/null | wc -l)
    echo "Location: ./backend/cache/videos"
    echo "Size: $CACHE_SIZE"
    echo "Files: $FILE_COUNT"
else
    echo "Cache directory not found"
fi
echo ""

# Output Directory Size
echo "📹 Generated Videos:"
if [ -d "/app/output" ]; then
    OUTPUT_SIZE=$(du -sh /app/output 2>/dev/null | cut -f1)
    FILE_COUNT=$(find /app/output -name "*.mp4" 2>/dev/null | wc -l)
    echo "Location: /app/output"
    echo "Size: $OUTPUT_SIZE"
    echo "Files: $FILE_COUNT"
elif [ -d "./output" ]; then
    OUTPUT_SIZE=$(du -sh ./output 2>/dev/null | cut -f1)
    FILE_COUNT=$(find ./output -name "*.mp4" 2>/dev/null | wc -l)
    echo "Location: ./output"
    echo "Size: $OUTPUT_SIZE"
    echo "Files: $FILE_COUNT"
else
    echo "Output directory not found"
fi
echo ""

# Docker Images Size
echo "🖼️  Docker Images:"
if command -v docker &> /dev/null; then
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E 'REPOSITORY|videogen'
else
    echo "Docker not available"
fi
echo ""

# Oldest Cache Files
echo "🕐 Oldest Cached Videos:"
if [ -d "/app/cache/videos" ]; then
    find /app/cache/videos -type f -printf '%T+ %p\n' 2>/dev/null | sort | head -5 | awk '{print $1, $2}'
elif [ -d "./backend/cache/videos" ]; then
    find ./backend/cache/videos -type f -printf '%T+ %p\n' 2>/dev/null | sort | head -5 | awk '{print $1, $2}'
fi
echo ""

echo "================================================"
echo "💡 Tips:"
echo "  - Run cleanup: python3 backend/cache_cleanup.py --full"
echo "  - Watch live: watch -n 5 './monitor_vps.sh'"
echo "  - Docker prune: docker system prune -a"
echo "================================================"
