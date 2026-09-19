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




def _select_story_idea(audience: str, tone: str) -> dict[str, Any]:
    raw = chat_json(
        "You create high-retention Roblox mini-movie concepts for Shorts. Return JSON only.",
        f"""
AUDIENCE: {audience}
CHANNEL TONE: {tone}

Create 8 DIFFERENT Roblox mini-movie ideas aimed at this audience.

Base them on recognisable Roblox-player feelings/situations, such as:
- entering a horror game with a friend and getting separated
- grinding for a rare item while someone else gets lucky instantly
- being underestimated as the noob
- a teammate betraying the group at the worst time
- lag/disconnect ruining an almost-win
- joining a strange empty server
- one player being left alive in a survival round
- an obby shortcut that seems too good to be true
- spending Robux and immediately regretting it
- a friend saying "one more game"

Do NOT copy these literally every time. Use them as the level of relatability.
Avoid fake inspirational morals, random lore dumps, generic "evil hacker" stories,
death/tragedy bait, and plots that only work because characters act stupid.

For each idea return:
- premise: one sentence
- genre
- opening: what happens in the first 1-2 seconds
- escalation: what makes it worse/more interesting
- payoff: the ending/twist/punchline

Return {{"ideas":[{{"premise":"...","genre":"...","opening":"...","escalation":"...","payoff":"..."}}]}}
""",
        temperature=0.72,
    )
    ideas = raw.get("ideas") if isinstance(raw.get("ideas"), list) else []
    ideas = [item for item in ideas if isinstance(item, dict)][:8]
    if not ideas:
        return {
            "premise": "Two friends enter a Roblox horror game and one vanishes just before the exit opens.",
            "genre": "horror",
            "opening": "The exit opens, but only one player's name is still in the server list.",
            "escalation": "The missing friend keeps triggering doors from rooms they supposedly left.",
            "payoff": "The survivor reaches the exit and sees the friend waiting outside, asking why they took so long.",
        }

    judged = chat_json(
        "You are a ruthless Roblox Shorts commissioning editor. Return JSON only.",
        f"""
AUDIENCE: {audience}
CANDIDATES:
{json.dumps(ideas, ensure_ascii=False)}

Score each 0-100 for:
- immediate_hook
- relatability_to_real_players
- visual_movie_potential
- escalation
- payoff
- originality
- cringe_avoidance (100 = not cringe)

Pick the best idea for a 20-45 second cinematic Roblox Short.
Do not reward random shock value. The best idea should be simple enough to understand
instantly but strong enough to make someone stay for the ending.

Return:
{{"best_index":0,"reason":"...","scores":[{{"index":0,"hook":0,"relatability":0,"visual":0,"escalation":0,"payoff":0,"originality":0,"cringe_avoidance":0}}]}}
""",
        temperature=0.16,
    )
    try:
        index = int(judged.get("best_index", 0))
    except Exception:
        index = 0
    index = max(0, min(index, len(ideas) - 1))
    selected = dict(ideas[index])
    selected["selection_reason"] = _clean(judged.get("reason"), 240)
    selected["candidate_scores"] = judged.get("scores") or []
    return selected

