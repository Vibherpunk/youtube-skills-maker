import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Regex patterns to exclude child/toddler content
CHILD_CONTENT_REGEX = re.compile(
    r"\b("
    r"kids?|children|child|toddlers?|babies|baby|infant|nursery|"
    r"rhymes?|lullab(y|ies)|cocomelon|peppa(\s+pig)?|paw\s+patrol|"
    r"bluey|blippi|chuchu|dave\s+and\s+ava|disney\s+junior|sesame\s+street|"
    r"cartoons?\s+for\s+kids|toys?\s+review|preschool|kindergarten|"
    r"sing-?along|bedtime\s+stor(y|ies)|fairy\s+tales?|learn\s+colors|"
    r"learn\s+shapes|abc\s+song|phonics|kids\s+video|kids\s+tv"
    r")\b",
    re.IGNORECASE,
)

# AI and Tech topic keyword mapping
AI_KEYWORDS_MAP = {
    "prompt-engineering": ["prompt", "prompting", "system prompt", "few-shot"],
    "rag": ["rag", "retrieval augmented", "vector database", "vector search", "embedding"],
    "agents": ["agent", "agents", "agentic", "crewai", "autogen", "swarm", "langgraph"],
    "orchestration": ["orchestration", "workflow", "n8n", "pipeline", "dag"],
    "ai-coding": [
        "vibe coding", "cursor", "copilot", "windsurf", "coding", "code", "coder",
        "devin", "claudecode", "claude code", "opencode", "cline", "aider"
    ],
    "automation": ["automation", "automate", "make.com", "zapier", "bot"],
}

# Broad AI & tech keyword pattern for prioritization
AI_TECH_GENERAL_REGEX = re.compile(
    r"\b("
    r"ai|artificial intelligence|llm|llms|gpt|gpt-4|gpt-5|claude|gemini|deepseek|"
    r"agent|agents|rag|prompt|prompts|cursor|coding|code|vibe coding|python|"
    r"developer|tech|robot|robots|robotics|humanoid|software|machine learning|"
    r"deep learning|automation|copilot|langchain|llamaindex|ollama|local ai|"
    r"openai|anthropic|mistral|fine-tuning|transformer|orchestration|api|neural"
    r")\b",
    re.IGNORECASE,
)


def infer_topics(title: str, channel: str) -> list:
    """Infers skill topics and AI relevance based on video title and channel name."""
    text = f"{title} {channel}".lower()
    topics = set()
    for topic, kw_list in AI_KEYWORDS_MAP.items():
        for kw in kw_list:
            if kw in text:
                topics.add(topic)
                break
    if AI_TECH_GENERAL_REGEX.search(text):
        topics.add("ai-tech")
    return sorted(list(topics))


def _fetch_raw_feed(
    feed_url: str,
    browser: str = "chrome:Default",
    cookies_fallback: str = "cookies.txt",
    fetch_limit: int = 100,
) -> list:
    """
    Executes yt-dlp to extract flat playlist entries for a given feed URL.
    Attempts extraction using browser cookies first, falling back to cookies file.
    """
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser,
        "--flat-playlist",
        "--playlist-end", str(fetch_limit),
        "-J",
        feed_url,
    ]

    entries = None

    # 1. Attempt using browser cookies
    try:
        print(f"[FeedSource] Fetching {feed_url} using browser cookies ({browser})...")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            entries = data.get("entries")
        else:
            stderr_snippet = res.stderr[:200] if res.stderr else "Empty stderr"
            print(f"[FeedSource] Warning: yt-dlp browser cookies extraction failed (exit {res.returncode}): {stderr_snippet}")
    except Exception as e:
        print(f"[FeedSource] Warning: Error during browser cookies extraction: {e}")

    # 2. Attempt fallback if browser extraction failed
    if entries is None:
        fallback_candidates = [
            Path(cookies_fallback),
            Path(__file__).parent.parent / cookies_fallback,
            Path("cookies.txt"),
            Path("data/cookies.txt"),
        ]
        found_fallback = None
        for p in fallback_candidates:
            if p.exists():
                found_fallback = p
                break

        if found_fallback:
            print(f"[FeedSource] Attempting fallback with cookies file: {found_fallback}...")
            cmd_fallback = [
                "yt-dlp",
                "--cookies", str(found_fallback),
                "--flat-playlist",
                "--playlist-end", str(fetch_limit),
                "-J",
                feed_url,
            ]
            try:
                res = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=90)
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    entries = data.get("entries")
                else:
                    stderr_snippet = res.stderr[:200] if res.stderr else "Empty stderr"
                    print(f"[FeedSource] Error: yt-dlp cookies fallback failed: {stderr_snippet}")
            except Exception as e:
                print(f"[FeedSource] Error during cookies fallback extraction: {e}")
        else:
            print(f"[FeedSource] Error: Fallback cookies file not found at {cookies_fallback}.")

    if not entries:
        return []

    return [e for e in entries if isinstance(e, dict)]


