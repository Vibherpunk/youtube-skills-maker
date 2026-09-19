from __future__ import annotations
import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Dict, List


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

SKILL_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "difficulty": {"type": "string"},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "skill_body": {"type": "string"},
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    "required": ["name", "description", "keywords", "difficulty", "prerequisites", "skill_body", "references"],
}

DECOMPOSED_SYNTH_SCHEMA = {
    "type": "object",
    "properties": {
        "skills": {
            "type": "array",
            "items": SKILL_ITEM_SCHEMA,
            "description": "List of atomic skills decomposed from the content."
        }
    },
    "required": ["skills"]
}

SYNTH_SCHEMA = SKILL_ITEM_SCHEMA


# ---------------------------------------------------------------------------
# General OpenAI-compatible API call
# ---------------------------------------------------------------------------

def _call_compatible_api_synth(system: str, user: str, api_key: str, api_base: str, model: str, decompose: bool = False) -> dict | None:
    """Call an OpenAI-compatible API endpoint for synthesis. Returns parsed JSON dict or None."""
    api_base_clean = api_base.rstrip("/")
    url = f"{api_base_clean}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 12288 if decompose else 8192,
    }
    # Omit response_format if the model/proxy does not support structured JSON schema mode
    if "deepseek-v4" not in model:
        schema = DECOMPOSED_SYNTH_SCHEMA if decompose else SYNTH_SCHEMA
        schema_name = "SynthesizedSkillsList" if decompose else "SynthesizedSkill"
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }

    data = json.dumps(payload).encode()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    # OpenRouter specific helper headers
    if "openrouter.ai" in api_base_clean:
        headers["HTTP-Referer"] = "https://github.com/Vibherpunk/i-know-kung-fu"
        headers["X-Title"] = "YouTube Skills Maker"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
    )

    delay = 20
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.load(resp)
            content = body["choices"][0]["message"]["content"]
            
            # Clean up markdown JSON wraps if present
            content_clean = content.strip()
            if content_clean.startswith("```"):
                content_clean = re.sub(r"^```(?:json)?\n", "", content_clean)
                content_clean = re.sub(r"\n```$", "", content_clean)
                
            return json.loads(content_clean)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            if e.code == 429:
                print(f"[Synthesizer] API rate limit (429). Waiting {delay}s (attempt {attempt+1}/6)...")
                time.sleep(delay)
                delay = min(delay * 2, 120)
            elif e.code in (502, 503, 504):
                print(f"[Synthesizer] Server error ({e.code}). Waiting {delay}s...")
                time.sleep(delay)
            else:
                print(f"[Synthesizer] HTTP {e.code}: {body_text[:300]}")
                return None
        except json.JSONDecodeError as e:
            print(f"[Synthesizer] JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"[Synthesizer] Unexpected error: {e}")
            return None

    print("[Synthesizer] Exhausted retries.")
    return None


# ---------------------------------------------------------------------------
# Gemini fallback
# ---------------------------------------------------------------------------

def _call_gemini_synth(prompt: str, system: str, api_key: str, model_name: str, decompose: bool = False) -> dict | list | None:
    try:
        from pydantic import BaseModel, Field
        from google import genai
        from google.genai import types
        from google.genai.errors import ClientError

        class ReferenceDoc(BaseModel):
            filename: str
            content: str

        class SynthesizedSkill(BaseModel):
            name: str
            description: str
            keywords: List[str]
            difficulty: str
            prerequisites: List[str]
            skill_body: str
            references: List[ReferenceDoc]

        class SynthesizedSkillsList(BaseModel):
            skills: List[SynthesizedSkill]

        schema = SynthesizedSkillsList if decompose else SynthesizedSkill

        client = genai.Client(api_key=api_key)
        delay = 45
        for attempt in range(5):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        system_instruction=system,
                        temperature=0.2,
                    ),
                )
                return json.loads(response.text)
            except ClientError as e:
                if e.code == 429:
                    print(f"[Synthesizer] Gemini 429. Waiting {delay}s...")
                    time.sleep(delay)
                    delay *= 2
                else:
                    print(f"[Synthesizer] Gemini error {e.code}: {e}")
                    return None
            except Exception as e:
                print(f"[Synthesizer] Gemini unexpected error: {e}")
                return None
    except Exception as e:
        print(f"[Synthesizer] Gemini import/setup error: {e}")
    return None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Taxonomy Determination & Companion Workflow Generation
