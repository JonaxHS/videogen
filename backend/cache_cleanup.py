#!/usr/bin/env python3
"""
Cache Cleanup Utility
Removes old video cache files to prevent disk exhaustion.
Can be run manually or scheduled via cron.
"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import argparse

CACHE_DIR = Path("/app/cache/videos")
MAX_CACHE_SIZE_MB = int(os.getenv("MAX_CACHE_SIZE_MB", "5000"))  # Default 5GB
MAX_FILE_AGE_DAYS = int(os.getenv("MAX_FILE_AGE_DAYS", "7"))  # Default 7 days


def get_cache_size():
    """Get total cache size in MB."""
    if not CACHE_DIR.exists():
        return 0
    total = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def cleanup_by_size(target_mb=None):
    """Remove oldest files until cache is below target size."""
    target = target_mb or MAX_CACHE_SIZE_MB
    current_size = get_cache_size()
    
    if current_size <= target:
        print(f"✓ Cache size ({current_size:.1f} MB) is within limit ({target} MB)")
        return
    
    print(f"⚠ Cache size ({current_size:.1f} MB) exceeds limit ({target} MB). Cleaning...")
    
    # Get all files sorted by modification time (oldest first)
    files = sorted(
        (f for f in CACHE_DIR.rglob("*") if f.is_file()),
        key=lambda f: f.stat().st_mtime
    )
    
    removed_count = 0
    removed_mb = 0
    
    for file_path in files:
        if current_size <= target:
            break
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        try:
            file_path.unlink()
            removed_count += 1
            removed_mb += file_size_mb
            current_size -= file_size_mb
            print(f"  Removed: {file_path.name} ({file_size_mb:.1f} MB)")
        except Exception as e:
            print(f"  Error removing {file_path.name}: {e}")
    
    print(f"✓ Cleanup complete: removed {removed_count} files ({removed_mb:.1f} MB)")


def cleanup_by_age(days=None):
    """Remove files older than specified days."""
    max_age = days or MAX_FILE_AGE_DAYS
    cutoff_time = (datetime.now() - timedelta(days=max_age)).timestamp()
    
    if not CACHE_DIR.exists():
        print("✓ Cache directory does not exist")
        return
    
    files_before = len(list(CACHE_DIR.rglob("*")))
    removed_count = 0
    removed_mb = 0
    
    for file_path in CACHE_DIR.rglob("*"):
        if not file_path.is_file():
            continue
        
        if file_path.stat().st_mtime < cutoff_time:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            try:
                file_path.unlink()
                removed_count += 1
                removed_mb += file_size_mb
                print(f"  Removed (age): {file_path.name} ({file_size_mb:.1f} MB)")
            except Exception as e:
                print(f"  Error removing {file_path.name}: {e}")
    
    print(f"✓ Age-based cleanup: removed {removed_count} files ({removed_mb:.1f} MB)")


def cleanup_empty_dirs():
    """Remove empty subdirectories."""
    if not CACHE_DIR.exists():
        return
    
    for dirpath in sorted(CACHE_DIR.rglob("*"), reverse=True):
        if dirpath.is_dir():
            try:
                dirpath.rmdir()
                print(f"  Removed empty directory: {dirpath}")
            except OSError:
                pass  # Directory not empty, skip


def main():
    parser = argparse.ArgumentParser(description="Clean up video cache")
    parser.add_argument("--size", type=float, help=f"Target cache size in MB (default {MAX_CACHE_SIZE_MB})")
    parser.add_argument("--age", type=int, help=f"Remove files older than N days (default {MAX_FILE_AGE_DAYS})")
    parser.add_argument("--full", action="store_true", help="Run both size and age cleanup")
    parser.add_argument("--status", action="store_true", help="Show cache status only")
    
    args = parser.parse_args()
    
    size = get_cache_size()
    print(f"\n📊 Cache Status:")
    print(f"  Location: {CACHE_DIR}")
    print(f"  Current Size: {size:.1f} MB")
    print(f"  Max Size: {MAX_CACHE_SIZE_MB} MB")
    print(f"  Max Age: {MAX_FILE_AGE_DAYS} days\n")
    
    if args.status:
        return
    
    if args.full or (args.size is None and args.age is None):
        cleanup_by_age(args.age)
        cleanup_by_size(args.size)
        cleanup_empty_dirs()
    else:
        if args.age is not None:
            cleanup_by_age(args.age)
        if args.size is not None:
            cleanup_by_size(args.size)
        cleanup_empty_dirs()
    
    print(f"\n✓ Final cache size: {get_cache_size():.1f} MB\n")


if __name__ == "__main__":
    main()