def _story_prompt(
    idea: str | None,
    audience: str,
    tone: str,
    target_seconds: int,
    genre: str,
) -> str:
    requested = idea.strip() if idea else "Use the selected premise supplied by the commissioning editor."
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
- Keep the story mostly inside ONE continuous game session/location so the movie is visually coherent.
  Change rooms/areas only when the plot actually requires it; prefer new camera angles over teleporting worlds.
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
- Reuse the same important props and environmental details when the story returns to a location.

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

        spoken_line = _clean(item.get("narration"), 240)
        if not spoken_line:
            continue

        raw_speaker = _clean(item.get("speaker") or "narrator", 30).lower()
        if raw_speaker == "narrator":
            speaker = "narrator"
        else:
            speaker_character = cmap.get(raw_speaker)
            speaker = speaker_character["id"] if speaker_character else raw_speaker

        scenes.append(
            {
                "role": role,
                "speaker": speaker,
                "narration": spoken_line,
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




def _deterministic_story_checks(story: dict, target_seconds: int) -> dict[str, Any]:
    scenes = story.get("scenes") or []
    narration = str(story.get("narration") or "")
    lower = narration.lower()
    scene_word_counts = [
        len(re.findall(r"\b[\w'-]+\b", str(scene.get("narration") or "")))
        for scene in scenes
    ]
    spoken_character_lines = sum(
        1 for scene in scenes
        if str(scene.get("speaker") or "narrator").lower() != "narrator"
    )
    max_words = max(scene_word_counts, default=0)
    total_words = len(re.findall(r"\b[\w'-]+\b", narration))
    expected_min = max(42, round(target_seconds * 1.7))
    expected_max = min(120, round(target_seconds * 2.8))
    banned_hits = [phrase for phrase in BANNED_STORY_PATTERNS if phrase in lower]

    return {
        "scene_count_ok": 6 <= len(scenes) <= 13,
        "short_lines_ok": max_words <= 18,
        "word_count_ok": expected_min <= total_words <= expected_max,
        "dialogue_ratio_ok": spoken_character_lines >= max(2, len(scenes) // 3),
        "banned_phrase_ok": not banned_hits,
        "banned_hits": banned_hits,
        "max_scene_words": max_words,
        "word_count": total_words,
        "expected_word_range": [expected_min, expected_max],
        "character_line_count": spoken_character_lines,
    }

def _score_story(story: dict, audience: str, target_seconds: int) -> dict[str, Any]:
    mechanical = _deterministic_story_checks(story, target_seconds)
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
    problems = list(result.get("problems") or [])
    rewrite_instructions = list(result.get("rewrite_instructions") or [])
    if not mechanical["short_lines_ok"]:
        problems.append(f"Some spoken beats are too long ({mechanical['max_scene_words']} words).")
        rewrite_instructions.append("Keep every spoken beat at 18 words or fewer.")
    if not mechanical["dialogue_ratio_ok"]:
        problems.append("Too much narrator exposition and not enough character dialogue.")
        rewrite_instructions.append("Move more of the story into short character dialogue and visible action.")
    if not mechanical["word_count_ok"]:
        problems.append(
            f"Spoken word count {mechanical['word_count']} is outside the target range "
            f"{mechanical['expected_word_range'][0]}-{mechanical['expected_word_range'][1]}."
        )
        rewrite_instructions.append("Adjust spoken length to fit the requested runtime without filler.")
    if mechanical["banned_hits"]:
        problems.append("Banned cringe/filler phrasing: " + ", ".join(mechanical["banned_hits"]))
        rewrite_instructions.append("Remove canned creator phrases, forced morals and generic AI filler.")

    passed = (
        total >= 82
        and scores["hook"] >= 84
        and scores["relatability"] >= 80
        and scores["payoff"] >= 80
        and scores["cringe_avoidance"] >= 85
        and all(
            mechanical[key]
            for key in (
                "scene_count_ok",
                "short_lines_ok",
                "word_count_ok",
                "dialogue_ratio_ok",
                "banned_phrase_ok",
            )
        )
    )
    return {
        "scores": scores,
        "mechanical": mechanical,
        "total": total,
        "problems": problems,
        "rewrite_instructions": rewrite_instructions,
        "passed": passed,
    }


def create_story(
    idea: str | None,
    *,
    audience: str,
    tone: str,
    target_seconds: int,
    genre: str = "auto",
) -> dict:
    selected_idea = None
    if not idea:
        selected_idea = _select_story_idea(audience, tone)
        idea = (
            f"Premise: {selected_idea.get('premise','')}. "
            f"Opening: {selected_idea.get('opening','')}. "
            f"Escalation: {selected_idea.get('escalation','')}. "
            f"Payoff: {selected_idea.get('payoff','')}."
        )
        genre = str(selected_idea.get("genre") or genre)

    draft = chat_json(
        "You are a sharp Roblox mini-movie writer/director. You write for young players without writing down to them. Return JSON only.",
        _story_prompt(idea, audience, tone, target_seconds, genre),
        temperature=0.62,
    )
    story = _normalise_story(draft, target_seconds)
    if selected_idea:
        story["idea_selection"] = selected_idea

    for _ in range(2):
        score = _score_story(story, audience, target_seconds)
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
        retained_idea = story.get("idea_selection")
        story = _normalise_story(rewritten, target_seconds)
        if retained_idea:
            story["idea_selection"] = retained_idea

    story["story_score"] = _score_story(story, audience, target_seconds)
    return story