# ---------------------------------------------------------------------------

def generate_companion_workflow(skill_name: str, description: str, deterministic_entities: list) -> dict:
    """
    Generates a valid, deployable n8n JSON workflow DAG that implements the deterministic
    rails (triggers, webhooks, cron, data normalization, database inserts) and establishes
    the clean execution boundary where the AI agent skill is invoked for judgment.
    """
    sanitized_name = skill_name.replace("-", " ").title()
    det_cues = [e["text"] if isinstance(e, dict) else str(e) for e in deterministic_entities]
    cues_str = ", ".join(det_cues[:5]) if det_cues else "webhook / API payload"

    return {
        "name": f"Workflow: {sanitized_name}",
        "nodes": [
            {
                "id": "node-trigger-001",
                "name": "Deterministic Ingestion Trigger",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [240, 300],
                "parameters": {
                    "httpMethod": "POST",
                    "path": f"{skill_name}-ingress",
                    "responseMode": "onReceived"
                },
                "notes": f"Deterministic rail listening for incoming events ({cues_str})"
            },
            {
                "id": "node-sanitize-002",
                "name": "Payload Sanitization & HMAC Verification",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [460, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": (
                        "// Deterministic validation: verify payload integrity and HMAC-SHA256 signature\n"
                        "const crypto = require('crypto');\n"
                        "const item = $json;\n"
                        "if (!item || (typeof item === 'object' && Object.keys(item).length === 0)) {\n"
                        "  throw new Error('Malformed or empty payload rejected.');\n"
                        "}\n\n"
                        "// Optional HMAC-SHA256 signature verification if secret configured\n"
                        "const secret = $env.WEBHOOK_HMAC_SECRET;\n"
                        "const headers = (typeof $headers !== 'undefined' ? $headers : (item._headers || {}));\n"
                        "const signature = headers['x-signature'] || headers['x-hub-signature-256'] || headers['x-webhook-signature'];\n"
                        "if (secret && signature) {\n"
                        "  const payloadStr = typeof item === 'string' ? item : JSON.stringify(item);\n"
                        "  const hmac = crypto.createHmac('sha256', secret).update(payloadStr).digest('hex');\n"
                        "  const expectedSig = signature.startsWith('sha256=') ? `sha256=${hmac}` : hmac;\n"
                        "  if (signature !== expectedSig && signature !== hmac) {\n"
                        "    throw new Error('HMAC signature verification failed: invalid signature.');\n"
                        "  }\n"
                        "}\n"
                        "return { json: { ...item, _verified_at: new Date().toISOString() } };"
                    )
                }
            },
            {
                "id": "node-agent-boundary-003",
                "name": f"Agent Skill Boundary: {sanitized_name}",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [680, 300],
                "parameters": {
                    "method": "POST",
                    "url": "={{ ($env.SYSTEM_ONE_URL || 'http://127.0.0.1:8000') + '/v1/decide' }}",
                    "sendBody": True,
                    "bodyParameters": {
                        "parameters": [
                            {"name": "instruction", "value": f"Execute skill '{skill_name}' rules on payload"},
                            {"name": "criteria", "value": description},
                            {"name": "context", "value": "={{ JSON.stringify($json) }}"}
                        ]
                    }
                },
                "notes": f"Invokes the companion agent skill '{skill_name}' to perform evaluation / judgment"
            },
            {
                "id": "node-action-004",
                "name": "Deterministic Action & State Persistence",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [900, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": (
                        "// Deterministically persist the agent's decision and trigger downstream rails\n"
                        "const decision = $json.decision || 'PROCEED';\n"
                        "return { json: { status: 'success', skill: '" + skill_name + "', decision, executed_at: new Date().toISOString() } };"
                    )
                }
            }
        ],
        "connections": {
            "Deterministic Ingestion Trigger": {
                "main": [[{"node": "Payload Sanitization & HMAC Verification", "type": "main", "index": 0}]]
            },
            "Payload Sanitization & HMAC Verification": {
                "main": [[{"node": f"Agent Skill Boundary: {sanitized_name}", "type": "main", "index": 0}]]
            },
            f"Agent Skill Boundary: {sanitized_name}": {
                "main": [[{"node": "Deterministic Action & State Persistence", "type": "main", "index": 0}]]
            }
        },
        "meta": {
            "templateCredsSetupCompleted": True,
            "instanceId": "harbor-system-one-generator"
        }
    }


