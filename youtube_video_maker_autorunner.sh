#!/bin/bash
# ==============================================================================
# YouTube Skills Maker / Video Maker Autorunner
# Continuous automated ingestion and skill synthesis from your personal feed.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Activate virtual environment if present
if [ -d "$DIR/.venv" ]; then
    source "$DIR/.venv/bin/activate"
fi

echo "[Autorunner] Starting YouTube Skills Maker Continuous Loop..."
echo "[Autorunner] Working Directory: $DIR"
echo "[Autorunner] Feed: Personal YouTube Recommendations (Child content filtered)"

exec python3 loop.py "$@"
