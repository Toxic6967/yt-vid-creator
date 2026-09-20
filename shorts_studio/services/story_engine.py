from __future__ import annotations

import json
import re
from typing import Any

from .ollama_client import chat_json
from .story_game import story_game_prompt_context


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
                "authentic Roblox R15 avatar with a square block head, classic simple Roblox smile face, "
                "rectangular torso, segmented block arms and legs, plastic game-avatar proportions; "
                "messy dark-brown Roblox hair accessory, royal-blue hoodie shirt texture, black cargo-style pants, white shoes; "
                "must look like an actual Roblox player avatar, never a human, clay toy, LEGO figure, Minecraft character or Pixar person"
            ),
            "personality": "confident, competitive, gets himself into trouble",
        },
        {
            "id": "mia",
            "name": "Mia",
            "gender": "female",
            "visual_identity": (
                "authentic Roblox R15 avatar with a square block head, classic simple Roblox smile face, "
                "rectangular torso, segmented block arms and legs, plastic game-avatar proportions; "
                "long dark Roblox ponytail hair accessory, purple jacket shirt texture, black pants, white shoes; "
                "must look like an actual Roblox player avatar, never a human, clay toy, LEGO figure, Minecraft character or Pixar person"
            ),
            "personality": "quick-thinking, sarcastic, notices details first",
        },
        {
            "id": "kai",
            "name": "Kai",
            "gender": "male",
            "visual_identity": (
                "authentic Roblox R15 avatar with a square block head, classic simple Roblox smile face, "
                "rectangular torso, segmented block arms and legs, plastic game-avatar proportions; "
                "short black Roblox hair accessory, red-and-black jacket shirt texture, dark pants, red shoes; "
                "must look like an actual Roblox player avatar, never a human, clay toy, LEGO figure, Minecraft character or Pixar person"
            ),
            "personality": "calm, loyal, suspicious when something feels wrong",
        },
    ]
    return dict(defaults[idx % len(defaults)])


