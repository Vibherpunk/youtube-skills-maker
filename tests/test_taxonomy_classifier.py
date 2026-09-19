#!/usr/bin/env python3
"""
Unit Test Suite for System One Taxonomy Classifier & Hybrid Workflows
Tests:
1. Hermetic Jev-online path (mocked non-autoregressive decisions)
2. Hermetic Deterministic Fallback path (mocked API failure / 402):
   - Case A: 2-hour multi-topic video mentioning postgres resolves to MODULAR_SKILL_SUITE
   - Multi-stage lifecycle masterclass resolves to MODULAR_SKILL_SUITE
   - Over-decomposition protection: short 5m video with 3 topics resolves to SINGLE_ATOMIC_SKILL
   - Deterministic rail + agentic evaluation resolves to HYBRID_WORKFLOW_AND_SKILL
   - Focused prompt review resolves to SINGLE_ATOMIC_SKILL
3. Companion n8n workflow DAG generation (real HMAC verification + dynamic SYSTEM_ONE_URL)
4. Packaging of hybrid skills with workflow.json strictly in workflows/ (defensive no-duplication in references/)
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.system_one import classify_content_taxonomy
from src.synthesize import generate_companion_workflow
from src.skill_builder import build_universal_skill


class StubExtractor:
    """Fast, hermetic entity extractor stub for unit testing without loading PyTorch/GLiNER."""
    def __init__(self, entities=None):
        self.entities = entities or []

    def extract(self, text, labels, threshold=0.30):
        return self.entities


class TestTaxonomyClassifier(unittest.TestCase):

    def setUp(self):
        # Default mock Jev that simulates an API error (forcing deterministic fallback)
        self.fallback_jev = MagicMock()
        self.fallback_jev.decide.return_value = {"error": "HTTP 402: Insufficient credits"}

    # ── Jev Online Path (Mocked Active Model) ─────────────────────────────────

    def test_mocked_jev_online_decisions(self):
        """Verify that when Jev returns valid non-autoregressive choices, they are honored directly."""
        mock_jev = MagicMock()
        stub_extractor = StubExtractor()

        # Jev chooses HYBRID
        mock_jev.decide.return_value = {
            "answers": {
                "artifact_taxonomy": {
                    "choice": "HYBRID_WORKFLOW_AND_SKILL",
                    "confidence": 0.96
                }
            }
        }
        res = classify_content_taxonomy("Arbitrary Title", "Arbitrary text", extractor=stub_extractor, jev=mock_jev)
        self.assertEqual(res["taxonomy"], "HYBRID_WORKFLOW_AND_SKILL")
        self.assertEqual(res["confidence"], 0.96)
        self.assertTrue(res["is_hybrid"])
        self.assertFalse(res["should_decompose"])

        # Jev chooses MODULAR
        mock_jev.decide.return_value = {
            "answers": {
                "artifact_taxonomy": {
                    "choice": "MODULAR_SKILL_SUITE",
                    "confidence": 0.92
                }
            }
        }
        res = classify_content_taxonomy("Arbitrary Title", "Arbitrary text", extractor=stub_extractor, jev=mock_jev)
        self.assertEqual(res["taxonomy"], "MODULAR_SKILL_SUITE")
        self.assertEqual(res["confidence"], 0.92)
        self.assertTrue(res["should_decompose"])
        self.assertFalse(res["is_hybrid"])

        # Jev chooses SINGLE
        mock_jev.decide.return_value = {
            "answers": {
                "artifact_taxonomy": {
                    "choice": "SINGLE_ATOMIC_SKILL",
                    "confidence": 0.94
                }
            }
        }
        res = classify_content_taxonomy("Arbitrary Title", "Arbitrary text", extractor=stub_extractor, jev=mock_jev)
        self.assertEqual(res["taxonomy"], "SINGLE_ATOMIC_SKILL")
        self.assertEqual(res["confidence"], 0.94)
        self.assertFalse(res["is_hybrid"])
        self.assertFalse(res["should_decompose"])

    # ── Deterministic Fallback Path (Hermetically Tested) ─────────────────────

    def test_fallback_precedence_case_a_modular_suite_with_postgres(self):
        """Case A edge case: 2-hour multi-topic video mentioning postgres must classify as MODULAR_SKILL_SUITE, not HYBRID."""
        title = "Building Multi-Agent Operating Systems: Full 2-Hour Course"
        text = (
            "Welcome to this complete masterclass. In chapter 1 we discuss system architecture. "
            "In chapter 2 we implement agent loops and prompt evaluation. "
            "We also mention that data can be saved to postgres or sqlite. "
            "In chapter 3 we explore tool orchestration, and in chapter 4 we deploy production verifiers. "
            + "This multi-stage lifecycle requires modular decomposition across all subsystems. " * 40
        )
        topics = ["architecture", "agent-loops", "memory", "tool-orchestration"]
        stub_extractor = StubExtractor([
            {"label": "multi_stage_process", "text": "multi-stage lifecycle", "confidence": 0.88, "start": 0, "end": 20}
        ])

        result = classify_content_taxonomy(
            title, text, duration=7200, topics=topics,
            extractor=stub_extractor, jev=self.fallback_jev
        )
        self.assertEqual(result["taxonomy"], "MODULAR_SKILL_SUITE")
        self.assertTrue(result["should_decompose"])
        self.assertFalse(result["is_hybrid"])

    def test_fallback_modular_skill_suite_classification(self):
        """Long multi-stage deep-dive must classify as MODULAR_SKILL_SUITE in fallback."""
        title = "Complete 2-Hour Autonomous Agent Engineering Masterclass"
        text = (
            "In this comprehensive multi-stage masterclass, we cover phase 1 agent memory, "
            "phase 2 dynamic tool selection, phase 3 subagent routing, and phase 4 production verification. "
            + "Each stage requires distinct architectural guidelines and prompts. " * 50
        )
        stub_extractor = StubExtractor([
            {"label": "multi_stage_process", "text": "phase 1 agent memory", "confidence": 0.85, "start": 0, "end": 20}
        ])

        result = classify_content_taxonomy(
            title, text, duration=1500,
            extractor=stub_extractor, jev=self.fallback_jev
        )
        self.assertEqual(result["taxonomy"], "MODULAR_SKILL_SUITE")
        self.assertTrue(result["should_decompose"])
        self.assertFalse(result["is_hybrid"])

    def test_fallback_over_decomposition_prevention(self):
        """A short 5-minute video with 3 brief topics but no duration/length signals must NOT over-decompose."""
        title = "Quick Tips on Three Coding Patterns"
        text = "Here are quick 1-minute tips on pattern A, pattern B, and pattern C. Keep it concise."
        topics = ["pattern-a", "pattern-b", "pattern-c"]
        stub_extractor = StubExtractor([])

        result = classify_content_taxonomy(
            title, text, duration=300, topics=topics,
            extractor=stub_extractor, jev=self.fallback_jev
        )
        self.assertEqual(result["taxonomy"], "SINGLE_ATOMIC_SKILL")
        self.assertFalse(result["should_decompose"])

    def test_fallback_hybrid_workflow_and_skill_classification(self):
        """Content with strict deterministic rails (webhook, hmac) + agentic judgment must classify as HYBRID."""
        title = "Building a Stripe Webhook and Auto-Refund AI Agent"
        text = (
            "Set up a webhook endpoint at /api/stripe-events to listen for charge.failed. "
            "Deterministically verify the HMAC signature and insert the event into the postgres database. "
            "Then, call the AI agent with the customer history and evaluation rubrics to decide "
            "whether to grant an instant courtesy refund or escalate to fraud review."
        )
        stub_extractor = StubExtractor([
            {"label": "webhook_endpoint", "text": "webhook endpoint", "confidence": 0.95, "start": 0, "end": 16},
            {"label": "hmac_signature", "text": "HMAC signature", "confidence": 0.92, "start": 20, "end": 34},
            {"label": "judgment_criteria", "text": "evaluation rubrics", "confidence": 0.90, "start": 40, "end": 58}
        ])

        result = classify_content_taxonomy(
            title, text, duration=600,
            extractor=stub_extractor, jev=self.fallback_jev
        )
        self.assertEqual(result["taxonomy"], "HYBRID_WORKFLOW_AND_SKILL")
        self.assertTrue(result["is_hybrid"])
        self.assertFalse(result["should_decompose"])

    def test_fallback_single_atomic_skill_classification(self):
        """Focused single-turn prompts with no infrastructure rails must classify as SINGLE_ATOMIC_SKILL."""
        title = "Clean Code Review Prompts"
        text = (
            "Here is how you perform a thorough code review. Look for variable naming, "
            "ensure functions do one thing, check test coverage, and follow PEP8 guidelines. "
            "Use this prompt template when auditing pull requests."
        )
        stub_extractor = StubExtractor([
            {"label": "prompt_pattern", "text": "prompt template", "confidence": 0.88, "start": 0, "end": 15}
        ])

        result = classify_content_taxonomy(
            title, text, duration=300,
            extractor=stub_extractor, jev=self.fallback_jev
        )
        self.assertEqual(result["taxonomy"], "SINGLE_ATOMIC_SKILL")
        self.assertFalse(result["is_hybrid"])
        self.assertFalse(result["should_decompose"])

    # ── Workflow DAG Generation & Packaging ───────────────────────────────────

    def test_companion_workflow_dag_generation(self):
        skill_name = "stripe-refund-evaluator"
        desc = "Evaluates failed charge events and decides whether to grant instant refund."
        entities = [{"text": "webhook endpoint"}, {"text": "postgres database"}]
        wf = generate_companion_workflow(skill_name, desc, entities)

        self.assertIn("name", wf)
        self.assertIn("Workflow: Stripe Refund Evaluator", wf["name"])
        self.assertIn("nodes", wf)
        node_names = [n["name"] for n in wf["nodes"]]
        self.assertIn("Deterministic Ingestion Trigger", node_names)
        self.assertIn("Payload Sanitization & HMAC Verification", node_names)
        self.assertIn("Agent Skill Boundary: Stripe Refund Evaluator", node_names)
        self.assertIn("Deterministic Action & State Persistence", node_names)

        # Verify real Node.js HMAC crypto implementation
        sanitize_node = next(n for n in wf["nodes"] if n["name"] == "Payload Sanitization & HMAC Verification")
        js_code = sanitize_node["parameters"]["jsCode"]
        self.assertIn("crypto.createHmac('sha256'", js_code)
        self.assertIn("WEBHOOK_HMAC_SECRET", js_code)

        # Verify dynamic agent boundary URL
        boundary_node = next(n for n in wf["nodes"] if n["name"] == "Agent Skill Boundary: Stripe Refund Evaluator")
        url_param = boundary_node["parameters"]["url"]
        self.assertIn("$env.SYSTEM_ONE_URL", url_param)
        self.assertIn("http://127.0.0.1:8000", url_param)

    def test_build_universal_skill_hybrid_packaging_defensive_duplication_check(self):
        """Ensures workflows/workflow.json is the single source of truth and defensively skips any workflow.json in references."""
        temp_dir = tempfile.mkdtemp()
        try:
            skill_name = "test-hybrid-skill"
            wf_data = generate_companion_workflow(skill_name, "Test description", [])
            skill_data = {
                "name": skill_name,
                "description": "A hybrid skill test",
                "keywords": ["test", "hybrid"],
                "difficulty": "intermediate",
                "prerequisites": [],
                "skill_body": "# Test Hybrid Skill\n\nInstructions here.",
                "workflow": wf_data,
                "references": [
                    # Even if an erroneous workflow.json is passed in references, skill_builder MUST skip it
                    {"filename": "workflow.json", "content": json.dumps(wf_data, indent=2)},
                    {"filename": "guide.md", "content": "Full guide content here with over 300 words..."}
                ]
            }

            build_universal_skill(skill_data, [], output_dir=temp_dir, enabled_adapters=[])
            skill_dir = Path(temp_dir) / skill_name

            # Verify files on disk
            self.assertTrue((skill_dir / "skill.md").exists())
            self.assertTrue((skill_dir / "metadata.yaml").exists())
            self.assertTrue((skill_dir / "workflows/workflow.json").exists())
            # Defensively NOT written to references/
            self.assertFalse((skill_dir / "references/workflow.json").exists())
            self.assertTrue((skill_dir / "references/guide.md").exists())

            # Verify workflow.json content is valid JSON
            with open(skill_dir / "workflows/workflow.json") as f:
                saved_wf = json.load(f)
            self.assertEqual(saved_wf["name"], wf_data["name"])

        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
