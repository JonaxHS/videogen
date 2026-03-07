#!/bin/bash
# Ubuntu VPS Disk Cleanup Script for VideoGen
# Usage: bash vps_cleanup.sh

set -e

echo "================================================"
echo "🧹 VideoGen VPS Ubuntu Cleanup Tool"
echo "================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   echo "Run with: sudo bash vps_cleanup.sh"
   exit 1
fi

# Step 1: Diagnose
echo -e "${YELLOW}1️⃣  DIAGNOSING DISK USAGE...${NC}"
echo ""

echo "💾 Top space consumers:"
du -sh /* 2>/dev/null | sort -rh | head -10
echo ""

# Step 2: Docker cleanup
echo -e "${YELLOW}2️⃣  CLEANING DOCKER...${NC}"
if command -v docker &> /dev/null; then
    echo "Docker system information:"
    docker system df
    echo ""
    
    echo "Removing unused containers, images, networks..."
    docker system prune -f --volumes
    echo -e "${GREEN}✓ Docker cleaned${NC}"
else
    echo "Docker not installed"
fi
echo ""

# Step 3: VideoGen cache cleanup
echo -e "${YELLOW}3️⃣  CLEANING VIDEOGEN CACHE...${NC}"
if [ -d "/app/cache/videos" ]; then
    CACHE_SIZE=$(du -sh /app/cache/videos | cut -f1)
    echo "Cache size before: $CACHE_SIZE"
    
    # Run Python cleanup
    if [ -f "/app/cache_cleanup.py" ]; then
        python3 /app/cache_cleanup.py --full
    else
        # Alternative: manual cleanup
        find /app/cache/videos -type f -mtime +3 -delete
        echo "✓ Removed files older than 3 days"
    fi
    
    CACHE_SIZE_AFTER=$(du -sh /app/cache/videos 2>/dev/null | cut -f1)
    echo -e "${GREEN}Cache size after: $CACHE_SIZE_AFTER${NC}"
else
    echo "Cache directory not found"
fi
echo ""

# Step 4: Remove old videos
echo -e "${YELLOW}4️⃣  CLEANING OLD GENERATED VIDEOS...${NC}"
if [ -d "/app/output" ]; then
    FILE_COUNT=$(find /app/output -name "*.mp4" 2>/dev/null | wc -l)
    echo "Videos found: $FILE_COUNT"
    
    echo "Removing videos older than 7 days..."
    find /app/output -type f -name "*.mp4" -mtime +7 -delete
    
    FILE_COUNT_AFTER=$(find /app/output -name "*.mp4" 2>/dev/null | wc -l)
    echo -e "${GREEN}Videos after cleanup: $FILE_COUNT_AFTER${NC}"
else
    echo "Output directory not found"
fi
echo ""

# Step 5: System cleanup
echo -e "${YELLOW}5️⃣  SYSTEM CLEANUP...${NC}"

# Remove package manager cache
apt clean
apt autoclean
echo "✓ APT cache cleaned"

# Remove old logs
journalctl --vacuum=3d
echo "✓ System logs cleaned (keeping last 3 days)"

# Remove temp files
find /tmp -type f -atime +5 -delete 2>/dev/null
find /var/tmp -type f -atime +5 -delete 2>/dev/null
echo "✓ Temp files cleaned"
echo ""

# Step 6: Final report
echo -e "${YELLOW}6️⃣  FINAL REPORT${NC}"
echo ""
echo "📊 Disk usage:"
df -h | grep -E '^Filesystem|/$'
echo ""

echo "Docker containers:"
docker ps -a --format "table {{.Names}}\t{{.Size}}" 2>/dev/null || echo "No containers running"
echo ""

echo "VideoGen directories:"
echo "Cache:  $(du -sh /app/cache 2>/dev/null | cut -f1 || echo 'N/A')"
echo "Output: $(du -sh /app/output 2>/dev/null | cut -f1 || echo 'N/A')"
echo ""

echo -e "${GREEN}================================================"
echo "✅ CLEANUP COMPLETE!"
echo "================================================${NC}"
echo ""
echo "💡 Next steps:"
echo "1. Monitor disk: df -h"
echo "2. Set up auto-cleanup (add to crontab):"
echo "   0 2 * * * /path/to/vps_cleanup.sh >> /var/log/videogen_cleanup.log 2>&1"
echo ""
