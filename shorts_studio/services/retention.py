from __future__ import annotations

import json
import re
from typing import Any

from .ollama_client import chat_json

FILLER_OPENERS = (
    "hey guys",
    "hey everyone",
    "today we're",
    "today we are",
    "in this video",
    "welcome back",
    "did you know",
)

REQUIRED_ROLES = ("hook", "setup", "build", "reveal", "payoff")


def _clean(text: str, limit: int = 600) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _source_pack(research: dict) -> str:
    return "\n\n".join(
        f"SOURCE {i}\nTITLE: {s.get('title','')}\nURL: {s.get('url','')}\nEXCERPT: {s.get('excerpt') or s.get('snippet','')}"
        for i, s in enumerate(research.get("sources", []), start=1)
    )


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def deterministic_checks(
    script: dict,
    target_seconds: int,
    *,
    require_citations: bool = True,
) -> dict[str, Any]:
    scenes = script.get("scenes") or []
    narration = " ".join(_clean(s.get("narration", ""), 500) for s in scenes)
    first = _clean((scenes[0].get("narration") if scenes else "") or script.get("hook", ""), 300)
    last = _clean(scenes[-1].get("narration", "") if scenes else "", 300)
    first_lower = first.lower()

    roles = [str(s.get("role", "")).lower().strip() for s in scenes]
    duplicate_lines = 0
    seen = set()
    for scene in scenes:
        normalized = re.sub(r"\W+", " ", str(scene.get("narration", "")).lower()).strip()
        if normalized and normalized in seen:
            duplicate_lines += 1
        seen.add(normalized)

    word_count = _word_count(narration)
    target_words = round(target_seconds * 2.45)
    pace_delta = abs(word_count - target_words)
    max_scene_words = max((_word_count(s.get("narration", "")) for s in scenes), default=0)

    return {
        "scene_count": len(scenes),
        "scene_count_ok": 9 <= len(scenes) <= 14,
        "hook_present": bool(first),
        "hook_words": _word_count(first),
        "hook_length_ok": 4 <= _word_count(first) <= 18,
        "hook_has_filler": any(first_lower.startswith(x) for x in FILLER_OPENERS),
        "roles_present": sorted({r for r in roles if r}),
        "roles_ok": all(role in roles for role in REQUIRED_ROLES),
        "duplicate_scene_lines": duplicate_lines,
        "no_duplicate_scene_lines": duplicate_lines == 0,
        "word_count": word_count,
        "target_words": target_words,
        "word_count_ok": pace_delta <= max(18, int(target_words * 0.24)),
        "max_scene_words": max_scene_words,
        "short_beats_ok": max_scene_words <= 18,
        "payoff_present": bool(last) and roles[-1:] == ["payoff"],
        "citations_ok": (
            all(bool(s.get("source_ids")) for s in scenes)
            if require_citations
            else True
        ),
        "visual_queries_ok": all(bool(_clean(s.get("visual_query", ""))) for s in scenes),
    }


def _normalize_script(script: dict, topic: str) -> dict:
    scenes = script.get("scenes") or []
    cleaned = []
    allowed_roles = {"hook", "setup", "build", "reveal", "payoff"}
    for idx, scene in enumerate(scenes):
        role = str(scene.get("role", "")).lower().strip()
        if role not in allowed_roles:
            if idx == 0:
                role = "hook"
            elif idx == len(scenes) - 1:
                role = "payoff"
            elif idx <= 2:
                role = "setup"
            elif idx >= max(1, len(scenes) - 3):
                role = "reveal"
            else:
                role = "build"

        cleaned.append(
            {
                "role": role,
                "narration": _clean(scene.get("narration", ""), 420),
                "visual_query": _clean(scene.get("visual_query", topic), 140),
                "on_screen_emphasis": _clean(scene.get("on_screen_emphasis", ""), 70),
                "source_ids": [
                    int(x) for x in scene.get("source_ids", []) if str(x).isdigit()
                ],
                "edit_instruction": _clean(
                    scene.get("edit_instruction", "hard cut, subtle push-in"), 120
                ),
                "pattern_interrupt": _clean(scene.get("pattern_interrupt", ""), 100),
                "sfx_cue": _clean(scene.get("sfx_cue", ""), 80),
            }
        )

    script["scenes"] = cleaned
    script["hook"] = cleaned[0]["narration"] if cleaned else _clean(script.get("hook", ""), 300)
    script["narration"] = " ".join(s["narration"] for s in cleaned)
    script["word_count"] = _word_count(script["narration"])
    return script


