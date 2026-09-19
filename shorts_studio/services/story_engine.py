from __future__ import annotations

import json
import re
from typing import Any

from .ollama_client import chat_json


BANNED_STORY_PATTERNS = (
    "then everyone clapped",
    "and learned a lesson",
    "the power of friendship",
    "like and subscribe",
    "smash that like",
    "you won't believe",
    "hey guys",
    "today we're",
)


def _clean(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(x) for x in value)
    elif isinstance(value, dict):
        value = " ".join(str(x) for x in value.values())
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def _default_character(idx: int) -> dict[str, str]:
    defaults = [
        {
            "id": "max",
            "name": "Max",
            "gender": "male",
            "visual_identity": (
                "blocky Roblox-style teen avatar, messy dark-brown hair, royal-blue hoodie, "
                "black cargo pants, white sneakers, expressive square face"
            ),
            "personality": "confident, competitive, gets himself into trouble",
        },
        {
            "id": "mia",
            "name": "Mia",
            "gender": "female",
            "visual_identity": (
                "blocky Roblox-style teen avatar, long dark hair in a high ponytail, purple jacket, "
                "black jeans, white shoes, expressive square face"
            ),
            "personality": "quick-thinking, sarcastic, notices details first",
        },
        {
            "id": "kai",
            "name": "Kai",
            "gender": "male",
            "visual_identity": (
                "blocky Roblox-style teen avatar, short black hair, red-and-black jacket, "
                "dark pants, red sneakers, expressive square face"
            ),
            "personality": "calm, loyal, suspicious when something feels wrong",
        },
    ]
    return dict(defaults[idx % len(defaults)])


