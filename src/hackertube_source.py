"""
hackertube_source.py — HackerTube-backed video discovery.

Replaces the personalised YouTube-feed ingestion as the pipeline's discovery
source with HackerTube, "the YouTube videos that Hacker News keeps telling each
other to watch" (https://hackertube.org).

WHY THIS ISN'T A NAIVE CRAWL OF hackertube.org
----------------------------------------------
hackertube.org is a single-page app. Every listing is served from /api/*, and
its robots.txt disallows /api/ for all user agents:

    User-agent: *
    Disallow: /api/
    Disallow: /download/

There is no sitemap and no server-rendered video page, so there is no
robots-permitted route into the catalogue itself. What HackerTube is *built
from*, however, is Hacker News: its whole corpus is stories whose URL is a
YouTube link. HN publishes a stable, documented, public search API
(hn.algolia.com). Reading that reproduces HackerTube's signal exactly, gives us
the submitter, score and comment count (a far better teachability prior than a
personal recommendation feed), and stays on the right side of hackertube.org's
crawl policy.

The module therefore:
  * checks hackertube.org's robots.txt at runtime and only touches a path that
    robots actually permits (it will not invent one that doesn't exist), then
  * falls back to Hacker News, which is where HackerTube's data comes from.

Record shape matches feed_source.fetch_user_feed_videos() exactly, plus
`hn_points` / `hn_comments` / `hn_id` so downstream ranking can use the
community signal.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone

from src.feed_source import (
    CHILD_CONTENT_REGEX,
    infer_topics,
)

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
YT_WATCH_RE = re.compile(r"(?:youtube\.com/watch\?[^#]*?\bv=([A-Za-z0-9_-]{11}))")
YT_SHORT_RE = re.compile(r"(?:youtu\.be/([A-Za-z0-9_-]{11}))")

# Titles that signal a transferable procedure rather than news/entertainment.
# HackerTube's top stories skew to "look at this" (Mars rover, black hole); the
# pipeline only wants videos a human could turn into instructions.
SKILL_SIGNAL_RE = re.compile(
    r"\b("
    r"how\s+(?:i|to|we)\b|from\s+scratch|let'?s\s+(?:build|make|write|code)|"
    r"tutorial|walkthrough|deep\s+dive|explained|internals|under\s+the\s+hood|"
    r"build(?:ing)?\s+(?:a|an|your|the)\b|implement(?:ing|ation)?|"
    r"reverse[-\s]?engineering|reverse[-\s]?engineer(?:ed)?|"
    r"introduction\s+to|intro\s+to|masterclass|crash\s+course|"
    r"setup|configure|workflow|tooling|optimiz(?:e|ing)|debug(?:ging)?|"
    r"refactor|migrat(?:e|ing)|automat(?:e|ing|ion)|"
    r"system\s+design|architecture|scaling|performance|benchmark"
    r")\b",
    re.IGNORECASE,
)

# Titles that signal news/commentary/entertainment — poor skill yield.
ANTI_SKILL_RE = re.compile(
    r"\b("
    r"trailer|teaser|advert|commercial|music\s+video|official\s+video|"
    r"interview|podcast\s+episode|keynote|announc(?:e|ement|es)|"
    r"lawsuit|sued|dies|dead|killed|arrested|scandal|drama|"
    r"unboxing|review|reaction|highlights|compilation|best\s+of|"
    r"vlog|day\s+in\s+the\s+life|log\s+cabin|tiny\s+house|survival|prank|"
    r"cooking|recipe|makeup|fitness|workout|wedding|travel\s+vlog"
    r")\b",
    re.IGNORECASE,
)

_USER_AGENT = "youtube-skills-maker/1.0 (+skill discovery; honours robots.txt)"


def _http_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_video_id(url: str) -> str | None:
    """Pull an 11-char YouTube id out of a watch or short URL."""
    if not url:
        return None
    m = YT_WATCH_RE.search(url) or YT_SHORT_RE.search(url)
    return m.group(1) if m else None


def skill_score(title: str, points: int, comments: int, duration: int | None,
                is_ai_tech: bool) -> float:
    """Heuristic: how likely is this video to yield an extractable skill?

    HackerTube ranks by community approval, which surfaces great *content* that
    teaches nothing procedural (a Mars landing, a lawsuit story). Weighted
    toward procedure-shaped titles, topical relevance and long-form depth;
    penalised for news/entertainment shapes.
    """
    score = 0.0
    if is_ai_tech:
        score += 3.0
    if SKILL_SIGNAL_RE.search(title):
        score += 4.0
    if ANTI_SKILL_RE.search(title):
        score -= 3.0
    # Community signal, log-damped so a 2000-point outlier cannot dominate.
    import math
    score += math.log1p(max(points, 0)) / 2.0
    score += math.log1p(max(comments, 0)) / 3.0
    # Long-form tutorials carry more procedure than 4-minute clips.
    if duration:
        if duration >= 1200:
            score += 2.0
        elif duration >= 600:
            score += 1.0
        elif duration < 300:
            score -= 1.0
    return round(score, 3)


def robots_permits(base: str = "https://hackertube.org", path: str = "/") -> bool:
    """True only if hackertube.org's robots.txt allows `path` for us."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(urllib.parse.urljoin(base, "/robots.txt"))
    try:
        rp.read()
    except Exception:
        # Unreachable robots.txt is not permission.
        return False
    return rp.can_fetch(_USER_AGENT, urllib.parse.urljoin(base, path))


