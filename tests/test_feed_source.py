#!/usr/bin/env python3
"""
Unit Test Suite for YouTube Feed Ingestion (src/feed_source.py)
Tests:
1. Topic inference from titles and channels (infer_topics)
2. Child content regex filtering
3. Filtering of music mixes (RD..., Mix - ...)
4. Filtering of YouTube Shorts (duration < 180s)
5. Prioritization of AI/tech candidates
6. Deduplication across multiple feeds
"""

import unittest
from unittest.mock import patch
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.feed_source import (
    infer_topics,
    CHILD_CONTENT_REGEX,
    fetch_user_feed_videos
)


class TestFeedSource(unittest.TestCase):

    def test_infer_topics(self):
        # AI Coding & Cursor
        topics = infer_topics("How I use Cursor and Claude Code for Vibe Coding", "AI Dev")
        self.assertIn("ai-coding", topics)
        self.assertIn("ai-tech", topics)

        # RAG & Embeddings
        topics = infer_topics("Building Advanced RAG with Vector Database", "Tech Channel")
        self.assertIn("rag", topics)

        # Agents & LangGraph
        topics = infer_topics("Autonomous Agent Loops with LangGraph and CrewAI", "Agent World")
        self.assertIn("agents", topics)

        # Non-AI generic video
        topics = infer_topics("How to bake sourdough bread", "Baking Channel")
        self.assertEqual(topics, [])

    def test_child_content_regex(self):
        self.assertTrue(bool(CHILD_CONTENT_REGEX.search("Cocomelon Nursery Rhymes for Toddlers")))
        self.assertTrue(bool(CHILD_CONTENT_REGEX.search("Peppa Pig Full Episodes for Kids")))
        self.assertTrue(bool(CHILD_CONTENT_REGEX.search("Learn colors and shapes with toys review")))
        self.assertFalse(bool(CHILD_CONTENT_REGEX.search("Autonomous AI Agent Architecture and Tool Calling")))

    @patch("src.feed_source._fetch_raw_feed")
    def test_fetch_user_feed_videos_filtering(self, mock_fetch):
        # Mocked raw entries
        mock_fetch.return_value = [
            # 1. Valid AI video
            {"id": "vid_ai_1", "title": "Building AI Agents with Python", "duration": 600, "uploader": "TechCorp"},
            # 2. Music mix (should be filtered out)
            {"id": "RD12345", "title": "My Mix - Synthwave", "duration": 1800, "uploader": "Various"},
            # 3. Title mix (should be filtered out)
            {"id": "vid_mix", "title": "Mix - Relaxing Beats", "duration": 2400, "uploader": "DJ Beats"},
            # 4. Short video < 180s (should be filtered out)
            {"id": "vid_short", "title": "Quick Python Trick", "duration": 45, "uploader": "Shorts"},
            # 5. Child content (should be filtered out)
            {"id": "vid_kids", "title": "Nursery Rhymes for Toddlers and Babies", "duration": 900, "uploader": "BabyTV"},
            # 6. Valid non-AI tech video
            {"id": "vid_general", "title": "How Operating Systems Handle Virtual Memory", "duration": 1200, "uploader": "ComputerScience"},
        ]

        results = fetch_user_feed_videos(
            browser="chrome:Default",
            feeds=["https://www.youtube.com/"],
            limit_per_feed=10,
            min_duration_seconds=180,
            prioritize_ai_tech=True,
            exclude_child_content=True
        )

        result_ids = [v["videoId"] for v in results]
        # Should retain vid_ai_1 and vid_general
        self.assertIn("vid_ai_1", result_ids)
        self.assertIn("vid_general", result_ids)
        # Should filter out mixes, shorts, and kids content
        self.assertNotIn("RD12345", result_ids)
        self.assertNotIn("vid_mix", result_ids)
        self.assertNotIn("vid_short", result_ids)
        self.assertNotIn("vid_kids", result_ids)

        # AI video should be prioritized first
        self.assertEqual(results[0]["videoId"], "vid_ai_1")

    @patch("src.feed_source._fetch_raw_feed")
    def test_fetch_user_feed_deduplication(self, mock_fetch):
        # Feed 1 returns video A and B; Feed 2 returns video B and C
        mock_fetch.side_effect = [
            [
                {"id": "vid_A", "title": "AI Model Training", "duration": 400},
                {"id": "vid_B", "title": "Deploying Kubernetes", "duration": 500}
            ],
            [
                {"id": "vid_B", "title": "Deploying Kubernetes", "duration": 500},
                {"id": "vid_C", "title": "Vector Embeddings", "duration": 600}
            ]
        ]

        results = fetch_user_feed_videos(
            feeds=["https://www.youtube.com/", "https://www.youtube.com/feed/subscriptions"],
            limit_per_feed=10
        )
        result_ids = [v["videoId"] for v in results]
        self.assertEqual(len(result_ids), 3)
        self.assertEqual(set(result_ids), {"vid_A", "vid_B", "vid_C"})


if __name__ == "__main__":
    unittest.main()