def _normalise_characters(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    items = raw if isinstance(raw, list) else []
    for idx, item in enumerate(items[:3]):
        if not isinstance(item, dict):
            continue
        fallback = _default_character(idx)
        cid = _clean(item.get("id") or item.get("name") or fallback["id"], 24).lower()
        cid = re.sub(r"[^a-z0-9_]+", "_", cid).strip("_") or fallback["id"]
        out.append(
            {
                "id": cid,
                "name": _clean(item.get("name") or fallback["name"], 30),
                "gender": _clean(item.get("gender") or fallback["gender"], 12).lower(),
                "visual_identity": _clean(
                    item.get("visual_identity") or fallback["visual_identity"], 320
                ),
                "personality": _clean(item.get("personality") or fallback["personality"], 180),
                "voice_profile": (
                    ("character-female-" + str(1 + sum(1 for c in out if c.get("gender") == "female")))
                    if _clean(item.get("gender") or fallback["gender"], 12).lower() == "female"
                    else ("character-male-" + str(1 + sum(1 for c in out if c.get("gender") == "male")))
                ),
            }
        )
    while len(out) < 2:
        fallback = _default_character(len(out))
        fallback["voice_profile"] = "character-female-1" if fallback["gender"] == "female" else f"character-male-{1 + sum(1 for c in out if c.get('gender') == 'male')}"
        out.append(fallback)
    return out


def _character_map(characters: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {}
    for character in characters:
        result[character["id"].lower()] = character
        result[character["name"].lower()] = character
    return result


def _story_prompt(
    idea: str | None,
    audience: str,
    tone: str,
    target_seconds: int,
    genre: str,
) -> str:
    requested = idea.strip() if idea else "Invent the strongest relatable Roblox mini-movie idea yourself."
    return f"""
AUDIENCE: {audience}
CHANNEL TONE: {tone}
TARGET LENGTH: {target_seconds} seconds
GENRE: {genre}
USER IDEA: {requested}

Create a short cinematic Roblox mini-movie for YouTube Shorts.

The audience is real young Roblox players, not toddlers. It must feel like a situation,
fear, joke, win, loss, betrayal, grind, teammate problem, rare-item moment, horror-game
moment, server moment, obby moment or friendship moment they can recognise.

NON-NEGOTIABLE:
- Hook in the FIRST 1-2 seconds. Start inside the problem; no introduction.
- One simple story. Maximum 3 characters.
- Conflict must escalate every few seconds.
- The ending must pay off the opening: twist, funny reversal, satisfying win, scary reveal,
  or relatable punchline.
- Do not write a fake inspirational moral.
- Do not write random nonsense just because it is dramatic.
- Do not use baby talk, forced Gen-Z slang, "bro" every sentence, or corporate AI wording.
- Dialogue should sound like actual players talking while gaming.
- Avoid long narration. Prefer characters acting and speaking.
- Every scene must be easy to understand visually with no explanation.
- Keep violence game-like/non-graphic and appropriate for the audience.
- Characters must keep EXACTLY the same clothing/hair/colours in every scene.

Return JSON exactly:
{{
  "title":"working story title",
  "genre":"funny|horror|mystery|action|relatable|sad",
  "premise":"one sentence",
  "hook":"first spoken line",
  "characters":[
    {{
      "id":"short id",
      "name":"...",
      "gender":"male|female",
      "visual_identity":"VERY specific unchanging avatar description including hair, top, bottoms, shoes and colours",
      "personality":"..."
    }}
  ],
  "scenes":[
    {{
      "role":"hook|setup|build|reveal|payoff",
      "speaker":"narrator or character id",
      "narration":"ONE short spoken line",
      "characters":["character ids visible in shot"],
      "environment":"specific Roblox-style game location",
      "action":"what physically happens during this shot",
      "camera":"wide|medium|close-up|over-shoulder|follow|low-angle|high-angle",
      "emotion":"...",
      "on_screen_emphasis":"0-4 words only",
      "sfx_cue":"optional",
      "motion_priority":"high|medium|low"
    }}
  ]
}}
"""


def _normalise_story(raw: dict, target_seconds: int) -> dict:
    characters = _normalise_characters(raw.get("characters"))
    cmap = _character_map(characters)

    scenes_raw = raw.get("scenes") if isinstance(raw.get("scenes"), list) else []
    scenes: list[dict[str, Any]] = []

    for idx, item in enumerate(scenes_raw[:13]):
        if not isinstance(item, dict):
            continue
        role = _clean(item.get("role"), 20).lower()
        if role not in {"hook", "setup", "build", "reveal", "payoff"}:
            role = "build"

        visible_ids: list[str] = []
        raw_visible = item.get("characters")
        if isinstance(raw_visible, list):
            for value in raw_visible:
                key = _clean(value, 30).lower()
                character = cmap.get(key)
                if character and character["id"] not in visible_ids:
                    visible_ids.append(character["id"])

        if not visible_ids and characters:
            visible_ids = [characters[min(idx, len(characters) - 1)]["id"]]

        identities = [
            next(c["visual_identity"] for c in characters if c["id"] == cid)
            for cid in visible_ids
        ]

        environment = _clean(item.get("environment"), 180) or "cinematic Roblox-style game environment"
        action = _clean(item.get("action"), 220) or _clean(item.get("narration"), 220)
        camera = _clean(item.get("camera"), 60) or "medium"
        emotion = _clean(item.get("emotion"), 80)

        keyframe_prompt = (
            "cinematic Roblox-style 3D movie frame, polished modern lighting, strong depth, "
            "clean blocky avatars, high-detail game environment, vertical composition. "
            f"Characters: {'; '.join(identities)}. Environment: {environment}. "
            f"Action frozen at the clearest dramatic moment: {action}. Camera: {camera}. "
            f"Emotion: {emotion}. Keep exact character clothing, hair and colours. "
            "No text, no logo, no watermark, no extra limbs, no duplicated characters."
        )
        motion_prompt = (
            f"{action}. Camera movement: {camera}. Keep the same characters, clothing, hair, "
            f"face design and environment throughout the shot. Emotion: {emotion}. "
            "Natural game-character body motion, cinematic timing, no morphing, no outfit changes."
        )

        scenes.append(
            {
                "role": role,
                "speaker": _clean(item.get("speaker") or "narrator", 30).lower(),
                "narration": _clean(item.get("narration"), 240),
                "characters": visible_ids,
                "character_visuals": identities,
                "environment": environment,
                "action": action,
                "camera": camera,
                "emotion": emotion,
                "visual_query": keyframe_prompt,
                "keyframe_prompt": keyframe_prompt,
                "motion_prompt": motion_prompt,
                "on_screen_emphasis": _clean(item.get("on_screen_emphasis"), 40),
                "source_ids": [],
                "edit_instruction": f"{camera} cinematic cut",
                "pattern_interrupt": "",
                "sfx_cue": _clean(item.get("sfx_cue"), 60),
                "motion_priority": _clean(item.get("motion_priority") or "medium", 12).lower(),
            }
        )

    if len(scenes) < 6:
        raise RuntimeError("Story writer did not create enough usable movie scenes.")

    scenes[0]["role"] = "hook"
    scenes[-1]["role"] = "payoff"

    narration = " ".join(s["narration"] for s in scenes if s["narration"])
    return {
        "topic": _clean(raw.get("title") or raw.get("premise") or "Roblox Story", 120),
        "title": _clean(raw.get("title") or "Roblox Story", 100),
        "genre": _clean(raw.get("genre") or "relatable", 24).lower(),
        "premise": _clean(raw.get("premise"), 240),
        "hook": scenes[0]["narration"],
        "characters": characters,
        "scenes": scenes,
        "claims": [],
        "warnings": [],
        "narration": narration,
        "word_count": len(re.findall(r"\b[\w'-]+\b", narration)),
        "target_seconds": target_seconds,
    }


def _score_story(story: dict, audience: str) -> dict[str, Any]:
    result = chat_json(
        "You are a ruthless short-form story editor for a successful Roblox channel. Return JSON only.",
        f"""
AUDIENCE: {audience}
STORY:
{json.dumps(story, ensure_ascii=False)}

Score 0-100:
- hook: does the first 1-2 seconds make someone stay?
- relatability: would Roblox players recognise the situation/emotion?
- escalation: does something meaningfully change/get worse or better every few seconds?
- payoff: does the ending reward watching?
- dialogue: does it sound like actual players rather than an AI script?
- movie_clarity: can every beat be understood visually?
- character_consistency: are characters simple and reusable across shots?
- cringe_avoidance: 100 means not cringe, not babyish, no forced slang, no fake moral.

Also list exact problems and exact rewrite instructions.

Return:
{{
  "hook":0,
  "relatability":0,
  "escalation":0,
  "payoff":0,
  "dialogue":0,
  "movie_clarity":0,
  "character_consistency":0,
  "cringe_avoidance":0,
  "problems":[],
  "rewrite_instructions":[]
}}
""",
        temperature=0.18,
    )
    keys = (
        "hook",
        "relatability",
        "escalation",
        "payoff",
        "dialogue",
        "movie_clarity",
        "character_consistency",
        "cringe_avoidance",
    )
    scores = {k: max(0, min(100, int(float(result.get(k, 0) or 0)))) for k in keys}
    total = round(
        scores["hook"] * 0.18
        + scores["relatability"] * 0.18
        + scores["escalation"] * 0.14
        + scores["payoff"] * 0.16
        + scores["dialogue"] * 0.10
        + scores["movie_clarity"] * 0.10
        + scores["character_consistency"] * 0.06
        + scores["cringe_avoidance"] * 0.08,
        1,
    )
    return {
        "scores": scores,
        "total": total,
        "problems": result.get("problems") or [],
        "rewrite_instructions": result.get("rewrite_instructions") or [],
        "passed": (
            total >= 82
            and scores["hook"] >= 84
            and scores["relatability"] >= 80
            and scores["payoff"] >= 80
            and scores["cringe_avoidance"] >= 85
        ),
    }


def create_story(
    idea: str | None,
    *,
    audience: str,
    tone: str,
    target_seconds: int,
    genre: str = "auto",
) -> dict:
    draft = chat_json(
        "You are a sharp Roblox mini-movie writer/director. You write for young players without writing down to them. Return JSON only.",
        _story_prompt(idea, audience, tone, target_seconds, genre),
        temperature=0.62,
    )
    story = _normalise_story(draft, target_seconds)

    for _ in range(2):
        score = _score_story(story, audience)
        if score["passed"]:
            story["story_score"] = score
            return story

        rewritten = chat_json(
            "You are rewriting a Roblox mini-movie that failed a strict audience-retention review. Return JSON only.",
            f"""
AUDIENCE: {audience}
TARGET: {target_seconds} seconds

CURRENT STORY:
{json.dumps(story, ensure_ascii=False)}

EDITOR SCORE:
{json.dumps(score, ensure_ascii=False)}

Rewrite the WHOLE story.
Preserve useful character identities, but fix the exact problems.
Start inside the conflict. Make it more recognisable to Roblox players.
Do not make it louder/randomer just to increase excitement.
No fake moral, no forced slang, no babyish wording.
Return the exact same story JSON shape.
""",
            temperature=0.48,
        )
        story = _normalise_story(rewritten, target_seconds)

    story["story_score"] = _score_story(story, audience)
    return story