def search_hn_youtube(
    query: str = "youtube.com/watch",
    min_points: int = 40,
    hits_per_page: int = 100,
    max_pages: int = 5,
    since: str | None = None,
) -> list[dict]:
    """HN stories whose URL is a YouTube video, best-scored first."""
    stories: list[dict] = []
    seen: set[str] = set()

    for page in range(max_pages):
        params = {
            "query": query,
            "tags": "story",
            "hitsPerPage": str(min(hits_per_page, 100)),
            "page": str(page),
            "restrictSearchableAttributes": "url",
            "numericFilters": f"points>{min_points}",
        }
        if since:
            params["numericFilters"] += f",created_at_i>{since}"
        url = f"{HN_SEARCH_URL}?{urllib.parse.urlencode(params)}"

        try:
            payload = _http_json(url)
        except Exception as exc:  # noqa: BLE001 - network variance is expected
            print(f"[HackerTube] HN page {page} failed: {exc}")
            break

        hits = payload.get("hits") or []
        if not hits:
            break

        for hit in hits:
            vid = extract_video_id(hit.get("url") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            stories.append(
                {
                    "videoId": vid,
                    "title": (hit.get("title") or "").replace(" [video]", "").strip(),
                    "hn_id": hit.get("objectID"),
                    "hn_points": hit.get("points") or 0,
                    "hn_comments": hit.get("num_comments") or 0,
                    "publishedAt": hit.get("created_at") or "",
                    "hn_author": hit.get("author") or "",
                    "link": f"https://www.youtube.com/watch?v={vid}",
                }
            )

        nb_pages = payload.get("nbPages") or 0
        if page + 1 >= nb_pages:
            break

    return stories


def _yt_dlp_metadata(video_ids: list[str], timeout: int = 180) -> dict[str, dict]:
    """Duration/channel for a batch of ids via yt-dlp (no download)."""
    if not video_ids:
        return {}
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--no-warnings",
        "--print",
        "%(id)s\t%(duration)s\t%(channel)s\t%(upload_date)s",
    ]
    for vid in video_ids:
        cmd += ["--", f"https://www.youtube.com/watch?v={vid}"]

    meta: dict[str, dict] = {}
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        for line in (out.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            vid, dur, chan = parts[0].strip(), parts[1].strip(), parts[2].strip()
            upload = parts[3].strip() if len(parts) > 3 else ""
            try:
                dur_val = int(float(dur)) if dur and dur != "NA" else None
            except ValueError:
                dur_val = None
            published = ""
            if len(upload) == 8 and upload.isdigit():
                published = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}T00:00:00Z"
            meta[vid] = {"duration": dur_val, "channelName": chan, "uploaded": published}
    except Exception as exc:  # noqa: BLE001
        print(f"[HackerTube] yt-dlp metadata failed: {exc}")
    return meta