def fetch_user_feed_videos(
    browser: str = "chrome:Default",
    feeds: list | None = None,
    limit_per_feed: int = 25,
    min_duration_seconds: int = 180,
    cookies_fallback: str = "cookies.txt",
    prioritize_ai_tech: bool = True,
    exclude_child_content: bool = True,
    **kwargs,
) -> list:
    """
    Ingests live YouTube feed videos from the user's personal recommendation feed.

    Filters:
    - Filters out music mix playlists (id starts with RD, Mix - title prefix, or playlist URLs)
    - Filters out YouTube Shorts and ultra-short videos (duration < min_duration_seconds or None)
    - Filters out child/toddler content if exclude_child_content is True
    - Prioritizes AI/tech videos if prioritize_ai_tech is True
    - Deduplicates across feeds and returns normalized video dictionaries
    """
    if feeds is None:
        feeds = ["https://www.youtube.com/"]
    elif isinstance(feeds, str):
        feeds = [feeds]

    all_videos = []
    seen_video_ids = set()
    fetch_limit = max(limit_per_feed * 4, 100)

    for feed_url in feeds:
        raw_entries = _fetch_raw_feed(
            feed_url=feed_url,
            browser=browser,
            cookies_fallback=cookies_fallback,
            fetch_limit=fetch_limit,
        )

        feed_candidates = []
        for entry in raw_entries:
            vid = entry.get("id")
            if not vid or not isinstance(vid, str):
                continue
            if vid in seen_video_ids:
                continue

            # Filter out playlists / music mixes
            if vid.startswith("RD") or entry.get("_type") == "playlist":
                continue
            url = entry.get("url", "")
            if "playlist?list=RD" in url or "list=RD" in url:
                continue
            title = (entry.get("title") or "").strip()
            if title.startswith("Mix -") or title.startswith("My Mix"):
                continue

            # Filter out shorts / videos under minimum duration
            duration = entry.get("duration")
            try:
                dur_val = float(duration) if duration is not None else None
            except (ValueError, TypeError):
                dur_val = None

            if dur_val is None or dur_val < min_duration_seconds:
                continue

            channel_name = (entry.get("channel") or entry.get("uploader") or "Unknown Channel").strip()

            # Filter out child content
            if exclude_child_content:
                if entry.get("is_kids") or entry.get("is_child_directed") or entry.get("made_for_kids"):
                    continue
                if CHILD_CONTENT_REGEX.search(title) or CHILD_CONTENT_REGEX.search(channel_name):
                    continue

            # Format publishedAt
            published_at = ""
            timestamp = entry.get("timestamp")
            if timestamp and isinstance(timestamp, (int, float)):
                try:
                    published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                except Exception:
                    pass
            if not published_at and entry.get("upload_date"):
                ud = str(entry["upload_date"])
                if len(ud) == 8 and ud.isdigit():
                    published_at = f"{ud[:4]}-{ud[4:6]}-{ud[6:]}T00:00:00Z"
            if not published_at:
                published_at = datetime.now(timezone.utc).isoformat()

            watch_link = (
                url
                if ("youtube.com/watch" in url or "youtu.be/" in url)
                else f"https://www.youtube.com/watch?v={vid}"
            )

            topics = infer_topics(title, channel_name)
            is_ai_tech = bool(topics) or bool(AI_TECH_GENERAL_REGEX.search(f"{title} {channel_name}"))

            video_record = {
                "videoId": vid,
                "title": title,
                "channelName": channel_name,
                "link": watch_link,
                "duration": int(dur_val),
                "publishedAt": published_at,
                "topics": topics,
                "is_ai_tech": is_ai_tech,
            }
            feed_candidates.append(video_record)

        # Prioritize within this feed if requested
        if prioritize_ai_tech:
            feed_candidates.sort(key=lambda v: (0 if v["is_ai_tech"] else 1, -v["duration"]))

        selected_from_feed = feed_candidates[:limit_per_feed]
        for v in selected_from_feed:
            seen_video_ids.add(v["videoId"])
            all_videos.append(v)

        print(
            f"[FeedSource] Feed '{feed_url}': {len(raw_entries)} raw entries -> "
            f"{len(feed_candidates)} valid -> {len(selected_from_feed)} selected."
        )

    if prioritize_ai_tech:
        all_videos.sort(key=lambda v: (0 if v["is_ai_tech"] else 1))

    ai_count = sum(1 for v in all_videos if v.get("is_ai_tech"))
    print(f"[FeedSource] Total unique videos ingested: {len(all_videos)} (AI/Tech prioritized: {ai_count})")
    return all_videos