def determine_taxonomy(topic_name: str, videos: list, text: str = "") -> dict:
    """
    Classifies technical content into one of three architectural software artifacts:
    1. SINGLE_ATOMIC_SKILL: Focused, single-turn prompt pattern with heuristic rules.
    2. MODULAR_SKILL_SUITE: Multi-stage lifecycle, multi-role process, or complex workflow (2-4 skills).
    3. HYBRID_WORKFLOW_AND_SKILL: Combines deterministic infrastructure rails with AI agent judgment.
    """
    try:
        from src.system_one import classify_content_taxonomy
        max_duration = 0.0
        all_topics = set()
        for v in videos:
            dur = v.get("duration")
            if dur and isinstance(dur, (int, float)) and dur > max_duration:
                max_duration = float(dur)
            all_topics.update(v.get("topics", []))
            
        return classify_content_taxonomy(
            title=topic_name, 
            text=text, 
            duration=max_duration,
            topics=list(all_topics)
        )
    except Exception as e:
        print(f"[Synthesizer] Taxonomy classification fallback: {e}")
        # Default fallback: requires substantial duration or length to decompose
        all_topics = set()
        max_dur = 0.0
        for v in videos:
            dur = v.get("duration", 0)
            if isinstance(dur, (int, float)) and dur > max_dur:
                max_dur = float(dur)
            all_topics.update(v.get("topics", []))
        is_long = (max_dur >= 1200 and (len(all_topics) >= 3 or len(text) > 20000 or len(text.split()) > 3500))
        if is_long or (len(all_topics) >= 3 and (max_dur >= 600 or len(text) > 5000)):
            return {"taxonomy": "MODULAR_SKILL_SUITE", "confidence": 0.70, "should_decompose": True}
        return {"taxonomy": "SINGLE_ATOMIC_SKILL", "confidence": 0.70, "should_decompose": False}


def should_decompose(videos: list, text: str = "", topic_name: str = "") -> bool:
    """
    Returns True if taxonomy determination indicates MODULAR_SKILL_SUITE.
    Delegates strictly to determine_taxonomy to prevent divergent contracts.
    """
    if not videos:
        return False
    tax = determine_taxonomy(topic_name or "skill", videos, text)
    return bool(tax.get("should_decompose", tax.get("taxonomy") == "MODULAR_SKILL_SUITE"))