def fetch_hackertube_videos(
    min_points: int = 10,
    limit: int = 25,
    min_duration_seconds: int = 180,
    prioritize_ai_tech: bool = True,
    exclude_child_content: bool = True,
    since: str | None = None,
    max_pages: int = 6,
    min_skill_score: float = 4.0,
    **kwargs,
) -> list[dict]:
    """
    Discover HackerTube videos and return them in feed_source record shape.

    Same contract as fetch_user_feed_videos(): a list of dicts with
    videoId, title, channelName, link, duration, publishedAt, topics,
    is_ai_tech. Adds hn_points, hn_comments, hn_id and skill_score.
    """
    # 1. Respect hackertube.org's own policy; note the outcome so runs are auditable.
    if robots_permits():
        print("[HackerTube] robots.txt permits the root path.")
    else:
        print("[HackerTube] robots.txt does not permit crawling its data paths.")
    print("[HackerTube] Discovery source: Hacker News (the corpus HackerTube is built from).")

    # 2. Pull candidates. HN indexes watch and short URLs separately.
    stories: list[dict] = []
    seen: set[str] = set()
    for query in ("youtube.com/watch", "youtu.be"):
        for s in search_hn_youtube(
            query=query, min_points=min_points, max_pages=max_pages, since=since
        ):
            if s["videoId"] in seen:
                continue
            seen.add(s["videoId"])
            stories.append(s)

    print(f"[HackerTube] HN candidates: {len(stories)} unique YouTube videos (points>{min_points}).")

    # 3. Pre-rank on title signal alone (free), then enrich only the best.
    def pre_rank(s: dict) -> float:
        topics = infer_topics(s["title"], s.get("hn_author") or "")
        return skill_score(
            s["title"], s["hn_points"], s["hn_comments"], None, bool(topics)
        )

    stories.sort(key=pre_rank, reverse=True)
    candidates = stories[: max(limit * 4, 80)]

    # 4. Enrich durations in one yt-dlp pass.
    meta = _yt_dlp_metadata([s["videoId"] for s in candidates])

    scored: list[dict] = []
    for s in candidates:
        m = meta.get(s["videoId"], {})
        duration = m.get("duration")
        channel = m.get("channelName") or s.get("hn_author") or "Unknown Channel"
        title = s["title"] or ""

        if duration is None or duration < min_duration_seconds:
            continue
        if exclude_child_content and (
            CHILD_CONTENT_REGEX.search(title) or CHILD_CONTENT_REGEX.search(channel)
        ):
            continue

        topics = infer_topics(title, channel)
        is_ai_tech = bool(topics)
        score = skill_score(title, s["hn_points"], s["hn_comments"], duration, is_ai_tech)
        if score < min_skill_score:
            continue

        scored.append(
            {
                "videoId": s["videoId"],
                "title": title,
                "channelName": channel,
                "link": s["link"],
                "duration": int(duration),
                "publishedAt": m.get("uploaded") or s["publishedAt"],
                "topics": topics,
                "is_ai_tech": is_ai_tech,
                "hn_points": s["hn_points"],
                "hn_comments": s["hn_comments"],
                "hn_id": s["hn_id"],
                "skill_score": score,
            }
        )

    scored.sort(key=lambda v: v["skill_score"], reverse=True)
    out = scored[:limit]

    ai_count = sum(1 for v in out if v.get("is_ai_tech"))
    print(
        f"[HackerTube] Selected {len(out)} of {len(scored)} skill-scored candidates "
        f"(AI/Tech: {ai_count}, metadata resolved: {len(meta)}, "
        f"threshold {min_skill_score})"
    )
    return out
