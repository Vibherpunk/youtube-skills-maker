import unittest
from unittest.mock import MagicMock, patch
from src.evaluator import evaluate_transcript


class TestSystemOneEvaluator(unittest.TestCase):
    def test_empty_transcript(self):
        """Empty transcript should return None immediately."""
        result = evaluate_transcript("test_vid", "Empty Title", "", "mock_key")
        self.assertIsNone(result)

    @patch("src.evaluator.get_system_one")
    def test_system_one_discards_non_technical_text(self, mock_get_sys1):
        """Non-technical content with 0 entities should be discarded by System One without LLM calls."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = []
        mock_jev = MagicMock()
        mock_get_sys1.return_value = (mock_extractor, mock_jev)

        non_technical_transcript = (
            "Hello everyone, welcome back to my daily vlog! Today we had breakfast, "
            "walked around the park, talked to neighbors, and discussed our favorite vacation spots. "
            "Tomorrow we are going to visit the beach and relax in the sun."
        )
        result = evaluate_transcript(
            video_id="vlog_123",
            title="My Daily Vacation Vlog",
            transcript_text=non_technical_transcript,
            api_key=""
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["is_teachable_skill"])
        self.assertEqual(result["skill_potential"], 1)
        self.assertIn("System One", result["reasoning"])

    @patch("src.evaluator.get_system_one")
    def test_system_one_high_confidence_actionable(self, mock_get_sys1):
        """When Jev returns high confidence actionable (P >= 0.80), should return teachable skill."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"label": "software_tool", "text": "Cursor", "confidence": 0.95},
            {"label": "software_tool", "text": "Docker", "confidence": 0.92},
            {"label": "architecture_pattern", "text": "Multi-agent", "confidence": 0.89},
        ]
        mock_jev = MagicMock()
        mock_jev.decide.return_value = {
            "answers": {
                "is_actionable_skill": {"choice": "actionable", "confidence": 0.92},
                "target_domain": {"choice": "ai_coding"}
            }
        }
        mock_get_sys1.return_value = (mock_extractor, mock_jev)

        result = evaluate_transcript(
            video_id="tech_123",
            title="Building Multi-Agent Systems in Cursor",
            transcript_text="In this tutorial we configure Cursor and Docker to build multi-agent workflows...",
            api_key=""
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["is_teachable_skill"])
        self.assertGreaterEqual(result["skill_potential"], 4)
        self.assertEqual(result["category"], "ai-coding")
        self.assertIn("System One", result["reasoning"])

    @patch("src.evaluator.get_system_one")
    def test_system_one_high_confidence_not_actionable(self, mock_get_sys1):
        """When Jev returns high confidence not actionable (P >= 0.80), should discard."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"label": "software_tool", "text": "iPhone", "confidence": 0.9},
            {"label": "software_tool", "text": "MacBook", "confidence": 0.85},
        ]
        mock_jev = MagicMock()
        mock_jev.decide.return_value = {
            "answers": {
                "is_actionable_skill": {"choice": "not_actionable", "confidence": 0.88},
                "target_domain": {"choice": "general_other"}
            }
        }
        mock_get_sys1.return_value = (mock_extractor, mock_jev)

        result = evaluate_transcript(
            video_id="review_123",
            title="Why I Switched from iPhone to Android",
            transcript_text="Here are my general thoughts on consumer tech and battery life...",
            api_key=""
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["is_teachable_skill"])
        self.assertEqual(result["skill_potential"], 1)

    @patch("src.evaluator._call_compatible_api")
    @patch("src.evaluator.get_system_one")
    def test_system_one_ambiguous_falls_back_to_llm(self, mock_get_sys1, mock_call_api):
        """When Jev confidence is ambiguous (P < 0.80), should fall back to LLM evaluation."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"label": "software_tool", "text": "Python", "confidence": 0.85},
            {"label": "software_tool", "text": "Flask", "confidence": 0.80},
        ]
        mock_jev = MagicMock()
        # Ambiguous confidence 0.65 < 0.80
        mock_jev.decide.return_value = {
            "answers": {
                "is_actionable_skill": {"choice": "actionable", "confidence": 0.65},
                "target_domain": {"choice": "ai_coding"}
            }
        }
        mock_get_sys1.return_value = (mock_extractor, mock_jev)

        mock_call_api.return_value = {
            "is_teachable_skill": True,
            "technique_description": "Building Flask APIs",
            "skill_potential": 4,
            "category": "ai-coding",
            "reasoning": "LLM evaluated as teachable",
            "keywords": ["python", "flask"]
        }

        with patch.dict("os.environ", {"LLM_API_KEY": "mock_test_key"}):
            result = evaluate_transcript(
                video_id="flask_123",
                title="Flask Quickstart",
                transcript_text="Python and Flask code walkthrough...",
                api_key=""
            )
            self.assertIsNotNone(result)
            self.assertEqual(result["reasoning"], "LLM evaluated as teachable")
            mock_call_api.assert_called()


if __name__ == "__main__":
    unittest.main()