def _score_script(
    script: dict,
    topic: str,
    niche: str,
    target_seconds: int,
    *,
    audience: str,
    tone: str,
    content_type: str,
    require_citations: bool,
) -> dict[str, Any]:
    checks = deterministic_checks(
        script,
        target_seconds,
        require_citations=require_citations,
    )
    rubric = chat_json(
        "You are a strict YouTube Shorts retention editor. Score the script, do not flatter it. Return JSON only.",
        f"""
CHANNEL NICHE: {niche}
AUDIENCE: {audience}
CHANNEL TONE: {tone}
CONTENT TYPE: {content_type}
TOPIC: {topic}
TARGET LENGTH: {target_seconds} seconds

SCRIPT:
{json.dumps(script, ensure_ascii=False)}

MECHANICAL CHECKS:
{json.dumps(checks, ensure_ascii=False)}

Score each category from 0-100:
- hook: first 1-2 seconds stop the scroll without lying
- curiosity: each beat creates a reason to hear the next beat
- progression: every beat adds new information and avoids repetition
- payoff: ending resolves the promise made by the hook
- naturalness: sounds like a real Roblox creator talking to the stated audience, not generic AI prose
- relatability: the viewer can quickly recognise why the situation/topic matters to them
- visual_pacing: scene plan creates frequent meaningful visual changes
- clarity: easy to follow at Shorts speed

Be especially harsh on generic openers, fake urgency, repeated information, weak endings, long sentences, or scenes that do not advance the story.

Return:
{{
  "hook": 0,
  "curiosity": 0,
  "progression": 0,
  "payoff": 0,
  "naturalness": 0,
  "relatability": 0,
  "visual_pacing": 0,
  "clarity": 0,
  "issues": ["specific issue"],
  "rewrite_instructions": ["specific fix"]
}}
""",
        temperature=0.12,
    )

    scores = {}
    for key in ("hook", "curiosity", "progression", "payoff", "naturalness", "relatability", "visual_pacing", "clarity"):
        try:
            scores[key] = max(0.0, min(100.0, float(rubric.get(key, 0))))
        except Exception:
            scores[key] = 0.0

    weighted = (
        scores["hook"] * 0.20
        + scores["curiosity"] * 0.14
        + scores["progression"] * 0.14
        + scores["payoff"] * 0.14
        + scores["naturalness"] * 0.10
        + scores["relatability"] * 0.12
        + scores["visual_pacing"] * 0.10
        + scores["clarity"] * 0.06
    )

    mechanical_penalty = 0.0
    if checks["hook_has_filler"]:
        mechanical_penalty += 15
    if not checks["hook_length_ok"]:
        mechanical_penalty += 8
    if not checks["scene_count_ok"]:
        mechanical_penalty += 8
    if not checks["roles_ok"]:
        mechanical_penalty += 8
    if not checks["payoff_present"]:
        mechanical_penalty += 10
    if not checks["short_beats_ok"]:
        mechanical_penalty += 6
    if not checks["no_duplicate_scene_lines"]:
        mechanical_penalty += 10
    if require_citations and not checks["citations_ok"]:
        mechanical_penalty += 8

    total = max(0.0, min(100.0, weighted - mechanical_penalty))
    passed = (
        total >= 80
        and scores["hook"] >= 80
        and scores["progression"] >= 75
        and scores["payoff"] >= 75
        and scores["visual_pacing"] >= 72
        and checks["scene_count_ok"]
        and checks["hook_length_ok"]
        and not checks["hook_has_filler"]
        and checks["payoff_present"]
        and checks["citations_ok"]
        and scores["relatability"] >= (78 if content_type == "relatable" else 62)
    )

    return {
        "total": round(total, 1),
        "passed": passed,
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "checks": checks,
        "issues": [str(x)[:240] for x in rubric.get("issues", [])][:8],
        "rewrite_instructions": [str(x)[:260] for x in rubric.get("rewrite_instructions", [])][:8],
    }