def _normalise_characters(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    items = raw if isinstance(raw, list) else []
    canonical = {
        _default_character(i)["name"].lower(): _default_character(i)
        for i in range(3)
    }
    canonical.update({
        _default_character(i)["id"].lower(): _default_character(i)
        for i in range(3)
    })

    for idx, item in enumerate(items[:3]):
        if not isinstance(item, dict):
            continue

        requested_name = _clean(item.get("name"), 30).lower()
        requested_id = _clean(item.get("id"), 24).lower()
        known = canonical.get(requested_id) or canonical.get(requested_name)
        fallback = known or _default_character(idx)

        cid = _clean(
            fallback["id"] if known else (item.get("id") or item.get("name") or fallback["id"]),
            24,
        ).lower()
        cid = re.sub(r"[^a-z0-9_]+", "_", cid).strip("_") or fallback["id"]

        out.append(
            {
                "id": cid,
                "name": fallback["name"] if known else _clean(item.get("name") or fallback["name"], 30),
                "gender": fallback["gender"] if known else _clean(item.get("gender") or fallback["gender"], 12).lower(),
                "visual_identity": (
                    fallback["visual_identity"]
                    if known
                    else _clean(item.get("visual_identity") or fallback["visual_identity"], 320)
                ),
                "personality": (
                    fallback["personality"]
                    if known
                    else _clean(item.get("personality") or fallback["personality"], 180)
                ),
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




def _select_story_idea(
    audience: str,
    tone: str,
    game_context: dict[str, Any],
    genre: str = "auto",
) -> dict[str, Any]:
    raw = chat_json(
        "You create high-retention Roblox mini-movie concepts for Shorts. Return JSON only.",
        f"""
AUDIENCE: {audience}
CHANNEL TONE: {tone}
REQUESTED GENRE: {genre}

REAL ROBLOX GAME CONTEXT:
{story_game_prompt_context(game_context)}

Create 8 DIFFERENT mini-movie ideas that happen INSIDE this exact Roblox game.

Every idea must:
- depend on a real mechanic, objective, location, item, enemy, round rule or player situation from the game context;
- be recognisable to someone who actually plays the game;
- be understandable even if the viewer only knows the game casually;
- use the game's mechanics to create the problem and payoff.

Good story energy: unlucky timing, teammate mistake, clutch save, scary close call,
rare drop luck, greed, betrayal, panic, risky shortcut, one-player-left moment, or a funny
reversal caused by the GAME itself.

Do NOT write generic "Roblox world" stories that could happen in any game.
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
        game_name = _clean(game_context.get("game_name"), 80) or "the selected Roblox game"
        situations = game_context.get("player_situations") or []
        situation = _clean(
            (situations[0] or {}).get("situation") if situations and isinstance(situations[0], dict) else "",
            220,
        )
        premise = situation or f"A player in {game_name} makes one risky mistake right before they are about to win."
        return {
            "premise": f"Inside {game_name}, {premise}",
            "genre": genre if genre != "auto" else "relatable",
            "opening": "Start at the exact moment the run is about to go wrong.",
            "escalation": "Use a verified game mechanic to make the problem worse.",
            "payoff": "Resolve it with a game-specific clutch, reversal or funny consequence.",
        }

    judged = chat_json(
        "You are a ruthless Roblox Shorts commissioning editor. Return JSON only.",
        f"""
AUDIENCE: {audience}
GAME: {game_context.get("game_name")}
CANDIDATES:
{json.dumps(ideas, ensure_ascii=False)}

Score each 0-100 for:
- immediate_hook
- relatability_to_real_players
- visual_movie_potential
- escalation
- payoff
- originality
- game_specificity: would a real player recognise that this story belongs in THIS game?
- cringe_avoidance (100 = not cringe)

Pick the best idea for a 20-45 second cinematic Roblox Short.
Do not reward random shock value. The best idea should be simple enough to understand
instantly but strong enough to make someone stay for the ending.

Return:
{{"best_index":0,"reason":"...","scores":[{{"index":0,"hook":0,"relatability":0,"visual":0,"escalation":0,"payoff":0,"originality":0,"game_specificity":0,"cringe_avoidance":0}}]}}
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
    game_context: dict[str, Any],
) -> str:
    requested = idea.strip() if idea else "Use the selected premise supplied by the commissioning editor."
    recurring_cast = "\n".join(
        f"- {_default_character(i)['name']}: {_default_character(i)['visual_identity']}; personality: {_default_character(i)['personality']}"
        for i in range(3)
    )
    return f"""
AUDIENCE: {audience}
CHANNEL TONE: {tone}
TARGET LENGTH: {target_seconds} seconds
GENRE: {genre}
USER IDEA: {requested}

REAL GAME CONTEXT — DO NOT INVENT OUTSIDE THIS:
{story_game_prompt_context(game_context)}

RECURRING CHANNEL CAST:
{recurring_cast}

Create a short cinematic mini-movie that takes place INSIDE {game_context.get("game_name")}.
Use 1-3 characters from the recurring cast whenever possible. Keep their names, exact
hair/clothing/colours and core personalities unchanged. A one-off side character is allowed
only when the plot genuinely needs one.

The audience is real young Roblox players, not toddlers. It must feel like a situation,
fear, joke, win, loss, betrayal, grind, teammate problem, rare-item moment, horror-game
moment, server moment, obby moment or friendship moment they can recognise.

NON-NEGOTIABLE:
- Hook in the FIRST 1-2 seconds. Start inside the problem; no introduction.
- Use 7-10 short scenes. Maximum 3 characters.
- Each narration line should usually be 5-12 spoken words so the visual shot can finish before the next cut.
- Tell it like a creator recounting something that just happened in the game, not like a movie trailer.
- Keep the story mostly inside ONE continuous game session/location so the movie is visually coherent.
  Change rooms/areas only when the plot actually requires it; prefer new camera angles over teleporting worlds.
- Conflict must escalate every few seconds.
- The ending must pay off the opening: twist, funny reversal, satisfying win, scary reveal,
  or relatable punchline.
- Do not write a fake inspirational moral.
- Do not write random nonsense just because it is dramatic.
- Do not use baby talk, forced Gen-Z slang, "bro" every sentence, or corporate AI wording.
- Use ONE natural narrator voice for the whole Short, like a person telling a quick story over the action.
- Keep narration conversational and human. No announcer voice, no documentary phrasing, no fake hype.
- Characters should ACT the story visually. If a character speaks, paraphrase/quote it inside the narrator line instead of switching voices.
- Avoid long narration. Each line should sound like something a real creator would naturally say in one breath.
- Every scene must be easy to understand visually with no explanation.
- Keep violence game-like/non-graphic and appropriate for the audience.
- Characters must keep EXACTLY the same clothing/hair/colours in every scene.
- EVERY visible player character must be an authentic Roblox R15 avatar: square block head, rectangular torso,
  segmented block arms/legs and simple Roblox face. Never humanoid Pixar/clay/LEGO/Minecraft-looking people.
- Reuse the same important props and environmental details when the story returns to a location.
- Use at least TWO real game-specific mechanics/locations/items from the verified game context.
- Never invent a fake item, enemy, currency, room, objective or UI element.

Return JSON exactly:
{{
  "title":"working story title",
  "game_name":"{game_context.get('game_name')}",
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
      "speaker":"narrator",
      "narration":"ONE short natural narrator line",
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


def _normalise_story(
    raw: dict,
    target_seconds: int,
    game_context: dict[str, Any],
) -> dict:
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

        game_name = _clean(raw.get("game_name") or game_context.get("game_name"), 80)
        environment = _clean(item.get("environment"), 180) or f"recognisable {game_name} Roblox gameplay area"
        action = _clean(item.get("action"), 220) or _clean(item.get("narration"), 220)
        camera = _clean(item.get("camera"), 60) or "medium"
        emotion = _clean(item.get("emotion"), 80)

        keyframe_prompt = (
            f"AUTHENTIC ROBLOX GAMEPLAY MOVIE FRAME from the real Roblox experience {game_name}. "
            "Use Roblox R15 player-avatar geometry: square block heads, simple Roblox faces, rectangular torsos, "
            "segmented block arms and legs, plastic Roblox game proportions. Absolutely NOT realistic humans, "
            "Pixar people, clay toys, LEGO minifigures, Minecraft/voxel people or generic cartoon children. "
            f"Characters: {'; '.join(identities)}. Recognisable in-game environment: {environment}. "
            f"Action frozen at the clearest dramatic moment: {action}. Camera: {camera}. Emotion: {emotion}. "
            "Modern Roblox game lighting, crisp 3D gameplay screenshot feel, cinematic depth, vertical composition. "
            "Frame characters around the middle/lower-middle and leave the top 12 percent as clean environment only. "
            "No words, no letters, no numbers, no captions, no signs, no fake game title, no logo, no watermark, "
            "no UI text, no extra limbs, no duplicated characters. Keep exact avatar clothing, hair and colours."
        )
        motion_prompt = (
            f"Inside {game_name} Roblox gameplay: {action}. Camera movement: {camera}. "
            "Keep authentic Roblox R15 square-head/block-limb geometry throughout the entire shot. "
            "Keep the exact same characters, clothing, hair, simple Roblox faces and environment. "
            f"Emotion: {emotion}. Natural Roblox game-animation body motion, cinematic timing, "
            "no morphing, no human anatomy, no outfit changes, no words or UI text appearing."
        )

        spoken_line = _clean(item.get("narration"), 240)
        if not spoken_line:
            continue

        speaker = "narrator"

        scenes.append(
            {
                "role": role,
                "speaker": speaker,
                "narration": spoken_line,
                "characters": visible_ids,
                "character_visuals": identities,
                "game_name": game_name,
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
        "game_name": _clean(raw.get("game_name") or game_context.get("game_name"), 80),
        "game_context": {
            "core_loop": game_context.get("core_loop"),
            "mechanics": game_context.get("mechanics", []),
            "locations": game_context.get("locations", []),
            "player_situations": game_context.get("player_situations", []),
        },
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
    narrator_lines = sum(
        1 for scene in scenes
        if str(scene.get("speaker") or "narrator").lower() == "narrator"
    )
    max_words = max(scene_word_counts, default=0)
    total_words = len(re.findall(r"\b[\w'-]+\b", narration))
    expected_min = max(42, round(target_seconds * 1.7))
    expected_max = min(120, round(target_seconds * 2.8))
    banned_hits = [phrase for phrase in BANNED_STORY_PATTERNS if phrase in lower]

    return {
        "scene_count_ok": 7 <= len(scenes) <= 11,
        "short_lines_ok": max_words <= 13,
        "word_count_ok": expected_min <= total_words <= expected_max,
        "single_narrator_ok": narrator_lines == len(scenes),
        "banned_phrase_ok": not banned_hits,
        "banned_hits": banned_hits,
        "max_scene_words": max_words,
        "word_count": total_words,
        "expected_word_range": [expected_min, expected_max],
        "narrator_line_count": narrator_lines,
    }

def _score_story(
    story: dict,
    audience: str,
    target_seconds: int,
    game_context: dict[str, Any],
) -> dict[str, Any]:
    mechanical = _deterministic_story_checks(story, target_seconds)
    result = chat_json(
        "You are a ruthless short-form story editor for a successful Roblox channel. Return JSON only.",
        f"""
AUDIENCE: {audience}
REAL GAME CONTEXT:
{story_game_prompt_context(game_context)}

STORY:
{json.dumps(story, ensure_ascii=False)}

Score 0-100:
- hook: does the first 1-2 seconds make someone stay?
- relatability: would Roblox players recognise the situation/emotion?
- escalation: does something meaningfully change/get worse or better every few seconds?
- payoff: does the ending reward watching?
- dialogue: does the ONE narrator sound conversational and human rather than like an AI/documentary announcer?
- movie_clarity: can every beat be understood visually?
- character_consistency: are characters simple and reusable across shots?
- game_specificity: does this clearly happen inside the named game using real mechanics, rather than generic Roblox?
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
  "game_specificity":0,
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
        "game_specificity",
        "cringe_avoidance",
    )
    scores = {k: max(0, min(100, int(float(result.get(k, 0) or 0)))) for k in keys}
    total = round(
        scores["hook"] * 0.16
        + scores["relatability"] * 0.16
        + scores["escalation"] * 0.11
        + scores["payoff"] * 0.14
        + scores["dialogue"] * 0.10
        + scores["movie_clarity"] * 0.09
        + scores["character_consistency"] * 0.05
        + scores["game_specificity"] * 0.12
        + scores["cringe_avoidance"] * 0.07,
        1,
    )
    problems = list(result.get("problems") or [])
    rewrite_instructions = list(result.get("rewrite_instructions") or [])
    if not mechanical["short_lines_ok"]:
        problems.append(f"Some spoken beats are too long ({mechanical['max_scene_words']} words).")
        rewrite_instructions.append("Keep every spoken beat at 13 words or fewer; most should be 5-12 words.")
    if not mechanical["single_narrator_ok"]:
        problems.append("Story switches speakers even though this format uses one consistent narrator.")
        rewrite_instructions.append("Use narrator as the speaker for every beat; let characters act visually.")
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
        and scores["game_specificity"] >= 82
        and scores["cringe_avoidance"] >= 85
        and all(
            mechanical[key]
            for key in (
                "scene_count_ok",
                "short_lines_ok",
                "word_count_ok",
                "single_narrator_ok",
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
    game_context: dict[str, Any],
    genre: str = "auto",
) -> dict:
    selected_idea = None
    if not idea:
        selected_idea = _select_story_idea(audience, tone, game_context, genre)
        idea = (
            f"Premise: {selected_idea.get('premise','')}. "
            f"Opening: {selected_idea.get('opening','')}. "
            f"Escalation: {selected_idea.get('escalation','')}. "
            f"Payoff: {selected_idea.get('payoff','')}."
        )
        genre = str(selected_idea.get("genre") or genre)

    draft = chat_json(
        "You are a sharp Roblox mini-movie writer/director. You write for young players without writing down to them. Return JSON only.",
        _story_prompt(idea, audience, tone, target_seconds, genre, game_context),
        temperature=0.62,
    )
    story = _normalise_story(draft, target_seconds, game_context)
    if selected_idea:
        story["idea_selection"] = selected_idea

    for _ in range(2):
        score = _score_story(story, audience, target_seconds, game_context)
        if score["passed"]:
            story["story_score"] = score
            return story

        rewritten = chat_json(
            "You are rewriting a Roblox mini-movie that failed a strict audience-retention review. Return JSON only.",
            f"""
AUDIENCE: {audience}
TARGET: {target_seconds} seconds
REAL GAME CONTEXT:
{story_game_prompt_context(game_context)}

CURRENT STORY:
{json.dumps(story, ensure_ascii=False)}

EDITOR SCORE:
{json.dumps(score, ensure_ascii=False)}

Rewrite the WHOLE story.
Preserve useful character identities, but fix the exact problems.
Start inside the conflict. Make it more recognisable to players of {game_context.get("game_name")}.
The problem and payoff must depend on real mechanics from the supplied game context.
Do not make it louder/randomer just to increase excitement.
No fake moral, no forced slang, no babyish wording.
Return the exact same story JSON shape.
""",
            temperature=0.48,
        )
        retained_idea = story.get("idea_selection")
        story = _normalise_story(rewritten, target_seconds, game_context)
        if retained_idea:
            story["idea_selection"] = retained_idea

    story["story_score"] = _score_story(story, audience, target_seconds, game_context)
    return story
