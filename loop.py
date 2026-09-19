#!/usr/bin/env python3
"""
loop.py — Continuous YouTube Skills Maker pipeline runner.

Runs the pipeline in a loop, processing batches of videos until all are done.
Automatically backs off and retries when YouTube is IP-blocking this machine.

Usage:
    python loop.py                     # Runs forever, 50 videos per batch
    python loop.py --batch-size 30     # Custom batch size
    python loop.py --max-batches 10    # Run at most 10 batches then stop
    python loop.py --no-push           # Skip GitHub push (for testing)
"""

import argparse
import subprocess
import sys
import time
import random
from dotenv import load_dotenv

load_dotenv()


# --- Config ---
PROBE_WAIT_MINUTES_INITIAL = 30    # First backoff after IP block
PROBE_WAIT_MINUTES_MAX = 120       # Cap backoff at 2 hours
PROBE_WAIT_MULTIPLIER = 1.5        # Exponential backoff multiplier
INTER_BATCH_DELAY_SECONDS = 60     # Cooldown between successful batches


def log(msg):
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[Loop {ts}] {msg}", flush=True)


def check_youtube_access() -> bool:
    """Probe YouTube by running a quick transcript check on a known-good video."""
    log("Probing YouTube access...")
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from src.transcribe import is_ip_blocked; "
             "import sys; sys.exit(0 if not is_ip_blocked() else 1)"],
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            log("✅ YouTube is accessible.")
            return True
        else:
            log("❌ YouTube is blocked (429 / IP ban).")
            return False
    except subprocess.TimeoutExpired:
        log("⚠️  Probe timed out — assuming blocked.")
        return False
    except Exception as e:
        log(f"⚠️  Probe error: {e} — assuming blocked.")
        return False


def count_remaining() -> int:
    """Return number of videos in the personal YouTube feed not yet processed."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", """
import json, os, yaml
from dotenv import load_dotenv
load_dotenv()
from src.feed_source import fetch_user_feed_videos
from src.state import State
with open('config.yaml') as f:
    config = yaml.safe_load(f)
feed_cfg = config.get('youtube_feed', {})
all_videos = fetch_user_feed_videos(
    browser=feed_cfg.get('browser', 'chrome:Default'),
    feeds=feed_cfg.get('feeds', ['https://www.youtube.com/']),
    limit_per_feed=feed_cfg.get('limit_per_feed', 25),
    min_duration_seconds=feed_cfg.get('min_duration_seconds', 180),
    cookies_fallback=feed_cfg.get('cookies_fallback', 'cookies.txt'),
    prioritize_ai_tech=feed_cfg.get('prioritize_ai_tech', True),
    exclude_child_content=feed_cfg.get('exclude_child_content', True)
)
state = State('data/state.json')
remaining = [v for v in all_videos if not state.is_video_processed(v['videoId'])]
print(len(remaining))
"""],
            capture_output=True, text=True, timeout=90
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            return int(lines[-1].strip())
        return -1
    except Exception as e:
        return -1  # Unknown


def run_batch(batch_size: int, no_push: bool) -> bool:
    """
    Run one pipeline batch. Returns True if successful, False if stopped early
    (e.g. due to IP block).
    """
    cmd = [sys.executable, "run.py", "--limit", str(batch_size)]
    if no_push:
        cmd.append("--no-push")

    log(f"Starting batch (--limit {batch_size})...")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        log(f"⚠️  Batch exited with code {result.returncode}.")
        return False
    return True


def wait_with_probe(wait_minutes: float) -> None:
    """Wait, checking for access every 10 minutes."""
    log(f"Waiting {wait_minutes:.0f} minutes before re-checking YouTube access...")
    check_interval = min(10, wait_minutes)
    elapsed = 0.0
    while elapsed < wait_minutes:
        time.sleep(check_interval * 60)
        elapsed += check_interval
        if elapsed < wait_minutes:
            log(f"  [{elapsed:.0f}/{wait_minutes:.0f} min] Still waiting...")
            if check_youtube_access():
                log("Access restored early! Resuming.")
                return
    log("Done waiting.")


def main():
    parser = argparse.ArgumentParser(description="Continuous YouTube Skills pipeline loop")
    parser.add_argument("--batch-size", type=int, default=50, help="Videos per batch (default: 50)")
    parser.add_argument("--max-batches", type=int, default=0, help="Max batches to run (0 = unlimited)")
    parser.add_argument("--no-push", action="store_true", help="Skip GitHub push")
    args = parser.parse_args()

    log("=" * 60)
    log("YouTube Skills Maker — Continuous Loop")
    log(f"  Batch size:   {args.batch_size} videos")
    log(f"  Max batches:  {'unlimited' if args.max_batches == 0 else args.max_batches}")
    log(f"  GitHub push:  {'disabled' if args.no_push else 'enabled'}")
    log("=" * 60)

    batch_num = 0
    backoff_minutes = PROBE_WAIT_MINUTES_INITIAL

    while True:
        # Check batch limit
        if args.max_batches > 0 and batch_num >= args.max_batches:
            log(f"Reached max batches ({args.max_batches}). Done.")
            break

        # Check remaining work
        remaining = count_remaining()
        if remaining == 0:
            log("🎉 All videos have been processed! Nothing left to do.")
            break
        elif remaining > 0:
            log(f"📊 ~{remaining} videos remaining to process.")

        # Probe YouTube before committing to a batch
        if not check_youtube_access():
            log(f"YouTube is blocked. Backing off for {backoff_minutes:.0f} minutes.")
            wait_with_probe(backoff_minutes)
            backoff_minutes = min(backoff_minutes * PROBE_WAIT_MULTIPLIER, PROBE_WAIT_MINUTES_MAX)
            # Add jitter to avoid synchronized retries
            backoff_minutes += random.uniform(-5, 5)
            continue

        # YouTube is accessible — reset backoff and run batch
        backoff_minutes = PROBE_WAIT_MINUTES_INITIAL
        batch_num += 1
        log(f"--- Batch #{batch_num} ---")
        run_batch(args.batch_size, args.no_push)

        # Brief cooldown between batches
        log(f"Batch #{batch_num} complete. Cooling down {INTER_BATCH_DELAY_SECONDS}s before next batch...")
        time.sleep(INTER_BATCH_DELAY_SECONDS)


if __name__ == "__main__":
    main()