def _rewrite_script(
    script: dict,
    score: dict,
    topic: str,
    niche: str,
    research: dict,
    target_seconds: int,
    *,
    audience: str,
    tone: str,
    content_type: str,
    require_citations: bool,
) -> dict:
    sources = _source_pack(research)
    target_words = max(58, min(110, round(target_seconds * 2.45)))

    rewritten = chat_json(
        "You are a senior YouTube Shorts writer/editor. Rewrite for retention while preserving factual accuracy. Return JSON only.",
        f"""
NICHE: {niche}
AUDIENCE: {audience}
TONE: {tone}
CONTENT TYPE: {content_type}
TOPIC: {topic}
TARGET: about {target_words} spoken words in {target_seconds} seconds.

SOURCE PACK:
{sources}

CURRENT SCRIPT:
{json.dumps(script, ensure_ascii=False)}

RETENTION REVIEW:
{json.dumps(score, ensure_ascii=False)}

Rewrite the entire Short.

NON-NEGOTIABLE STRUCTURE:
- 9-14 short scenes, usually about 1.5-3.5 seconds each.
- Scene 1 role=hook. It must immediately present the most interesting truthful tension/fact. 4-18 spoken words.
- Then setup -> build -> build -> reveal -> payoff. More than one build/reveal scene is allowed.
- Every scene must add information or meaningfully change the viewer's understanding.
- The final scene role=payoff and must answer/resolve the hook. Do not end with generic engagement begging.
- No "hey guys", "today we're", "in this video", "you won't believe", fake urgency, or unsupported superlatives.
- Use short spoken sentences that sound natural aloud.
- If CONTENT TYPE is relatable, keep it as a familiar scenario and do not invent specific factual claims, statistics, dates or quotes.
- If CONTENT TYPE is factual/trend, use ONLY factual claims supported by the source pack.
- Factual scenes must include valid SOURCE numbers when citations are required.
- on_screen_emphasis must be 1-5 punchy words, not the full narration.
- visual_query must describe what should visibly appear for that exact beat.
- edit_instruction should be a short editing direction such as "hard cut + fast push-in", "quick crop change", "UI highlight", or "wide-to-close zoom".
- pattern_interrupt should be used only when useful: e.g. "flash stat", "map pop", "screenshot punch-in", "caption scale hit". Empty is allowed.
- sfx_cue should be subtle and optional: e.g. "soft whoosh", "click", "impact". Empty is allowed.

Return exactly:
{{
  "topic": "...",
  "hook": "...",
  "scenes": [
    {{
      "role": "hook|setup|build|reveal|payoff",
      "narration": "...",
      "visual_query": "...",
      "on_screen_emphasis": "...",
      "source_ids": [1,2],
      "edit_instruction": "...",
      "pattern_interrupt": "...",
      "sfx_cue": "..."
    }}
  ],
  "claims": [{{"claim":"...", "source_ids":[1,2], "confidence":"high|medium"}}],
  "warnings": []
}}
""",
        temperature=0.38,
    )
    return _normalize_script(rewritten, topic)


def _final_fact_check(
    script: dict,
    topic: str,
    research: dict,
    *,
    content_type: str,
) -> dict:
    sources = _source_pack(research)
    if content_type == "relatable":
        checked = chat_json(
            "You are the final safety and naturalness editor for a relatable Roblox Short. Return corrected JSON only.",
            f"""
TOPIC: {topic}
SCRIPT:
{json.dumps(script, ensure_ascii=False)}

This is a relatable/POV scenario, not a factual news report.
- Keep the scenario plausible and recognisable.
- Remove invented statistics, dates, developer claims, quotes, or claims that literally every Roblox player does something.
- Keep the hook, escalation, payoff, short scenes and visual/edit fields.
- Keep source_ids empty unless the script genuinely contains a sourced factual statement.
Return the corrected script in the same JSON shape.
""",
            temperature=0.08,
        )
    else:
        checked = chat_json(
            "You are the final factual safety editor for a YouTube Short. Return corrected JSON only.",
            f"""
TOPIC: {topic}

SOURCE PACK:
{sources}

SCRIPT:
{json.dumps(script, ensure_ascii=False)}

Check every factual statement against the source pack.
- Remove or cautiously rewrite anything not supported.
- Never invent a fact to improve the hook.
- Keep the same retention structure, role fields, edit fields and approximate scene count.
- Preserve source_ids only when they actually support the scene.
- Do not make the script flatter or more generic unless accuracy requires it.
Return the corrected script in the same JSON shape.
""",
            temperature=0.08,
        )
    return _normalize_script(checked, topic)


def optimize_retention(
    script: dict,
    topic: str,
    niche: str,
    research: dict,
    target_seconds: int,
    *,
    audience: str,
    tone: str,
    content_type: str = "trend",
    require_citations: bool = True,
    max_rewrites: int = 2,
) -> dict:
    current = _normalize_script(script, topic)
    attempts = []

    for attempt in range(max_rewrites + 1):
        score = _score_script(
            current,
            topic,
            niche,
            target_seconds,
            audience=audience,
            tone=tone,
            content_type=content_type,
            require_citations=require_citations,
        )
        attempts.append({"attempt": attempt + 1, **score})
        if score["passed"] or attempt >= max_rewrites:
            break
        current = _rewrite_script(
            current,
            score,
            topic,
            niche,
            research,
            target_seconds,
            audience=audience,
            tone=tone,
            content_type=content_type,
            require_citations=require_citations,
        )

    current = _final_fact_check(
        current,
        topic,
        research,
        content_type=content_type,
    )
    final_score = _score_script(
        current,
        topic,
        niche,
        target_seconds,
        audience=audience,
        tone=tone,
        content_type=content_type,
        require_citations=require_citations,
    )

    current["retention"] = {
        "passed": final_score["passed"],
        "total": final_score["total"],
        "scores": final_score["scores"],
        "checks": final_score["checks"],
        "issues": final_score["issues"],
        "attempts": attempts,
        "rewrite_count": max(0, len(attempts) - 1),
    }
    return current
