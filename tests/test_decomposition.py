import unittest
from unittest.mock import patch, MagicMock
from src.synthesize import (
    should_decompose,
    _normalize_and_fix_skills,
    _fix_reference_links,
    synthesize_skill,
)


class TestSkillDecomposition(unittest.TestCase):

    @patch("src.system_one.classify_content_taxonomy")
    def test_should_decompose_duration_trigger(self, mock_classify):
        """Comprehensive masterclasses >= 1200 seconds (20 minutes) should trigger decomposition."""
        def fake_classify(title, text, duration=0, topics=None, **kwargs):
            dur = duration or 0
            has_topics = bool(topics and len(topics) >= 3)
            is_modular = (dur >= 1200 and (has_topics or len(text) > 20000)) or (has_topics and dur >= 600)
            return {
                "taxonomy": "MODULAR_SKILL_SUITE" if is_modular else "SINGLE_ATOMIC_SKILL",
                "should_decompose": is_modular
            }
        mock_classify.side_effect = fake_classify

        short_video = [{"videoId": "v1", "title": "Short intro", "duration": 600}]
        self.assertFalse(should_decompose(short_video))

        long_video = [{"videoId": "v2", "title": "Comprehensive masterclass", "duration": 1500, "topics": ["architecture", "agent-loops", "eval"]}]
        self.assertTrue(should_decompose(long_video))

    @patch("src.system_one.classify_content_taxonomy")
    def test_should_decompose_multi_topic_trigger(self, mock_classify):
        """Content spanning >= 3 distinct topics with substantial duration (>=600s) should trigger decomposition."""
        def fake_classify(title, text, duration=0, topics=None, **kwargs):
            dur = duration or 0
            has_topics = bool(topics and len(topics) >= 3)
            is_modular = (dur >= 1200 and (has_topics or len(text) > 20000)) or (has_topics and dur >= 600)
            return {
                "taxonomy": "MODULAR_SKILL_SUITE" if is_modular else "SINGLE_ATOMIC_SKILL",
                "should_decompose": is_modular
            }
        mock_classify.side_effect = fake_classify

        multi_topic_video = [
            {"videoId": "v3", "title": "Full Stack AI", "duration": 800, "topics": ["agents", "rag", "ai-coding"]}
        ]
        self.assertTrue(should_decompose(multi_topic_video))

    @patch("src.system_one.classify_content_taxonomy")
    def test_should_decompose_false_for_focused_short_video(self, mock_classify):
        """A short, focused single-topic video should NOT trigger decomposition."""
        def fake_classify(title, text, duration=0, topics=None, **kwargs):
            is_modular = (duration or 0) >= 1200 or (topics and len(topics) >= 3 and (duration or 0) >= 600)
            return {
                "taxonomy": "MODULAR_SKILL_SUITE" if is_modular else "SINGLE_ATOMIC_SKILL",
                "should_decompose": is_modular
            }
        mock_classify.side_effect = fake_classify

        focused_video = [
            {"videoId": "v4", "title": "Quick Prompt Tip", "duration": 300, "topics": ["prompt-engineering"]}
        ]
        self.assertFalse(should_decompose(focused_video))

    def test_normalize_and_fix_skills_from_decomposed_list(self):
        """Model returning a decomposed list with 'skills' should be properly normalized."""
        raw_response = {
            "skills": [
                {
                    "name": "agent-orchestration-patterns",
                    "description": "Orchestrating agents with LangGraph",
                    "keywords": ["langgraph", "orchestration"],
                    "difficulty": "advanced",
                    "prerequisites": ["python"],
                    "skill_body": "See [Core Guide](references/core_concepts.md) for details.",
                    "references": [
                        {"filename": "core_concepts.md", "content": "Comprehensive guide on agent graph state management."}
                    ]
                },
                {
                    "name": "agent-tool-calling-guardrails",
                    "description": "Enforcing schema contracts on tool calls",
                    "keywords": ["tool-calling", "guardrails"],
                    "difficulty": "intermediate",
                    "prerequisites": ["json-schema"],
                    "skill_body": "Refer to [Tool Reference](references/tool_reference.md).",
                    "references": [
                        {"filename": "tool_reference.md", "content": "Detailed specification of Pydantic tool models."}
                    ]
                }
            ]
        }

        skills = _normalize_and_fix_skills(raw_response, "fallback-topic")
        self.assertEqual(len(skills), 2)
        self.assertEqual(skills[0]["name"], "agent-orchestration-patterns")
        self.assertEqual(skills[1]["name"], "agent-tool-calling-guardrails")
        self.assertIn("references/core_concepts.md", skills[0]["skill_body"])
        self.assertIn("references/tool_reference.md", skills[1]["skill_body"])

    def test_normalize_and_fix_skills_from_single_skill(self):
        """Model returning a single skill object should be normalized to a 1-item list."""
        raw_response = {
            "name": "cursor-fast-mode",
            "description": "Enabling fast cursor rules",
            "keywords": ["cursor"],
            "difficulty": "beginner",
            "prerequisites": [],
            "skill_body": "Follow [Setup Guide](references/setup.md).",
            "references": [
                {"filename": "setup.md", "content": "How to set up cursor rules."}
            ]
        }

        skills = _normalize_and_fix_skills(raw_response, "cursor-tips")
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["name"], "cursor-fast-mode")

    def test_fix_reference_links(self):
        """Fixes placeholder or malformed reference links to match filenames in references."""
        skill_dict = {
            "name": "rag-pipeline",
            "skill_body": "Review the concepts in [Concepts](core_concepts.md) and [Patterns](patterns.md).",
            "references": [
                {"filename": "core_concepts.md", "content": "Detailed concepts."},
                {"filename": "patterns.md", "content": "Detailed patterns."}
            ]
        }
        fixed = _fix_reference_links(skill_dict)
        self.assertIn("[Concepts](references/core_concepts.md)", fixed["skill_body"])
        self.assertIn("[Patterns](references/patterns.md)", fixed["skill_body"])


if __name__ == "__main__":
    unittest.main()
