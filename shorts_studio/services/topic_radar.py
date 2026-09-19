from __future__ import annotations

import math
import re
import statistics
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from ddgs import DDGS
from yt_dlp import YoutubeDL

from ..db import (
    finish_radar_run,
    get_channel_profile,
    get_recent_generated_topics,
    list_topics,
    replace_topics,
)
from .ollama_client import chat_json


def _clean(value: Any, limit: int = 220) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _youtube_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 12,
        "retries": 1,
        "extract_flat": False,
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearchdate{limit}:{query}", download=False)
    except Exception:
        return []

    now = datetime.now(timezone.utc)
    output = []
    for entry in (info or {}).get("entries") or []:
        if not entry:
            continue
        timestamp = entry.get("timestamp")
        age_days = None
        if timestamp:
            try:
                published = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                age_days = max(0.0, (now - published).total_seconds() / 86400)
            except Exception:
                pass
        output.append(
            {
                "title": _clean(entry.get("title"), 180),
                "url": entry.get("webpage_url") or entry.get("original_url") or "",
                "channel": _clean(entry.get("channel") or entry.get("uploader"), 90),
                "views": int(entry.get("view_count") or 0),
                "duration": int(entry.get("duration") or 0),
                "age_days": age_days,
            }
        )
    return output


def _web_search(query: str, limit: int = 8) -> list[dict[str, str]]:
    try:
        results = DDGS(timeout=8).text(query, max_results=limit)
    except Exception:
        return []
    return [
        {
            "title": _clean(x.get("title"), 180),
            "url": x.get("href") or x.get("url") or "",
            "snippet": _clean(x.get("body"), 300),
        }
        for x in (results or [])
        if x.get("title")
    ]


def _youtube_score(videos: list[dict[str, Any]]) -> float:
    views = sorted((v["views"] for v in videos if v.get("views", 0) > 0), reverse=True)[:5]
    if not views:
        return 30.0
    median = statistics.median(views)
    # About 1k observed views ~= 50, 100k ~= 83, 1m+ ~= 100.
    return round(max(0.0, min(100.0, 16.67 * math.log10(max(1.0, median)))), 1)


def _recency_score(videos: list[dict[str, Any]]) -> float:
    ages = [float(v["age_days"]) for v in videos if v.get("age_days") is not None][:8]
    if not ages:
        return 45.0
    freshest = min(ages)
    recent_share = sum(1 for age in ages if age <= 14) / len(ages)
    score = max(0.0, 100.0 - min(freshest, 60.0) * 1.25)
    score = score * 0.65 + recent_share * 100 * 0.35
    return round(score, 1)


def _duplicate_risk(title: str, old_topics: list[str]) -> float:
    if not old_topics:
        return 0.0
    normalized = title.lower()
    return round(
        max(SequenceMatcher(None, normalized, old.lower()).ratio() for old in old_topics) * 100,
        1,
    )


def _discover_subjects(profile: dict[str, Any]) -> list[str]:
    pool = []
    for query in ("Roblox", "Roblox update", "Roblox new game", "Roblox trending"):
        pool.extend(_youtube_search(query, 8))
    seen = set()
    lines = []
    for item in sorted(pool, key=lambda x: x.get("views", 0), reverse=True):
        key = item["title"].lower()
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(f"- {item['title']} | observed_views={item['views']} | age_days={item['age_days']}")
        if len(lines) >= 28:
            break

    web = _web_search("Roblox trending games updates", 12)
    web_lines = "\n".join(f"- {x['title']} | {x['snippet']}" for x in web[:10])
    prompt = (
        "Find 8 distinct Roblox subjects worth investigating for a Shorts channel. Subjects can be games, updates, "
        "features, records, controversies only when well sourced, or fast-rising Roblox trends. Do not invent names. "
        "Prefer specific subjects visible in the evidence. Return JSON: {\"subjects\":[\"...\"]}.\n\n"
        f"CHANNEL NICHE: {profile['niche']}\n\nYOUTUBE SEARCH EVIDENCE:\n" + "\n".join(lines) +
        "\n\nWEB EVIDENCE:\n" + web_lines
    )
    try:
        result = chat_json(
            "You are a Roblox trend researcher. Treat the supplied search results as evidence, not absolute global rankings. Return JSON only.",
            prompt,
            temperature=0.25,
        )
        subjects = [_clean(x, 90) for x in result.get("subjects", []) if _clean(x, 90)]
    except Exception:
        subjects = []

    fallbacks = ["Roblox updates", "Blox Fruits", "Brookhaven", "Roblox RIVALS", "Dress to Impress", "Roblox new games"]
    for item in fallbacks:
        if item.lower() not in {x.lower() for x in subjects}:
            subjects.append(item)
        if len(subjects) >= 8:
            break
    return subjects[:8]


