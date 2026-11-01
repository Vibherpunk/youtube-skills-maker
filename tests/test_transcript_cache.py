"""Tests for transcript cache pruning."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.transcribe import prune_transcript_cache  # noqa: E402


def _mk(cache_dir: Path, name: str, size: int = 100, age: float = 0.0) -> Path:
    p = cache_dir / name
    p.write_text(json.dumps({"video_id": name, "text": "x" * size}))
    if age:
        old = time.time() - age
        os.utime(p, (old, old))
    return p


class TestPruneTranscriptCache:
    def test_missing_dir_is_noop(self, tmp_path):
        assert prune_transcript_cache(data_dir=str(tmp_path)) == 0

    def test_deletes_all_by_default(self, tmp_path):
        cache = tmp_path / "transcripts"
        cache.mkdir()
        _mk(cache, "a.json")
        _mk(cache, "b.json")
        assert prune_transcript_cache(data_dir=str(tmp_path)) == 2
        assert list(cache.glob("*.json")) == []

    def test_keep_last_retains_newest(self, tmp_path):
        cache = tmp_path / "transcripts"
        cache.mkdir()
        _mk(cache, "old.json", age=3600)
        _mk(cache, "mid.json", age=1800)
        _mk(cache, "new.json", age=0)
        deleted = prune_transcript_cache(data_dir=str(tmp_path), keep_last=1)
        assert deleted == 2
        assert [p.name for p in cache.glob("*.json")] == ["new.json"]

    def test_max_bytes_caps_size(self, tmp_path):
        cache = tmp_path / "transcripts"
        cache.mkdir()
        for i in range(5):
            _mk(cache, f"f{i}.json", size=1000, age=(5 - i) * 100)
        prune_transcript_cache(data_dir=str(tmp_path), max_bytes=2500)
        remaining = list(cache.glob("*.json"))
        assert len(remaining) < 5
        assert sum(p.stat().st_size for p in remaining) <= 2500

    def test_ignores_non_json(self, tmp_path):
        cache = tmp_path / "transcripts"
        cache.mkdir()
        _mk(cache, "a.json")
        keep = cache / "notes.txt"
        keep.write_text("keep me")
        prune_transcript_cache(data_dir=str(tmp_path))
        assert keep.exists()
        assert not (cache / "a.json").exists()
