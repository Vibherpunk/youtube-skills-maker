# YouTube Skills Maker

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![System One: GLiNER](https://img.shields.io/badge/System%20One-GLiNER%20(MPS%2FCPU)-orange.svg)](https://github.com/urchade/GLiNER)
[![Multi-Platform Adapters](https://img.shields.io/badge/adapters-Antigravity%20%7C%20Cursor%20%7C%20Claude%20%7C%20Copilot%20%7C%20Windsurf-brightgreen.svg)](#universal-platform-packaging)
[![Decomposition](https://img.shields.io/badge/decomposition-1--to--N%20Atomic%20Skills-purple.svg)](#1-to-n-atomic-skill-decomposition-engine)

An enterprise-grade, autonomous knowledge synthesis pipeline that transforms practitioner video content into structured, production-ready AI agent skills. Moving beyond passive databases, YouTube Skills Maker ingests live recommendation and subscription feeds directly from authenticated browser sessions, runs sub-50ms zero-shot neural perception to filter actionable engineering paradigms, decomposes multi-hour masterclasses into atomic skill suites, and compiles universal adapter formats across all major agent environments.

---

## 🚀 Key Architectural Capabilities

### 1. Dynamic Personal Feed & Subscription Ingestion (`src/feed_source.py`)
Rather than relying on static or curated database queues, the pipeline connects directly to the operator's active YouTube profile (`chrome:Default`) via `yt-dlp`:
- **Algorithmic Home Feed Extraction:** Ingests live personalized recommendations (`https://www.youtube.com/`) reflecting active technical interests.
- **Subscription Feed Scanning:** Continuously monitors tracked engineering channels (`https://www.youtube.com/feed/subscriptions`) for newly released practitioner tutorials.
- **Signal-to-Noise Filtering:** Automatically drops YouTube Shorts ($< 180\text{s}$), algorithmic music mixes (`RD...`), and duplicate video IDs before processing.

### 2. Sub-50ms Zero-Shot Neural Perception (Local GLiNER Engine)
Eliminates wasteful and slow LLM calls on irrelevant videos through an embedded bidirectional encoder model ([`urchade/gliner_medium-v2.1`](https://github.com/urchade/GLiNER)) running natively on Apple Silicon Metal (MPS) or CPU:
- **Zero-Shot Entity & Concept Extraction:** Instantly extracts target entities:
  - `framework_or_library` (e.g., PyTorch, LangGraph, vLLM, FastEmbed)
  - `actionable_technique` (e.g., Speculative Decoding, AST Linting, RLCD)
  - `code_paradigm` (e.g., Non-Autoregressive Extraction, Memory Enclaves)
  - `operational_metric` (e.g., Token Latency, VRAM Footprint, Inode Usage)
- **High-Throughput Perception Filter:** Evaluates transcript density and filters out generic commentary, marketing hype, or surface-level summaries in $<25\text{ms}$ consuming $<450\text{MB}$ RAM.

### 3. 1-to-N Atomic Skill Decomposition Engine (`src/synthesize.py`)
Standard tools compress complex multi-topic tutorials into shallow, monolithic summaries or discard them entirely. YouTube Skills Maker incorporates an automated decomposition heuristic:
- **Decomposition Heuristic (`should_decompose`):** Triggered automatically when video duration $\ge 1200\text{s}$ ($20+\text{ minutes}$) or when neural entity extraction identifies high multi-topic conceptual density ($\ge 3$ distinct architectural paradigms).
- **Atomic Skill Synthesis:** Disassembles the transcript into an array of 2 to 4 focused, composable agent skills.
- **Cross-Referenced Markdown Integrity:** Validates relative markdown links across all emitted sibling skills, ensuring unified references while maintaining atomic modularity.

### 4. Resilient 3-Layer Transcript Extraction
Ensures 100% transcript acquisition across diverse video configurations:
1. **Layer 1 (Free / Instant):** Direct subtitle API extraction via `youtube-transcript-api`.
2. **Layer 2 (Auto-Generated Subtitle Fallback):** Headless automated VTT/SRT download via `yt-dlp`.
3. **Layer 3 (Multimodal Audio Transcription):** High-fidelity multimodal audio parsing using Gemini Flash audio comprehension when closed captions are disabled.

### 5. Universal Platform Packaging & Export
Synthesizes verified knowledge into a neutral core specification, then runs dedicated compiler adapters targeting modern AI coding environments:

| Platform | Emitted Format | Target Location |
| :--- | :--- | :--- |
| **Google Antigravity** | `SKILL.md` frontmatter + modular `references/` | `~/.agents/skills/<skill-name>/` |
| **Cursor IDE** | Unified `.mdc` rule definitions with activation triggers | `.cursor/rules/<skill-name>.mdc` |
| **Claude Code** | Structured guidelines for project context | `CLAUDE.md` / `.claude/skills/` |
| **GitHub Copilot** | Markdown workspace prompt instructions | `.github/copilot-instructions.md` |
| **Windsurf IDE** | Specialized workflow rules | `.windsurfrules` |

### 6. Ecosystem Deduplication & State Ledger
- **Public Registry Audit:** Queries Vercel's [skills.sh](https://skills.sh) public repository to avoid reinventing existing community skills.
- **Local Ledger Hash Tracking:** Maintains an atomic state store (`data/state.json`) recording processed video IDs, transcript hashes, extracted entities, and emitted skill directories.

---

## 🏛️ Pipeline Flow

```
   ┌─────────────────────────────────────────────────────────────┐
   │             Operator Personal YouTube Profile               │
   │      (Home Recommendation Feed + Channel Subscriptions)     │
   └──────────────────────────────┬──────────────────────────────┘
                                  │ yt-dlp (chrome:Default cookies)
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │          3-Layer Ingestion & Transcript Extraction          │
   │   (youtube-transcript-api ──> yt-dlp ──> Multimodal Audio)  │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │         GLiNER System One Perception Layer (MPS/CPU)        │
   │  Extracts: Code Paradigms, Libraries, Actionable Techniques │
   │                  Latency: 15ms - 25ms                       │
   └──────────────────────────────┬──────────────────────────────┘
                                  │ Actionable?
                        ┌─────────┴─────────┐
                     No │                   │ Yes
                        ▼                   ▼
                   [ Skipped ]    ┌──────────────────────────────┐
                                  │  Duration >= 20m or Multi-   │
                                  │  Topic Density >= 3 Topics?  │
                                  └───────┬──────────────┬───────┘
                                       No │              │ Yes
                                          ▼              ▼
                                  ┌──────────────┐ ┌──────────────┐
                                  │ 1 Focused    │ │ 1-to-N Suite │
                                  │ Atomic Skill │ │ (2-4 Skills) │
                                  └───────┬──────┘ └──────┬───────┘
                                          │               │
                                          ▼               ▼
   ┌─────────────────────────────────────────────────────────────┐
   │             Universal Multi-Platform Compiler               │
   │    Antigravity  │  Cursor (.mdc)  │  Claude Code (CLAUDE)   │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │      Staged into Harbor Skill Pool & Git Repository         │
   └─────────────────────────────────────────────────────────────┘
```

---

## 💻 Installation & Setup

### Prerequisites
- **Python 3.12+**
- **yt-dlp**: `brew install yt-dlp`
- **GitHub CLI**: `gh auth login`
- **Google Chrome**: Signed into your target YouTube account (uses profile `chrome:Default`).

### Installation
```bash
git clone https://github.com/Vibherpunk/youtube-skills-maker.git
cd youtube-skills-maker

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration (`config.yaml`)
Configure your ingestion sources and LLM providers:
```yaml
youtube_feed:
  browser: "chrome:Default"
  cookies_fallback: "cookies.txt"
  feeds:
    - "https://www.youtube.com/"
    - "https://www.youtube.com/feed/subscriptions"
  limit_per_feed: 20
  min_duration_seconds: 180
  prioritize_ai_tech: true

providers:
  eval_model: "gemini-2.5-flash"
  synth_model: "gemini-2.5-flash"
```

---

## ⚡ Usage

### 1. Dry Run (Inspect Feed & Test Extraction)
Runs the feed ingestor, extracts subtitles, and executes zero-shot GLiNER evaluation without writing skills or altering state:
```bash
python run.py --dry-run
```

### 2. Local Synthesis (Write Skills, Skip Git Push)
Generates skill files and platform adapters locally into `data/ai-skills/skills/`:
```bash
python run.py --no-push
```

### 3. Full Production Run
Evaluates videos, decomposes skills, builds all platform adapters, and commits/pushes new skills directly to your skill repository:
```bash
python run.py
```

### Options & Flags
- `--limit <n>`: Limit processing to $n$ candidate videos per execution run.
- `--reset-state`: Flushes `data/state.json`, allowing full re-processing of historical feeds.

---

## 📄 License & Attribution

Distributed under the **MIT License**. Engineered for autonomous agent environments, Harbor room routing, and multi-IDE agent operations.
