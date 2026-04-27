"""
Flush Webhook Cache
===================
Run this script to move ALL pending webhook files (both sniffer queue
and pending_retry) into the processed/ folder.

Use this after you've manually handled all outstanding updates/reschedules
so the bot doesn't attempt to re-process them.

Usage:
    python flush_webhooks.py              # Flush everything
    python flush_webhooks.py --dry-run    # Preview what would be flushed
"""
import os
import sys
import glob
import shutil
from datetime import datetime

# Fix Windows console encoding for emoji output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SNIFFER_DIR = os.path.join(ROOT_DIR, "webhook_sniffer")
RETRY_DIR = os.path.join(SNIFFER_DIR, "pending_retry")
PROCESSED_DIR = os.path.join(SNIFFER_DIR, "processed")


def flush_webhooks(dry_run=False):
    """Move all pending webhook JSON files to processed/."""
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

    moved = 0
    
    # 1. Flush main sniffer queue
    for fpath in sorted(glob.glob(os.path.join(SNIFFER_DIR, "*.json"))):
        fname = os.path.basename(fpath)
        if dry_run:
            print(f"  [DRY RUN] Would flush: {fname}")
        else:
            dest = os.path.join(PROCESSED_DIR, fname)
            shutil.move(fpath, dest)
            print(f"  ✅ Flushed: {fname}")
        moved += 1

    # 2. Flush pending_retry queue
    if os.path.exists(RETRY_DIR):
        for fpath in sorted(glob.glob(os.path.join(RETRY_DIR, "*.json"))):
            fname = os.path.basename(fpath)
            if dry_run:
                print(f"  [DRY RUN] Would flush (retry): {fname}")
            else:
                dest = os.path.join(PROCESSED_DIR, fname)
                shutil.move(fpath, dest)
                print(f"  ✅ Flushed (retry): {fname}")
            moved += 1

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if moved == 0:
        print(f"\n[{timestamp}] No pending webhooks to flush.")
    elif dry_run:
        print(f"\n[{timestamp}] DRY RUN: {moved} file(s) would be flushed.")
    else:
        print(f"\n[{timestamp}] ✅ Flushed {moved} webhook file(s) to processed/.")
    
    return moved


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN MODE ===\n")
    else:
        print("=== FLUSHING ALL PENDING WEBHOOKS ===\n")
    
    flush_webhooks(dry_run=dry_run)
