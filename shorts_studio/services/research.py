from __future__ import annotations

import concurrent.futures
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from ..config import settings
from .ollama_client import chat_json


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _clean(text: object, limit: int = 600) -> str:
    """Normalize occasionally messy LLM/search values into safe display text."""
    if text is None:
        value = ""
    elif isinstance(text, str):
        value = text
    elif isinstance(text, (list, tuple, set)):
        value = " ".join(_clean(item, limit) for item in text if item is not None)
    elif isinstance(text, dict):
        # Prefer common text-bearing fields before falling back to values.
        preferred = (
            text.get("text")
            or text.get("title")
            or text.get("name")
            or text.get("value")
        )
        if preferred is not None:
            value = _clean(preferred, limit)
        else:
            value = " ".join(
                _clean(item, limit)
                for item in text.values()
                if item is not None
            )
    else:
        value = str(text)

    return re.sub(r"\s+", " ", value).strip()[:limit]


def _safe_search(query: str, max_results: int = 12) -> list[dict]:
    try:
        results = DDGS(timeout=8).text(query, max_results=max_results)
        return list(results or [])
    except Exception:
        return []


def discover_topic(
    niche: str,
    requested_topic: str | None = None,
    requested_content_type: str = "auto",
) -> dict:
    if requested_topic:
        return {
            "topic": requested_topic,
            "content_type": requested_content_type if requested_content_type != "auto" else "trend",
            "reason": "Topic was supplied manually.",
            "candidates": [],
        }

    if "roblox" in niche.lower():
        try:
            from .topic_radar import pick_best_roblox_topic
            return pick_best_roblox_topic()
        except Exception:
            pass

    year = datetime.now(timezone.utc).year
    raw = []
    for query in (
        f"{niche} latest {year}",
        f"{niche} new discovery interesting fact {year}",
        f"{niche} explained news",
    ):
        raw.extend(_safe_search(query, 10))

    seen = set()
    candidates = []
    for rank, item in enumerate(raw):
        title = _clean(item.get("title", ""), 160)
        href = item.get("href") or item.get("url") or ""
        if not title or not href:
            continue
        key = re.sub(r"\W+", "", title.lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        hook_terms = sum(
            1 for word in ("new", "first", "why", "how", "found", "reveals", "discovery", "secret", "record")
            if word in title.lower()
        )
        score = max(0.0, 100 - rank * 1.8) + hook_terms * 4
        candidates.append(
            {
                "title": title,
                "url": href,
                "domain": _domain(href),
                "snippet": _clean(item.get("body", ""), 260),
                "score": round(score, 1),
            }
        )
        if len(candidates) >= 18:
            break

    if not candidates:
        selection = chat_json(
            "You are an editor for high-quality educational YouTube Shorts. Return JSON only.",
            f"Propose one evergreen, specific, verifiable Short topic inside this niche: {niche!r}. "
            "Return {\"topic\": string, \"reason\": string}. Avoid generic listicles and sensational claims.",
        )
        return {"topic": selection["topic"], "reason": selection.get("reason", ""), "candidates": []}

    selection = chat_json(
        "You are the commissioning editor for an original, fact-based YouTube Shorts channel. Return JSON only.",
        "Choose exactly one candidate that can become a genuinely useful 20-45 second Short. "
        "Prefer a specific idea with verifiable facts and a natural visual story. Avoid tragedy exploitation, "
        "celebrity gossip, vague listicles, and claims that depend on only one weak source.\n\n"
        f"NICHE: {niche}\nCANDIDATES:\n" + "\n".join(
            f"[{i}] score={c['score']} | {c['title']} | {c['domain']} | {c['snippet']}"
            for i, c in enumerate(candidates[:12], start=1)
        ) + "\n\nReturn {\"candidate_index\": integer, \"topic\": string, \"reason\": string}.",
    )
    idx = int(selection.get("candidate_index", 1)) - 1
    idx = max(0, min(idx, len(candidates) - 1))
    topic = _clean(selection.get("topic") or candidates[idx]["title"], 180)
    return {"topic": topic, "reason": selection.get("reason", ""), "candidates": candidates[:12]}


def _fetch_page(url: str) -> str:
    try:
        headers = {"User-Agent": settings.user_agent}
        with httpx.Client(timeout=9, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        text = " ".join(p.get_text(" ", strip=True) for p in soup.find_all(["p", "li"]))
        return _clean(text, settings.max_source_chars)
    except Exception:
        return ""


def research_topic(topic: str) -> dict:
    results = []
    for query in (topic, f"{topic} facts explained", f"{topic} source"):
        results.extend(_safe_search(query, 8))

    unique = []
    seen_urls = set()
    seen_domains = set()
    for item in results:
        url = item.get("href") or item.get("url") or ""
        if not url or url in seen_urls:
            continue
        domain = _domain(url)
        if not domain:
            continue
        if domain in seen_domains and len(unique) < 5:
            continue
        seen_urls.add(url)
        seen_domains.add(domain)
        unique.append(
            {
                "title": _clean(item.get("title", ""), 180),
                "url": url,
                "domain": domain,
                "snippet": _clean(item.get("body", ""), 600),
            }
        )
        if len(unique) >= 8:
            break

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        bodies = list(executor.map(lambda x: _fetch_page(x["url"]), unique[:6]))
    for item, body in zip(unique[:6], bodies):
        item["excerpt"] = body or item["snippet"]
    for item in unique[6:]:
        item["excerpt"] = item["snippet"]

    evidence_score = min(100, int(25 * math.log2(max(1, len(unique)) + 1) + 10 * len(seen_domains)))
    return {
        "topic": topic,
        "sources": unique,
        "evidence_score": evidence_score,
        "source_domains": sorted(seen_domains),
    }


def write_fact_checked_script(
    topic: str,
    niche: str,
    research: dict,
    target_seconds: int,
    *,
    audience: str = "General Roblox audience",
    tone: str = "Fast gaming documentary",
) -> dict:
    sources = research.get("sources", [])
    if len(sources) < 2:
        raise RuntimeError("Not enough independent source material was found to make a fact-checked Short.")

    source_text = "\n\n".join(
        f"SOURCE {i}\nTITLE: {s['title']}\nURL: {s['url']}\nEXCERPT: {s['excerpt']}"
        for i, s in enumerate(sources, start=1)
    )
    target_words = max(58, min(108, round(target_seconds * 2.45)))
    prompt = f"""
NICHE: {niche}
AUDIENCE: {audience}
TONE: {tone}
TOPIC: {topic}
TARGET LENGTH: {target_seconds} seconds, about {target_words} spoken words.

SOURCE PACK:
{source_text}

Create an original Short using only claims supported by the source pack. Do not copy source wording.
Every factual scene must cite one or more SOURCE numbers. If a claim is uncertain, omit it.

Use 9-14 SHORT beats so the visual can change roughly every 1.5-3.5 seconds.
The opening line must be a strong truthful hook of roughly 4-18 spoken words.
Write for the stated audience: energetic, clear and easy to follow, but never babyish or patronizing.
Every beat must add new information or change what the viewer understands.
End with a payoff that resolves the hook.
No "hey guys", "today we're", "in this video", "you won't believe", fake urgency, or generic AI filler.

Return JSON exactly:
{{
  "topic": "...",
  "hook": "...",
  "scenes": [
    {{
      "role":"hook|setup|build|reveal|payoff",
      "narration":"short natural spoken beat",
      "visual_query":"specific thing the viewer should SEE in this beat",
      "on_screen_emphasis":"1-5 punchy words",
      "source_ids":[1,2],
      "edit_instruction":"short edit direction",
      "pattern_interrupt":"optional visual interruption",
      "sfx_cue":"optional subtle sound cue"
    }}
  ],
  "claims": [{{"claim":"...", "source_ids":[1,2], "confidence":"high|medium"}}],
  "warnings": []
}}
"""
    draft = chat_json(
        "You are a meticulous high-retention YouTube Shorts writer. Accuracy and natural spoken language matter. Return JSON only.",
        prompt,
        temperature=0.45,
    )

    script = chat_json(
        "You are a skeptical fact-check editor. Return corrected JSON only.",
        "Audit the draft against the supplied source pack. Remove or rewrite every factual claim that is not clearly supported. "
        "Do not add new facts. Preserve the hook/setup/build/reveal/payoff structure, short pacing and visual/edit fields. "
        "Each factual scene must list the SOURCE numbers that support it.\n\n"
        f"SOURCE PACK:\n{source_text}\n\nDRAFT JSON:\n{draft}",
        temperature=0.15,
    )
    return _clean_script(script, topic, require_sources=True)


def write_relatable_script(
    topic: str,
    niche: str,
    target_seconds: int,
    *,
    audience: str,
    tone: str,
) -> dict:
    target_words = max(55, min(105, round(target_seconds * 2.35)))
    prompt = f"""
NICHE: {niche}
AUDIENCE: {audience}
TONE: {tone}
RELATABLE IDEA: {topic}
TARGET: {target_seconds} seconds, about {target_words} spoken words.

Write a highly relatable Roblox Short based on a familiar player situation.

This is NOT a news explainer.
Do not invent statistics, dates, update claims, developer quotes, or pretend the scenario happens to literally every player.

STYLE:
- 8-13 fast beats.
- Hook should instantly recreate the painful/funny situation.
- Use "when...", "POV...", "you finally...", short reactions and escalating beats when natural.
- The viewer should recognise the feeling within the first 2 seconds.
- Escalate the scenario, then give a funny/satisfying payoff.
- Natural Roblox-player wording, but do not force slang every sentence.
- Energetic for young players, not babyish.
- Each beat needs a concrete scene that could be shown visually.
- Keep narration concise enough for a human-sounding voiceover.
- No generic "like and subscribe" ending.

Return JSON exactly:
{{
  "topic":"...",
  "hook":"...",
  "scenes":[
    {{
      "role":"hook|setup|build|reveal|payoff",
      "narration":"...",
      "visual_query":"exact Roblox-inspired situation to show",
      "on_screen_emphasis":"1-5 words",
      "source_ids":[],
      "edit_instruction":"short edit direction",
      "pattern_interrupt":"optional visual interruption",
      "sfx_cue":"optional subtle sound cue"
    }}
  ],
  "claims":[],
  "warnings":[]
}}
"""
    script = chat_json(
        "You write genuinely relatable, fast Roblox Shorts for young players. Do not sound like corporate marketing or generic AI. Return JSON only.",
        prompt,
        temperature=0.58,
    )
    return _clean_script(script, topic, require_sources=False)


def _clean_script(script: dict, topic: str, *, require_sources: bool) -> dict:
    scenes = script.get("scenes") or []
    if not scenes:
        raise RuntimeError("The local model did not produce any script scenes.")

    allowed_roles = {"hook", "setup", "build", "reveal", "payoff"}
    for idx, scene in enumerate(scenes):
        role = _clean(scene.get("role", ""), 20).lower()
        if role not in allowed_roles:
            if idx == 0:
                role = "hook"
            elif idx == len(scenes) - 1:
                role = "payoff"
            elif idx <= 2:
                role = "setup"
            elif idx >= len(scenes) - 3:
                role = "reveal"
            else:
                role = "build"

        scene["role"] = role
        scene["narration"] = _clean(scene.get("narration", ""), 420)
        scene["visual_query"] = _clean(scene.get("visual_query", topic), 180)
        scene["on_screen_emphasis"] = _clean(scene.get("on_screen_emphasis", ""), 70)
        scene["source_ids"] = [int(x) for x in scene.get("source_ids", []) if str(x).isdigit()]
        scene["edit_instruction"] = _clean(scene.get("edit_instruction", "hard cut + subtle push-in"), 120)
        scene["pattern_interrupt"] = _clean(scene.get("pattern_interrupt", ""), 100)
        scene["sfx_cue"] = _clean(scene.get("sfx_cue", ""), 80)

        if not scene["narration"]:
            raise RuntimeError("A generated scene had no narration.")
        if require_sources and not scene["source_ids"]:
            script.setdefault("warnings", []).append("A factual scene has no explicit source citation.")

    if scenes:
        scenes[0]["role"] = "hook"
        scenes[-1]["role"] = "payoff"

    full_text = " ".join(scene["narration"] for scene in scenes)
    script["hook"] = scenes[0]["narration"] if scenes else _clean(script.get("hook", ""), 240)
    script["word_count"] = len(re.findall(r"\b[\w'-]+\b", full_text))
    script["narration"] = full_text
    script["scenes"] = scenes
    return script


def create_metadata(topic: str, script: dict) -> dict:
    result = chat_json(
        "You are a YouTube metadata editor. Be specific, readable, and non-spammy. Return JSON only.",
        f"TOPIC: {topic}\nSCRIPT: {script.get('narration','')}\n"
        "Return {\"title\": string under 70 chars, \"description\": string under 350 chars, "
        "\"hashtags\": [3 to 5 short hashtags without spaces]}. Avoid misleading clickbait.",
        temperature=0.35,
    )
    hashtags = []
    for tag in result.get("hashtags", []):
        tag = str(tag).strip().replace(" ", "")
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        hashtags.append(tag[:40])
    return {
        "title": _clean(result.get("title", topic), 70),
        "description": _clean(result.get("description", ""), 350),
        "hashtags": hashtags[:5],
    }