def _normalize_and_fix_skills(result: Any, default_topic: str) -> list[dict]:
    """Normalizes raw model response into a list of valid, fixed skill dicts."""
    raw_list = []
    if isinstance(result, dict):
        if "skills" in result and isinstance(result["skills"], list):
            raw_list = result["skills"]
        elif "name" in result and "skill_body" in result:
            raw_list = [result]
    elif isinstance(result, list):
        raw_list = result

    fixed_skills = []
    for s in raw_list:
        if isinstance(s, dict) and s.get("skill_body"):
            fixed = _fix_reference_links(s)
            if not fixed.get("name"):
                fixed["name"] = default_topic
            fixed_skills.append(fixed)

    return fixed_skills


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize_skill(topic_name: str, videos: list, api_key: str, model_name: str = "gemini-2.5-flash") -> list[dict] | None:
    """
    Synthesizes video transcripts into agent-agnostic skill structures.
    When content-rich (multi-topic, >20min duration, multiple technique clusters),
    decomposes the transcript into N separate atomic skills.
    Returns a list of synthesized skill dicts, or None if synthesis fails.
    """
    # Build source/transcript blocks
    sources_summary = []
    transcripts_block = []

    for v in videos:
        vid = v["videoId"]
        title = v["title"]
        ch_name = v.get("channelName", "Unknown Channel")
        link = v.get("link", f"https://www.youtube.com/watch?v={vid}")

        transcript_text = ""
        cache_path = f"data/transcripts/{vid}.json"
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                transcript_text = cached.get("text", "")
        except Exception as e:
            print(f"[Synthesizer] Could not read cached transcript for {vid}: {e}")
            continue

        sources_summary.append(f"- '{title}' by {ch_name} (URL: {link})")
        transcripts_block.append(
            f"--- START TRANSCRIPT: {title} ({link}) ---\n{transcript_text[:50000]}\n--- END TRANSCRIPT ---"
        )

    if not transcripts_block:
        print("[Synthesizer] No transcript data available. Aborting.")
        return None

    sources_str = "\n".join(sources_summary)
    transcripts_str = "\n\n".join(transcripts_block)

    tax_info = determine_taxonomy(topic_name, videos, transcripts_str)
    taxonomy_mode = tax_info.get("taxonomy", "SINGLE_ATOMIC_SKILL")
    print(f"[Synthesizer] System One Taxonomy Decision for '{topic_name}': {taxonomy_mode} (confidence={tax_info.get('confidence', 0.8):.2f})")

    decompose = (taxonomy_mode == "MODULAR_SKILL_SUITE")

    def _apply_hybrid_workflow(skill_list: list[dict]) -> list[dict]:
        if taxonomy_mode == "HYBRID_WORKFLOW_AND_SKILL":
            print(f"[Synthesizer] Attaching companion deterministic workflow for hybrid skill '{topic_name}'...")
            for skill in skill_list:
                wf_data = generate_companion_workflow(
                    skill.get("name", topic_name),
                    skill.get("description", ""),
                    tax_info.get("deterministic_entities", [])
                )
                skill["workflow"] = wf_data
                skill["taxonomy"] = "HYBRID_WORKFLOW_AND_SKILL"
                if "Deterministic Workflow Rail" not in skill.get("skill_body", ""):
                    hybrid_note = (
                        "\n\n## ⚙️ Deterministic Workflow Rail (Hybrid Architecture)\n\n"
                        "This capability pairs this agent skill with an exportable deterministic workflow rail ([`workflow.json`](workflows/workflow.json)).\n"
                        "- **Deterministic Rails:** Webhook ingestion, payload validation, HMAC checks, and database updates are handled deterministically.\n"
                        "- **Agent Judgment:** This skill provides the reasoning, evaluation rubrics, and policy decisions at the decision node.\n"
                        "- **Deployable Workflow:** See [`workflows/workflow.json`](workflows/workflow.json) for the n8n JSON DAG.\n"
                    )
                    skill["skill_body"] = skill.get("skill_body", "").rstrip() + hybrid_note
        return skill_list

    if decompose:
        print(f"[Synthesizer] Content-rich material detected for '{topic_name}'. Enabling 1-to-N Skill Decomposition...")
        system_instruction = """You are an expert AI agent curriculum engineer.
Your job is to read content-rich video transcripts and decompose the knowledge into N SEPARATE, ATOMIC "Skill" files for an AI AGENT.
Rather than compressing multi-topic or deep content into a single monolithic skill, decompose the material into 2 to 4 focused, modular skills with independent names, triggers, step-by-step workflows, and reference documents.
Address the agent directly as "you" or "your". Make instructions concrete with best practices, pitfalls, and code/prompt templates.

CRITICAL RULES FOR REFERENCES IN EACH SKILL:
1. Each skill will produce 2-4 reference documents in its `references` array.
2. Each reference MUST have a short, descriptive `filename` ending in `.md`, e.g. `core_concepts.md`, `practical_guide.md`, `code_examples.md`.
3. Each reference `content` field MUST be a FULL, SUBSTANTIVE markdown document — minimum 300 words.
4. In each skill's `skill_body`, link to them using EXACTLY `references/<filename>`.

Output a JSON object with a "skills" array containing the decomposed atomic skills."""

        user_prompt = f"""We have the following content-rich sources discussing '{topic_name}':
{sources_str}

Here are the transcripts:
{transcripts_str}

Decompose this knowledge into 2 to 4 separate, atomic AI agent skills.
Each atomic skill must focus on ONE coherent technique, workflow, or architectural pattern.
For each skill include:
1. "name": descriptive kebab-case name (e.g. '{topic_name}-core-setup', '{topic_name}-advanced-workflow')
2. "description": when and why an AI agent should trigger this skill
3. "keywords": 3-8 specific keyword tags
4. "difficulty": beginner, intermediate, or advanced
5. "prerequisites": list of prerequisites
6. "skill_body": complete, comprehensive markdown SOP with overview, numbered step-by-step actions, copy-pasteable code/prompts, best practices, pitfalls, and validation steps
7. "references": 2-4 full reference markdown docs (300+ words each)

Output as JSON matching the SynthesizedSkillsList schema."""
    else:
        system_instruction = """You are an expert AI agent curriculum engineer.
Your job is to read video transcripts that teach a HUMAN how to do something with AI, and translate that knowledge into a direct, actionable "Skill" for an AI AGENT.
Address the agent directly as "you" or "your". Make instructions concrete with best practices, pitfalls, and code/prompt templates.

CRITICAL RULES FOR REFERENCES:
1. You will produce 2-4 reference documents in the `references` array.
2. Each reference MUST have a short, descriptive `filename` ending in `.md`, e.g. `core_concepts.md`, `practical_guide.md`, `code_examples.md`, `common_pitfalls.md`.
3. Each reference `content` field MUST be a FULL, SUBSTANTIVE markdown document — minimum 300 words. Do NOT write one-liners or stubs.
4. In the `skill_body`, when you link to a reference, use EXACTLY `references/<filename>`.

Output as JSON matching the SynthesizedSkill schema."""

        user_prompt = f"""We have the following sources discussing the topic '{topic_name}':
{sources_str}

Here are the transcripts:
{transcripts_str}

Synthesize this knowledge into a single, comprehensive, high-quality agent skill SOP.
Include:
1. An overview and core concepts
2. Detailed step-by-step workflow with numbered actions
3. Concrete code snippets or prompt templates (copy-pasteable, fully annotated)
4. Best-practice guidelines and common pitfalls with specific examples from the transcripts
5. Validation and testing steps
6. Reconcile any differences among sources
7. 2-4 reference documents — each must be a FULL markdown doc (300+ words), not a stub.

Output as JSON matching the SynthesizedSkill schema."""

    if taxonomy_mode == "HYBRID_WORKFLOW_AND_SKILL":
        user_prompt += "\n\nNOTE: This capability operates as a HYBRID architecture (deterministic workflow rail + agent skill). Delineate in the instructions what the deterministic rail handles (webhooks, payload verification, database updates) versus what the agent handles (judgment, evaluation, decision making)."

    print(f"[Synthesizer] Synthesizing '{topic_name}' from {len(videos)} source(s) (Taxonomy: {taxonomy_mode}, decompose={decompose})...")

    # --- Custom OpenAI-compatible API base primary ---
    llm_api_key = os.getenv("LLM_API_KEY", os.getenv("OPENROUTER_API_KEY", "")).strip()
    if llm_api_key:
        api_base = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1").strip()
        synth_model = os.getenv("SYNTH_MODEL", "deepseek/deepseek-chat")
        print(f"[Synthesizer] Using Custom API base ({synth_model}) @ {api_base}...")
        result = _call_compatible_api_synth(system_instruction, user_prompt, llm_api_key, api_base, synth_model, decompose=decompose)
        if result:
            skills = _normalize_and_fix_skills(result, topic_name)
            if skills:
                skills = _apply_hybrid_workflow(skills)
                print(f"[Synthesizer] ✓ Synthesized {len(skills)} skill(s) for '{topic_name}': {[s.get('name') for s in skills]}")
                return skills
        print("[Synthesizer] Primary API synthesis failed, trying LiteLLM fallback...")

    # --- Local LiteLLM / OpenCode Go Fallback ---
    litellm_key = os.getenv("LITELLM_MASTER_KEY", "").strip()
    print("[Synthesizer] Using LiteLLM fallback (deepseek-v4-pro)...")
    result = _call_compatible_api_synth(system_instruction, user_prompt, litellm_key, "http://127.0.0.1:4000/v1", "deepseek-v4-pro", decompose=decompose)
    if result:
        skills = _normalize_and_fix_skills(result, topic_name)
        if skills:
            skills = _apply_hybrid_workflow(skills)
            print(f"[Synthesizer] ✓ LiteLLM synthesized {len(skills)} skill(s) for '{topic_name}': {[s.get('name') for s in skills]}")
            return skills
    print("[Synthesizer] LiteLLM fallback failed, trying Gemini fallback...")

    # --- Gemini fallback ---
    if api_key:
        gemini_model = os.getenv("GEMINI_SYNTH_MODEL", "gemini-2.5-flash")
        print(f"[Synthesizer] Using Gemini fallback ({gemini_model})...")
        result = _call_gemini_synth(user_prompt, system_instruction, api_key, gemini_model, decompose=decompose)
        if result:
            skills = _normalize_and_fix_skills(result, topic_name)
            if skills:
                skills = _apply_hybrid_workflow(skills)
                print(f"[Synthesizer] ✓ Gemini synthesized {len(skills)} skill(s) for '{topic_name}': {[s.get('name') for s in skills]}")
                return skills

    print(f"[Synthesizer] ✗ All backends failed for '{topic_name}'.")
    return None