def _discover_relatable_ideas(profile: dict[str, Any]) -> list[str]:
    pool = []
    for query in (
        "Roblox relatable moments",
        "Roblox POV relatable",
        "Roblox things every player does",
        "Roblox funny player moments",
    ):
        pool.extend(_youtube_search(query, 8))

    lines = []
    seen = set()
    for item in sorted(pool, key=lambda x: x.get("views", 0), reverse=True):
        title = item.get("title", "")
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        lines.append(
            f"- {title} | observed_views={item.get('views', 0)} | age_days={item.get('age_days')}"
        )
        if len(lines) >= 24:
            break

    prompt = f"""
AUDIENCE: {profile.get('audience', 'young Roblox players')}
CHANNEL: {profile.get('niche', 'Roblox')}

RECENT RELATABLE ROBLOX VIDEO TITLES:
{chr(10).join(lines)}

Propose 4 specific, highly relatable Roblox Short scenarios.

The idea should make a Roblox player think "that literally happens to me".
Prefer universal platform/gameplay situations over obscure game-specific lore:
lag at the worst moment, disconnects, grinding for one item, rare-drop pain,
friends saying one more game, joining too late, getting targeted, spending Robux,
inventory mistakes, server chaos, finally winning after repeated losses, etc.

Do not copy the titles above. Do not make factual claims or pretend literally every
Roblox player has experienced it. Keep each idea short and visual.

Return {{"ideas":["...","...","...","..."]}}.
"""
    try:
        result = chat_json(
            "You are a Roblox Shorts ideation editor for a young gaming audience. Return JSON only.",
            prompt,
            temperature=0.5,
        )
        ideas = [_clean(x, 110) for x in result.get("ideas", []) if _clean(x, 110)]
    except Exception:
        ideas = []

    fallbacks = [
        "When lag hits exactly as you are about to win",
        "Grinding forever for a rare item and your friend gets it first try",
        "Your friend says one more game and suddenly it is an hour later",
        "Joining the server right after the event you wanted ends",
    ]
    for item in fallbacks:
        if item.lower() not in {x.lower() for x in ideas}:
            ideas.append(item)
        if len(ideas) >= 4:
            break
    return ideas[:4]


