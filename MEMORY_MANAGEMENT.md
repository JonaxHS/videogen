# Memory Management Guide

## Problem
The VPS can run out of disk/memory space due to accumulated video cache files, especially when generating many videos.

## Solutions Implemented

### 1. Docker Memory Limits
Updated `docker-compose.yml` with memory constraints:
- **Limit**: 1GB per container
- **Reservation**: 512MB per container
- **SwapLimit**: 1GB total

This prevents processes from consuming unlimited memory.

### 2. Automatic Cache Cleanup
The backend now automatically cleans up old cache files:

**Environment Variables** (add to `.env`):
```bash
# Max cache size in MB (default: 5000 = 5GB)
MAX_CACHE_SIZE_MB=5000

# Max file age in days before deletion (default: 7)
MAX_FILE_AGE_DAYS=7

# Limit FFmpeg encoder threads to reduce RAM spikes on small VPS (default: 2)
FFMPEG_THREADS=2
```

**How it works:**
- After each video download, the system checks cache size
- If cache exceeds `MAX_CACHE_SIZE_MB`, oldest files are removed
- Files older than `MAX_FILE_AGE_DAYS` are automatically deleted
- Cleanup runs at most every 60 seconds to avoid overhead

### 3. Manual Cleanup Script
Run manually or via cron:

```bash
# Show cache status only
python3 backend/cache_cleanup.py --status

# Clean up by size (keep cache under 4000 MB)
python3 backend/cache_cleanup.py --size 4000

# Clean up by age (remove files older than 3 days)
python3 backend/cache_cleanup.py --age 3

# Run both checks (default)
python3 backend/cache_cleanup.py --full
```

### 4. Scheduled Cleanup (Cron)
Set up daily cleanup at 2 AM:

```bash
# Make script executable
chmod +x backend/cleanup_cron.sh

# Add to crontab
crontab -e

# Add this line:
0 2 * * * /path/to/videogen/backend/cleanup_cron.sh

# Or use a container-based cron if running in Docker
```

### 5. Docker Prune
Clean up Docker images and unused volumes:

```bash
# Remove unused containers, networks, dangling images
docker system prune

# Also remove unused volumes
docker system prune -a --volumes
```

## Recommendations

**For Production VPS:**
1. Set `MAX_CACHE_SIZE_MB=2000` (2GB) for small VPS
2. Set `MAX_FILE_AGE_DAYS=3` to keep only recent videos
3. Run scheduled cleanup every night:
   ```bash
   0 2 * * * /path/to/videogen/backend/cleanup_cron.sh
   ```
4. Monitor disk usage:
   ```bash
   df -h
   du -sh /app/cache
   ```

**For Development:**
1. Keep defaults or increase `MAX_CACHE_SIZE_MB` to 10000
2. Disable automatic cleanup by setting `MAX_CACHE_SIZE_MB` very high
3. Run cleanup manually when needed

## Troubleshooting

**"no space left on device" error:**
1. Check disk usage: `df -h`
2. Run manual cleanup: `python3 backend/cache_cleanup.py --full`
3. If still low, reduce `MAX_CACHE_SIZE_MB` and restart
4. Delete old generated videos: `rm -f /app/output/*.mp4`

**Memory usage still high:**
1. Check container memory: `docker stats videogen-backend`
2. Reduce memory from 1GB to 512MB in docker-compose.yml
3. Reduce `MAX_CACHE_SIZE_MB` to 1000
4. Enable swap file on VPS if available

**Cron not running:**
1. Check if script is executable: `ls -l backend/cleanup_cron.sh`
2. View cron logs: `grep CRON /var/log/syslog` (Linux) or `log stream --predefined RemovedSources` (macOS)
3. Test manually: `bash backend/cleanup_cron.sh`
