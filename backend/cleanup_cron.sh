#!/bin/bash
# Cleanup cache videos daily at 2 AM
# Add this to crontab: 0 2 * * * /path/to/videogen/backend/cleanup_cron.sh

cd "$(dirname "$0")"
/usr/bin/python3 cache_cleanup.py --full >> /var/log/videogen_cache_cleanup.log 2>&1
