"""Tests for the HackerTube (Hacker News) discovery source."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hackertube_source import (  # noqa: E402
    extract_video_id,
    fetch_hackertube_videos,
    robots_permits,
    search_hn_youtube,
    skill_score,
)


class TestExtractVideoId:
    def test_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&t=30s"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_non_youtube(self):
        assert extract_video_id("https://example.com/video") is None

    def test_empty(self):
        assert extract_video_id("") is None


class TestSkillScore:
    def test_procedural_long_ai_video_scores_high(self):
        s = skill_score("Let's build GPT: from scratch, in code", 1110, 783, 7000, True)
        assert s > 10

    def test_news_headline_scores_low(self):
        s = skill_score("Facebook Fraud", 1678, 400, 539, False)
        assert s < 8

    def test_vlog_is_penalised(self):
        vlog = skill_score("Building a log cabin vlog day in the life", 300, 50, 3000, False)
        tutorial = skill_score("How to build a compiler from scratch", 300, 50, 3000, False)
        assert tutorial > vlog

    def test_lifetime_movie_trailer_low(self):
        assert skill_score("Official trailer", 2000, 100, 3000, False) < 8

    def test_short_clip_penalised(self):
        short = skill_score("How to configure nginx", 100, 10, 120, False)
        long = skill_score("How to configure nginx", 100, 10, 1800, False)
        assert long > short


class TestSearchHnYoutube:
    @patch("src.hackertube_source._http_json")
    def test_parses_hits_and_dedupes(self, mock_http):
        mock_http.return_value = {
            "hits": [
                {"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                 "title": "A [video]", "objectID": "1", "points": 100,
                 "num_comments": 5, "created_at": "2025-01-01", "author": "x"},
                {"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                 "title": "A dup", "objectID": "2", "points": 90,
                 "num_comments": 1, "created_at": "2025-01-02", "author": "y"},
                {"url": "https://example.com/notvideo",
                 "title": "nope", "objectID": "3", "points": 80,
                 "num_comments": 0, "created_at": "2025-01-03", "author": "z"},
            ],
            "nbPages": 1,
        }
        out = search_hn_youtube(min_points=10, max_pages=1)
        assert len(out) == 1
        assert out[0]["videoId"] == "aaaaaaaaaaa"
        assert out[0]["title"] == "A"  # [video] suffix stripped
        assert out[0]["hn_points"] == 100


class TestRobots:
    def test_returns_bool(self):
        assert isinstance(robots_permits(), bool)


class TestFetchHackertubeVideos:
    @patch("src.hackertube_source._yt_dlp_metadata")
    @patch("src.hackertube_source.search_hn_youtube")
    def test_filters_and_scores(self, mock_search, mock_meta):
        mock_search.return_value = [
            {"videoId": "aaaaaaaaaaa", "title": "Let's build GPT from scratch",
             "hn_id": "1", "hn_points": 500, "hn_comments": 50,
             "publishedAt": "2025-01-01", "hn_author": "a",
             "link": "https://www.youtube.com/watch?v=aaaaaaaaaaa"},
            {"videoId": "bbbbbbbbbbb", "title": "Official trailer for a movie",
             "hn_id": "2", "hn_points": 500, "hn_comments": 50,
             "publishedAt": "2025-01-01", "hn_author": "b",
             "link": "https://www.youtube.com/watch?v=bbbbbbbbbbb"},
            {"videoId": "ccccccccccc", "title": "How to configure nginx",
             "hn_id": "3", "hn_points": 50, "hn_comments": 5,
             "publishedAt": "2025-01-01", "hn_author": "c",
             "link": "https://www.youtube.com/watch?v=ccccccccccc"},
        ]
        mock_meta.return_value = {
            "aaaaaaaaaaa": {"duration": 7000, "channelName": "Karpathy", "uploaded": ""},
            "bbbbbbbbbbb": {"duration": 3000, "channelName": "Studio", "uploaded": ""},
            "ccccccccccc": {"duration": 400, "channelName": "Dev", "uploaded": ""},
        }

        out = fetch_hackertube_videos(limit=10, min_skill_score=4.0)

        ids = [v["videoId"] for v in out]
        assert "bbbbbbbbbbb" not in ids, "trailer must be filtered"
        assert ids[0] == "aaaaaaaaaaa", "procedural AI video should rank first"
        assert all(v["duration"] >= 180 for v in out)
        assert "skill_score" in out[0]

    @patch("src.hackertube_source._yt_dlp_metadata")
    @patch("src.hackertube_source.search_hn_youtube")
    def test_drops_unknown_duration(self, mock_search, mock_meta):
        mock_search.return_value = [
            {"videoId": "aaaaaaaaaaa",
             "title": "How to configure nginx",
             "hn_id": "1", "hn_points": 50, "hn_comments": 5,
             "publishedAt": "2025-01-01", "hn_author": "a",
             "link": "https://www.youtube.com/watch?v=aaaaaaaaaaa"},
        ]
        mock_meta.return_value = {}  # metadata lookup failed entirely

        out = fetch_hackertube_videos(limit=10)
        assert out == [], "unknown duration must be dropped, not guessed"