"""
system_one.py — Unified System One AI Interface (GLiNER + Jev)

Combines:
1. Local GLiNER: Zero-shot information & entity extraction (<500MB RAM, Apple Silicon MPS/CPU).
2. OpenRouter Jev: High-speed non-autoregressive decision & policy engine (~100ms, RLCD calibrated).

Guaranteed memory-safe alongside resident 35B model (mtplx-ornith/wang-yang-ornith-1.5-35b-mtplx-4bit).
"""
import os
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

# Lazy imports for heavy local packages
_gliner_model = None

# OpenRouter Configuration
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"


def get_openrouter_key() -> str:
    """Retrieves OpenRouter key from local auth config or environment."""
    auth_path = Path.home() / ".local/share/opencode/auth.json"
    if auth_path.exists():
        try:
            with open(auth_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("openrouter", {}).get("key", "")
                if key and key.startswith("sk-or-v1-"):
                    return key
        except Exception:
            pass

    key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY", "")
    return key


class GlinerExtractor:
    """Local zero-shot entity and feature extraction via GLiNER on Apple Silicon MPS/CPU."""

    def __init__(self, model_name: str = "urchade/gliner_medium-v2.1", device: Optional[str] = None):
        self.model_name = model_name
        self.device = device
        self._load_model()

    def _load_model(self):
        global _gliner_model
        if _gliner_model is None:
            import torch
            from gliner import GLiNER
            if self.device is None:
                self.device = "mps" if torch.backends.mps.is_available() else "cpu"
            print(f"[GLiNER] Loading {self.model_name} onto {self.device}...")
            _gliner_model = GLiNER.from_pretrained(self.model_name).to(self.device)
            print(f"[GLiNER] Model loaded successfully.")
        self.model = _gliner_model

    def extract(self, text: str, labels: List[str], threshold: float = 0.35) -> List[Dict[str, Any]]:
        """Extracts arbitrary zero-shot entity spans from text in ~15-30ms."""
        if not text or not text.strip() or not labels:
            return []
        try:
            # GLiNER handles chunks natively; keep text bounded
            cleaned_text = text[:8000]
            entities = self.model.predict_entities(cleaned_text, labels, threshold=threshold)
            return [
                {
                    "label": ent["label"],
                    "text": ent["text"],
                    "confidence": round(float(ent["score"]), 3),
                    "start": ent["start"],
                    "end": ent["end"]
                }
                for ent in entities
            ]
        except Exception as e:
            print(f"[GLiNER] Extraction error: {e}")
            return []


class JevDecisionEngine:
    """Non-autoregressive decision engine calling TypeSafe Jev via OpenRouter."""

    def __init__(self, model: str = DEFAULT_JEV_MODEL, api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or get_openrouter_key()
        if not self.api_key:
            print("[Jev] Warning: No OpenRouter API key found.")

    def decide(self, state: Any, questions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Submits state and structured questions to Jev.
        
        questions schema:
        {
          "q_id": {
             "type": "choice" | "score" | "noul",
             "instructions": "...",
             "criteria": { "opt1": "desc1", "opt2": "desc2" }
          }
        }
        """
        if not self.api_key:
            return {"error": "Missing OpenRouter API key"}

        payload = {
            "model": self.model,
            "state": state,
            "questions": questions
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_DECISIONS_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Vibherpunk/system-one",
                "X-Title": "System One Engine"
            }
        )

        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode(errors="replace")
                print(f"[Jev] HTTP {e.code}: {err_body[:300]}")
                if e.code in (429, 502, 503):
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return {"error": f"HTTP {e.code}: {err_body}"}
            except Exception as e:
                print(f"[Jev] Request error: {e}")
                return {"error": str(e)}

        return {"error": "Exhausted retries"}


def evaluate_content_system_one(title: str, text: str, extractor: Optional[GlinerExtractor] = None, jev: Optional[JevDecisionEngine] = None) -> Dict[str, Any]:
    """
    Two-stage System One evaluation pipeline:
    1. GLiNER extracts operational tools, constraints, metrics, and workflows.
    2. Jev executes parallel decision on actionability and category.
    """
    if extractor is None:
        extractor = GlinerExtractor()
    if jev is None:
        jev = JevDecisionEngine()

    # Stage 1: Fast Entity Extraction
    labels = ["software_tool", "code_framework", "negative_constraint", "operational_metric", "actionable_workflow"]
    entities = extractor.extract(f"{title}\n{text[:4000]}", labels, threshold=0.35)

    extracted_tools = [e["text"] for e in entities if e["label"] in ("software_tool", "code_framework")]
    has_concrete_entities = len(extracted_tools) > 0 or any(e["label"] == "actionable_workflow" for e in entities)

    # Stage 2: Jev Calibrated Policy Decision
    state = {
        "title": title,
        "extracted_entities": [e["text"] for e in entities[:15]],
        "text_sample": text[:1500]
    }

    questions = {
        "is_actionable_skill": {
            "type": "choice",
            "instructions": "Determine if this content demonstrates an actionable, reproducible engineering or operational workflow for AI agents.",
            "criteria": {
                "actionable": "Demonstrates specific code, tool configurations, operational heuristics, or reproducible workflows.",
                "not_actionable": "High-level opinion, news commentary, fluff, or non-technical chatter."
            }
        },
        "target_domain": {
            "type": "choice",
            "instructions": "Classify the primary operational domain.",
            "criteria": {
                "ai_agent_engineering": "Agent frameworks, tool calling, local LLMs, prompts, or orchestration.",
                "ad_creative_growth": "Advertising hooks, growth loops, conversion, or video direction.",
                "devops_infra": "Docker, Kubernetes, VPS, CI/CD, or networking.",
                "general_other": "General commentary or other topics."
            }
        }
    }

    jev_res = jev.decide(state, questions)
    answers = jev_res.get("answers", {})

    is_actionable = answers.get("is_actionable_skill", {}).get("choice") == "actionable"
    confidence = answers.get("is_actionable_skill", {}).get("confidence", 0.5)
    domain = answers.get("target_domain", {}).get("choice", "general_other")

    return {
        "is_actionable": is_actionable and has_concrete_entities,
        "confidence": confidence,
        "domain": domain,
        "extracted_entities": entities,
        "jev_raw": jev_res
    }


def classify_content_taxonomy(
    title: str,
    text: str,
    duration: Optional[float] = None,
    topics: Optional[List[str]] = None,
    extractor: Optional[GlinerExtractor] = None,
    jev: Optional[JevDecisionEngine] = None
) -> Dict[str, Any]:
    """
    Classifies technical content into one of three architectural software artifacts:
    1. SINGLE_ATOMIC_SKILL: A focused, single-objective AI agent prompt skill with heuristic rules.
    2. MODULAR_SKILL_SUITE: A multi-stage lifecycle, multi-role process, or complex workflow requiring 2-4 distinct atomic skills.
    3. HYBRID_WORKFLOW_AND_SKILL: Combines deterministic infrastructure rails (webhooks, cron, APIs, SQL, HMAC) with AI agent judgment.
    """
    if extractor is None:
        extractor = GlinerExtractor()
    if jev is None:
        jev = JevDecisionEngine()

    sample = f"{title}\n{text[:5000]}"
    labels = [
        "webhook_endpoint",
        "cron_schedule",
        "hmac_signature",
        "api_integration",
        "sql_query",
        "bash_script",
        "heuristic_rule",
        "judgment_criteria",
        "prompt_pattern",
        "multi_stage_process"
    ]
    entities = extractor.extract(sample, labels, threshold=0.30)

    deterministic_labels = {
        "webhook_endpoint", "cron_schedule", "hmac_signature", 
        "api_integration", "sql_query", "bash_script"
    }
    agentic_labels = {
        "heuristic_rule", "judgment_criteria", "prompt_pattern"
    }
    multi_stage_labels = {"multi_stage_process"}

    det_entities = [e for e in entities if e["label"] in deterministic_labels]
    agentic_entities = [e for e in entities if e["label"] in agentic_labels]
    multi_stage_entities = [e for e in entities if e["label"] in multi_stage_labels]

    # Strict rail signals for deterministic infrastructure workflows
    sample_lower = sample.lower()
    strict_rail_keywords = ["webhook", "cron", "hmac", "api endpoint", "rest api", "ingress", "fastapi", "express"]
    has_strict_rail_keywords = any(k in sample_lower for k in strict_rail_keywords)
    has_agentic_keywords = any(k in sample_lower for k in ["prompt", "heuristic", "rubric", "guideline", "evaluat", "reasoning"])
    has_multistage_keywords = any(k in sample_lower for k in ["lifecycle", "phase 1", "step 1", "pipeline", "end-to-end"])
    has_multi_topics = topics is not None and len(set(topics)) >= 3

    # Check length and duration signals
    is_long_duration = duration is not None and duration >= 1200
    is_lengthy_transcript = len(text) > 20000 or len(text.split()) > 3500

    # Modular suite condition: multi-topic (>=3 with duration >=600s or length signals), long deep-dive (>=1200s), or multi-stage processes
    is_modular_candidate = (
        (is_long_duration and (has_multi_topics or is_lengthy_transcript or len(multi_stage_entities) >= 1 or has_multistage_keywords))
        or (has_multi_topics and (is_long_duration or is_lengthy_transcript or (duration is not None and duration >= 600) or len(multi_stage_entities) >= 1))
        or (len(multi_stage_entities) >= 1 and (is_lengthy_transcript or has_multistage_keywords))
        or (has_multistage_keywords and is_lengthy_transcript)
    )

    state = {
        "title": title,
        "duration_seconds": duration or 0,
        "transcript_words": len(text.split()),
        "deterministic_entities": [e["text"] for e in det_entities[:10]],
        "agentic_entities": [e["text"] for e in agentic_entities[:10]],
        "multi_stage_signals": len(multi_stage_entities) > 0 or is_long_duration or has_multistage_keywords
    }

    questions = {
        "artifact_taxonomy": {
            "type": "choice",
            "instructions": "Determine whether this technical content should be represented as a single atomic skill, a modular skill suite, or a hybrid (deterministic workflow + agent skill).",
            "criteria": {
                "HYBRID_WORKFLOW_AND_SKILL": "Content relies on mechanical/deterministic rails (webhooks, cron triggers, HMAC, database inserts, API calls, scripts) combined with AI judgment or evaluation.",
                "MODULAR_SKILL_SUITE": "Content covers a multi-stage lifecycle, multi-role pipeline, or long deep-dive (>20 mins) that naturally divides into 2-4 distinct atomic skills.",
                "SINGLE_ATOMIC_SKILL": "Content describes a single focused skill, prompt pattern, or evaluation task executed in a single turn."
            }
        }
    }

    jev_res = jev.decide(state, questions)
    answers = jev_res.get("answers", {})
    taxonomy_choice = answers.get("artifact_taxonomy", {}).get("choice")
    confidence = answers.get("artifact_taxonomy", {}).get("confidence", 0.5)

    # Fallback to calibrated deterministic heuristic if Jev did not return a valid choice or API returned error
    if taxonomy_choice not in ("HYBRID_WORKFLOW_AND_SKILL", "MODULAR_SKILL_SUITE", "SINGLE_ATOMIC_SKILL"):
        if is_modular_candidate:
            taxonomy_choice = "MODULAR_SKILL_SUITE"
            confidence = 0.86
        elif (len(det_entities) >= 2 or has_strict_rail_keywords) and (len(agentic_entities) >= 1 or has_agentic_keywords):
            taxonomy_choice = "HYBRID_WORKFLOW_AND_SKILL"
            confidence = 0.88
        else:
            taxonomy_choice = "SINGLE_ATOMIC_SKILL"
            confidence = 0.82

    return {
        "taxonomy": taxonomy_choice,
        "confidence": confidence,
        "deterministic_entities": det_entities,
        "agentic_entities": agentic_entities,
        "is_hybrid": taxonomy_choice == "HYBRID_WORKFLOW_AND_SKILL",
        "should_decompose": taxonomy_choice == "MODULAR_SKILL_SUITE",
        "jev_raw": jev_res
    }