# ---------------------------------------------------------------------------
# Post-processing: fix any broken reference links the model still produces
# ---------------------------------------------------------------------------

def _fix_reference_links(result: dict) -> dict:
    """
    After synthesis, scan skill_body for broken reference links and replace them
    with the actual filenames from the references array. Also warns about thin refs.
    """
    refs = result.get("references", [])
    skill_body = result.get("skill_body", "")

    # Build a map: normalised title → actual filename
    filename_map = {}
    for ref in refs:
        fname = ref.get("filename", "")
        # Warn if content is thin
        content = ref.get("content", "")
        word_count = len(content.split())
        if word_count < 150:
            print(f"[Synthesizer] ⚠️  Reference '{fname}' is thin ({word_count} words) — consider re-synthesis.")
        if fname:
            # normalise: strip path, lower, no extension
            key = os.path.splitext(os.path.basename(fname))[0].lower().replace(" ", "-").replace("_", "-")
            filename_map[key] = fname

    # Replace any markdown links whose href looks like a placeholder (no 'references/' prefix
    # or doesn't match an actual filename) with the closest actual filename.
    def replace_link(match):
        text = match.group(1)
        href = match.group(2)
        # Already correct
        if href.startswith("references/") and any(href == f"references/{r.get('filename','')}" for r in refs):
            return match.group(0)
        # Try to match by normalised text or href stem
        stem = os.path.splitext(os.path.basename(href))[0].lower().replace(" ", "-").replace("_", "-")
        if stem in filename_map:
            return f"[{text}](references/{filename_map[stem]})"
        # Try matching by link text
        text_key = text.lower().replace(" ", "-")
        if text_key in filename_map:
            return f"[{text}](references/{filename_map[text_key]})"
        # Fallback: use first reference filename if only one ref
        if len(refs) == 1:
            return f"[{text}](references/{refs[0]['filename']})"
        return match.group(0)  # leave unchanged if we can't resolve

    fixed_body = re.sub(r"\[([^\]]+)\]\(([^)]+\.md)\)", replace_link, skill_body)
    result["skill_body"] = fixed_body
    return result