def scan_roblox_topics(profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    profile = profile or get_channel_profile()
    old_topics = get_recent_generated_topics()
    subjects = _discover_subjects(profile)[:6]
    relatable_ideas = _discover_relatable_ideas(profile)
    raw = []

    for subject in subjects:
        videos = _youtube_search(f"Roblox {subject}", 8)
        web = _web_search(f"Roblox {subject} update news", 6)
        yt_score = _youtube_score(videos)
        recency = _recency_score(videos)
        raw.append(
            {
                "subject": subject,
                "content_type": "trend",
                "youtube_score": yt_score,
                "recency_score": recency,
                "videos": videos[:6],
                "web": web[:5],
                "evidence_score": min(100.0, len(videos) * 8 + len(web) * 7),
            }
        )

    for idea in relatable_ideas:
        videos = _youtube_search(f"Roblox relatable {idea}", 8)
        raw.append(
            {
                "subject": idea,
                "content_type": "relatable",
                "youtube_score": _youtube_score(videos),
                "recency_score": _recency_score(videos),
                "videos": videos[:6],
                "web": [],
                "evidence_score": min(100.0, len(videos) * 10),
            }
        )

    evidence_lines = []
    for i, item in enumerate(raw, start=1):
        top_titles = "; ".join(v["title"] for v in item["videos"][:3])
        evidence_lines.append(
            f"[{i}] type={item['content_type']} | {item['subject']} | youtube={item['youtube_score']} "
            f"| recency={item['recency_score']} | evidence={item['evidence_score']} | examples={top_titles}"
        )

    try:
        judged = chat_json(
            "You are an editor scoring Roblox Short ideas. Do not claim the evidence proves a global ranking. Return JSON only.",
            "For every numbered idea, score curiosity, channel_fit and relatability from 0-100, then propose one specific Short title "
            "and a one-sentence reason. For type=trend, stay factual and researchable. For type=relatable, make it a recognisable POV/scenario "
            "for young Roblox players and do NOT turn it into a fake news claim. Avoid babyish wording.\n"
            f"AUDIENCE: {profile.get('audience','young Roblox players')}\nCHANNEL: {profile['niche']}\nEVIDENCE:\n" + "\n".join(evidence_lines) +
            "\nReturn {\"items\":[{\"index\":1,\"title\":\"...\",\"reason\":\"...\","
            "\"curiosity\":85,\"channel_fit\":95,\"relatability\":90}]}",
            temperature=0.25,
        )
        judgments = {int(x.get("index", 0)): x for x in judged.get("items", [])}
    except Exception:
        judgments = {}

    topics = []
    for idx, item in enumerate(raw, start=1):
        judge = judgments.get(idx, {})
        title = _clean(judge.get("title") or f"Why {item['subject']} is trending on Roblox", 180)
        curiosity = float(judge.get("curiosity") or 70)
        channel_fit = float(judge.get("channel_fit") or 90)
        relatability = float(judge.get("relatability") or (88 if item["content_type"] == "relatable" else 60))
        dup = _duplicate_risk(title, old_topics)
        if item["content_type"] == "relatable":
            overall = (
                item["youtube_score"] * 0.22 +
                item["recency_score"] * 0.08 +
                curiosity * 0.20 +
                channel_fit * 0.16 +
                relatability * 0.28 +
                item["evidence_score"] * 0.06 -
                dup * 0.20
            )
        else:
            overall = (
                item["youtube_score"] * 0.36 +
                item["recency_score"] * 0.20 +
                curiosity * 0.17 +
                channel_fit * 0.12 +
                relatability * 0.07 +
                item["evidence_score"] * 0.08 -
                dup * 0.22
            )
        topics.append(
            {
                "id": uuid.uuid4().hex[:12],
                "title": title,
                "subject": item["subject"],
                "reason": _clean(judge.get("reason") or "Strong recent Roblox search activity with usable research evidence.", 280),
                "score": round(max(0.0, min(100.0, overall)), 1),
                "youtube_score": item["youtube_score"],
                "recency_score": item["recency_score"],
                "curiosity_score": round(curiosity, 1),
                "channel_fit_score": round(channel_fit, 1),
                "duplicate_risk": dup,
                "evidence": {
                    "content_type": item["content_type"],
                    "relatability_score": round(relatability, 1),
                    "youtube_samples": item["videos"],
                    "web_sources": item["web"],
                    "note": (
                        "Relatable ideas are scenario concepts, not factual claims about every player."
                        if item["content_type"] == "relatable"
                        else "Scores use observed recent public search metadata and are not a claim of total YouTube-wide views."
                    ),
                },
            }
        )
    return sorted(topics, key=lambda x: x["score"], reverse=True)


def run_radar_job(run_id: str) -> None:
    try:
        topics = scan_roblox_topics()
        replace_topics(run_id, topics)
        finish_radar_run(run_id, "finished")
    except Exception as exc:
        finish_radar_run(run_id, "failed", str(exc))


def pick_best_roblox_topic() -> dict[str, Any]:
    cached = list_topics(1)
    if cached:
        best = cached[0]
    else:
        results = scan_roblox_topics()
        if not results:
            raise RuntimeError("Roblox Trend Radar could not find a usable topic.")
        best = results[0]
    return {
        "topic": best["title"],
        "content_type": (best.get("evidence") or {}).get("content_type", "trend"),
        "reason": f"Roblox Trend Radar score {best['score']}/100. {best['reason']}",
        "candidates": [best],
    }
