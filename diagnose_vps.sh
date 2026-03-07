#!/bin/bash
# Quick commands to diagnose disk usage on VPS
# Run these on your VPS: ssh user@your_vps.com 'bash -s' < diagnose.sh

echo "1️⃣  What's using the most space?"
sudo du -sh /* 2>/dev/null | sort -rh | head -10

echo ""
echo "2️⃣  Docker disk usage:"
docker system df

echo ""
echo "3️⃣  Cache directory:"
du -sh /app/cache 2>/dev/null || echo "No /app/cache"

echo ""
echo "4️⃣  Output directory:"
du -sh /app/output 2>/dev/null || echo "No /app/output"

echo ""
echo "5️⃣  Docker images:"
docker images --format "{{.Repository}}\t{{.Tag}}\t{{.Size}}"

echo ""
echo "6️⃣  Container sizes:"
docker ps -a --format "table {{.Names}}\t{{.Size}}"

echo ""
echo "7️⃣  Running containers memory:"
docker stats --no-stream --format "table {{.Names}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo ""
echo "8️⃣  Largest files in cache:"
find /app/cache -type f -exec ls -lh {} \; 2>/dev/null | awk '{print $5, $9}' | sort -rh | head -10
