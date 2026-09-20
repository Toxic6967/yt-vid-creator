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
                "authentic Roblox R15 player avatar with classic Roblox proportions, softly beveled plastic head, "
                "simple classic Roblox face decal, R15 torso, separate upper/lower arms and legs with visible Roblox joints; "
                "messy dark-brown Roblox catalog hair accessory, royal-blue hoodie clothing texture, black cargo-style pants, white shoes; "
                "recognizably Roblox, not voxel/cubic Minecraft, not LEGO, not a human child and not a Pixar character"
            ),
            "personality": "confident, competitive, gets himself into trouble",
        },
        {
            "id": "mia",
            "name": "Mia",
            "gender": "female",
            "visual_identity": (
                "authentic Roblox R15 player avatar with classic Roblox proportions, softly beveled plastic head, "
                "simple classic Roblox face decal, R15 torso, separate upper/lower arms and legs with visible Roblox joints; "
                "long dark Roblox ponytail catalog hair accessory, purple jacket clothing texture, black pants, white shoes; "
                "recognizably Roblox, not voxel/cubic Minecraft, not LEGO, not a human child and not a Pixar character"
            ),
            "personality": "quick-thinking, sarcastic, notices details first",
        },
        {
            "id": "kai",
            "name": "Kai",
            "gender": "male",
            "visual_identity": (
                "authentic Roblox R15 player avatar with classic Roblox proportions, softly beveled plastic head, "
                "simple classic Roblox face decal, R15 torso, separate upper/lower arms and legs with visible Roblox joints; "
                "short black Roblox catalog hair accessory, red-and-black jacket clothing texture, dark pants, red shoes; "
                "recognizably Roblox, not voxel/cubic Minecraft, not LEGO, not a human child and not a Pixar character"
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

Pick the best idea for a 45-70 second cinematic Roblox mini-movie.
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
- Use 10-14 purposeful scenes. Maximum 3 characters.
- Each narration line should usually be 6-14 spoken words. The longer runtime is for MORE STORY, not filler.
- Build a real cause-and-effect story arc:
  1) HOOK: show the immediate problem or strange situation.
  2) GOAL: make it obvious what the player is trying to do.
  3) FIRST OBSTACLE: a real game mechanic makes the goal harder.
  4) FAILED ATTEMPT / COST: something goes wrong because of a choice or mechanic.
  5) ESCALATION: the situation becomes harder, riskier, funnier or scarier.
  6) TURN: the player notices/tries something that changes the direction of the story.
  7) CLIMAX: one decisive game action resolves the central problem.
  8) PAYOFF: directly answer the hook with a satisfying result, reversal or punchline.
- Every scene must CAUSE or ENABLE the next important beat. If a scene can be removed without changing the story, remove it.
- Tell it like a creator recounting something that just happened in the game, not like a movie trailer.
- Keep it inside ONE continuous game session, but the VIDEO must visibly progress.
- Use at least 4 visually different rooms, areas, obstacles, set-pieces or background compositions from the same game when the verified context allows it.
- The background must look like a polished ROBLOX GAME ENVIRONMENT: Roblox Studio-style materials, simple readable geometry, stylized game lighting and game-scale props. Never make a photoreal real-world movie set or a Minecraft voxel map.
- Never leave two adjacent scenes with the same environment AND the same camera framing. Each cut must reveal new visual information.
- Conflict must escalate every few seconds.
- Establish one clear central goal and keep it alive through the whole Short.
- Do not introduce random new villains, secret weapons, portals, powers, rare items or lore unless the verified game context supports them AND they matter to the original goal.
- No coincidence may solve the climax. The ending must come from a character decision, skill, mistake or verified game mechanic established earlier.
- The ending must pay off the opening: twist, funny reversal, satisfying win, scary reveal,
  or relatable punchline.
- Do not write a fake inspirational moral.
- Do not write random nonsense just because it is dramatic.
- Do not use baby talk, forced Gen-Z slang, "bro" every sentence, or corporate AI wording.
- Use ONE natural narrator voice for the whole Short, like a real creator casually telling friends what happened.
- The narration must read smoothly as ONE continuous paragraph when all scene lines are joined together.
- Use contractions and ordinary spoken English. Vary sentence length. Let some lines flow into the next instead of sounding like eight separate announcements.
- Do NOT repeatedly start lines with "I", "Then", "And then", "So", "But then", "Suddenly", or "That's when".
- Do NOT use trailer/documentary phrases like "little did I know", "everything changed", "what happened next", "I couldn't believe it", or fake hype.
- Characters ACT the story visually. If a character speaks, paraphrase or briefly quote it inside the narrator's continuous story.
- Avoid long narration. Each line should sound natural when spoken aloud and should connect cleanly to the lines around it.
- Every scene must be easy to understand visually with no explanation.
- Keep violence game-like/non-graphic and appropriate for the audience.
- Characters must keep EXACTLY the same clothing/hair/colours in every scene.
- EVERY visible player character must look unmistakably like a Roblox R15 avatar: classic Roblox body proportions,
  beveled plastic head, classic Roblox face decal, R15 torso and visibly separated upper/lower limb parts.
  Never use voxel/Minecraft cube anatomy, pixel faces, LEGO/minifigure proportions, realistic human anatomy,
  Pixar/cartoon children, fingers, noses or realistic mouths.
- Reuse the same important props and environmental details when the story returns to a location.
- Use at least TWO real game-specific mechanics/locations/items from the verified game context.
- Never invent a fake item, enemy, currency, room, objective or UI element.

Return JSON exactly:
{{
  "title":"working story title",
  "game_name":"{game_context.get('game_name')}",
  "genre":"funny|horror|mystery|action|relatable|sad",
  "premise":"one sentence",
  "story_goal":"the one clear thing the player wants during this story",
  "stakes":"what they lose/fail/miss if the goal goes wrong",
  "turning_point":"the decision, discovery or game mechanic that changes the direction of the story",
  "payoff":"how the climax directly resolves the hook and central goal",
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
      "environment":"specific verified in-game area/background for THIS shot; avoid repeating the previous shot",
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

    for idx, item in enumerate(scenes_raw[:16]):
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
        allowed_cameras = ("wide", "medium", "close-up", "over-shoulder", "follow", "low-angle", "high-angle")
        if camera not in allowed_cameras:
            camera = allowed_cameras[idx % len(allowed_cameras)]
        if scenes and camera == str(scenes[-1].get("camera") or ""):
            camera = allowed_cameras[(allowed_cameras.index(camera) + 2 + idx) % len(allowed_cameras)]
        emotion = _clean(item.get("emotion"), 80)

        keyframe_prompt = (
            f"FRAME FROM A ROBLOX R15 GAMEPLAY MINI-MOVIE set inside the real Roblox experience {game_name}. "
            "The players must have unmistakable modern Roblox R15 avatar anatomy: softly beveled plastic head, "
            "classic Roblox face decal, R15 torso, separate upper/lower arms and legs with visible Roblox-style joints, "
            "catalog hair accessories and Roblox clothing textures. Do NOT make voxel cube people. Do NOT make Minecraft, "
            "LEGO, Pixar, clay figures or realistic humans. "
            f"Characters: {'; '.join(identities)}. THIS SHOT'S game area/background: {environment}. "
            f"THIS SHOT'S action: {action}. Camera/framing: {camera}. Emotion conveyed by pose: {emotion}. "
            "Use a noticeably different composition from the previous shot. Show the game environment clearly enough "
            "that a player can recognise where the scene is. Current polished Roblox-engine lighting, cinematic depth, vertical composition. "
            "IMPORTANT: the generated picture contains ZERO typography. Every sign, monitor, poster, board and label must be blank or purely pictorial. "
            "No readable words, fake words, letters, numbers, captions, subtitles, logos, watermarks, usernames, UI text or symbols. "
            "All English captions are added later by the editor. Keep exact avatar outfit colours and hair identity."
        )
        motion_prompt = (
            f"Inside the real Roblox experience {game_name}: {action}. Camera movement: {camera}. "
            "Preserve unmistakable Roblox R15 anatomy and proportions throughout: classic face decal, R15 torso, "
            "separate upper/lower limbs and Roblox catalog hair/clothing. Keep exact character identity and outfit. "
            f"Environment for this shot: {environment}. Emotion through Roblox-style pose/animation: {emotion}. "
            "One readable action only, natural Roblox game-animation timing, no morphing and no human anatomy. "
            "Do not generate ANY writing, letters, numbers, captions, signs, usernames or UI; text is added later in editing."
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

    if len(scenes) < 10:
        raise RuntimeError("Story writer did not create enough usable scenes for a proper longer mini-movie.")

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
        "story_goal": _clean(raw.get("story_goal"), 220),
        "stakes": _clean(raw.get("stakes"), 220),
        "turning_point": _clean(raw.get("turning_point"), 240),
        "payoff": _clean(raw.get("payoff"), 240),
        "hook": scenes[0]["narration"],
        "characters": characters,
        "scenes": scenes,
        "claims": [],
        "warnings": [],
        "narration": narration,
        "word_count": len(re.findall(r"\b[\w'-]+\b", narration)),
        "target_seconds": target_seconds,
    }




def _writer_view(story: dict) -> dict[str, Any]:
    """Strip generated visual/continuity fields before asking Qwen to rewrite."""
    return {
        "title": story.get("title"),
        "game_name": story.get("game_name"),
        "genre": story.get("genre"),
        "premise": story.get("premise"),
        "story_goal": story.get("story_goal"),
        "stakes": story.get("stakes"),
        "turning_point": story.get("turning_point"),
        "payoff": story.get("payoff"),
        "hook": story.get("hook"),
        "characters": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "gender": c.get("gender"),
                "visual_identity": c.get("visual_identity"),
                "personality": c.get("personality"),
            }
            for c in (story.get("characters") or [])[:3]
        ],
        "scenes": [
            {
                "role": scene.get("role"),
                "speaker": "narrator",
                "narration": scene.get("narration"),
                "characters": scene.get("characters") or [],
                "environment": scene.get("environment"),
                "action": scene.get("action"),
                "camera": scene.get("camera"),
                "emotion": scene.get("emotion"),
                "on_screen_emphasis": scene.get("on_screen_emphasis"),
                "sfx_cue": scene.get("sfx_cue"),
                "motion_priority": scene.get("motion_priority"),
            }
            for scene in (story.get("scenes") or [])[:15]
        ],
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
    unique_environments = {
        re.sub(r"\s+", " ", str(scene.get("environment") or "").strip().lower())
        for scene in scenes
        if str(scene.get("environment") or "").strip()
    }
    unique_cameras = {
        str(scene.get("camera") or "").strip().lower()
        for scene in scenes
        if str(scene.get("camera") or "").strip()
    }
    max_words = max(scene_word_counts, default=0)
    total_words = len(re.findall(r"\b[\w'-]+\b", narration))
    expected_min = max(82, round(target_seconds * 1.85))
    expected_max = min(180, round(target_seconds * 2.50))
    banned_hits = [phrase for phrase in BANNED_STORY_PATTERNS if phrase in lower]

    line_starters = []
    for scene in scenes:
        line = re.sub(r"\s+", " ", str(scene.get("narration") or "")).strip()
        first = re.sub(r"[^a-z']+", "", line.lower().split(" ", 1)[0]) if line else ""
        line_starters.append(first)
    mechanical_starters = {"i", "then", "and", "so", "but", "suddenly"}
    mechanical_start_count = sum(1 for x in line_starters if x in mechanical_starters)
    repeated_start_run = any(
        line_starters[i]
        and line_starters[i] == line_starters[i - 1] == line_starters[i - 2]
        for i in range(2, len(line_starters))
    )
    natural_flow_ok = (
        mechanical_start_count <= max(2, len(scenes) // 3)
        and not repeated_start_run
    )

    roles = [str(scene.get("role") or "").lower() for scene in scenes]
    reveal_indexes = [i for i, role in enumerate(roles) if role == "reveal"]
    arc_structure_ok = (
        bool(roles)
        and roles[0] == "hook"
        and roles[-1] == "payoff"
        and "setup" in roles[: max(3, len(roles) // 2)]
        and roles.count("build") >= 3
        and bool(reveal_indexes)
        and max(reveal_indexes) >= max(4, len(roles) // 2)
    )

    arc_fields_ok = all(
        bool(str(story.get(key) or "").strip())
        for key in ("story_goal", "stakes", "turning_point", "payoff")
    )

    return {
        "scene_count_ok": 10 <= len(scenes) <= 15,
        "short_lines_ok": max_words <= 16,
        "arc_structure_ok": arc_structure_ok,
        "arc_fields_ok": arc_fields_ok,
        "word_count_ok": expected_min <= total_words <= expected_max,
        "single_narrator_ok": narrator_lines == len(scenes),
        "natural_flow_ok": natural_flow_ok,
        "mechanical_start_count": mechanical_start_count,
        "line_starters": line_starters,
        "visual_variety_ok": len(unique_environments) >= 4 and len(unique_cameras) >= 5,
        "unique_environment_count": len(unique_environments),
        "unique_camera_count": len(unique_cameras),
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
{json.dumps(_writer_view(story), ensure_ascii=False)}

Score 0-100:
- hook: does the first 1-2 seconds make someone stay?
- relatability: would Roblox players recognise the situation/emotion?
- escalation: does something meaningfully change/get worse or better every few seconds?
- payoff: does the ending reward watching?
- coherence: is there one understandable central goal from setup through climax, with no random nonsense?
- cause_effect: do important beats happen because of previous choices/game mechanics rather than coincidence?
- setup_payoff: does the climax/payoff use something established earlier and directly resolve the opening problem?
- dialogue: does the ONE narrator sound conversational and human rather than like an AI/documentary announcer?
- movie_clarity: can every beat be understood visually?
- character_consistency: are characters simple and reusable across shots?
- visual_variety: do consecutive scenes visibly change framing, area, obstacle or set-piece instead of repeating one backdrop?
- game_specificity: does this clearly happen inside the named game using real mechanics, rather than generic Roblox?
- cringe_avoidance: 100 means not cringe, not babyish, no forced slang, no fake moral.

Also list exact problems and exact rewrite instructions.

Return:
{{
  "hook":0,
  "relatability":0,
  "escalation":0,
  "payoff":0,
  "coherence":0,
  "cause_effect":0,
  "setup_payoff":0,
  "dialogue":0,
  "movie_clarity":0,
  "character_consistency":0,
  "visual_variety":0,
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
        "coherence",
        "cause_effect",
        "setup_payoff",
        "dialogue",
        "movie_clarity",
        "character_consistency",
        "visual_variety",
        "game_specificity",
        "cringe_avoidance",
    )
    scores = {k: max(0, min(100, int(float(result.get(k, 0) or 0)))) for k in keys}
    total = round(
        scores["hook"] * 0.11
        + scores["relatability"] * 0.10
        + scores["escalation"] * 0.09
        + scores["payoff"] * 0.11
        + scores["coherence"] * 0.09
        + scores["cause_effect"] * 0.07
        + scores["setup_payoff"] * 0.05
        + scores["dialogue"] * 0.08
        + scores["movie_clarity"] * 0.06
        + scores["character_consistency"] * 0.04
        + scores["visual_variety"] * 0.07
        + scores["game_specificity"] * 0.09
        + scores["cringe_avoidance"] * 0.04,
        1,
    )
    problems = list(result.get("problems") or [])
    rewrite_instructions = list(result.get("rewrite_instructions") or [])
    if not mechanical["short_lines_ok"]:
        problems.append(f"Some spoken beats are too long ({mechanical['max_scene_words']} words).")
        rewrite_instructions.append("Keep every spoken beat at 16 words or fewer; most should be 6-14 words.")
    if not mechanical["arc_structure_ok"] or not mechanical["arc_fields_ok"]:
        problems.append("The story does not have a complete goal → obstacle → turn → climax → payoff arc.")
        rewrite_instructions.append(
            "Rebuild the plot around one central goal. Establish stakes, make setbacks causal, create a turning point, "
            "then resolve the original problem through a character choice or verified game mechanic."
        )
    if not mechanical["single_narrator_ok"]:
        problems.append("Story switches speakers even though this format uses one consistent narrator.")
        rewrite_instructions.append("Use narrator as the speaker for every beat; let characters act visually.")
    if not mechanical["natural_flow_ok"]:
        problems.append(
            f"Narration restarts too mechanically between scenes ({mechanical['mechanical_start_count']} stiff line starts)."
        )
        rewrite_instructions.append(
            "Rewrite the scene lines so they join into one continuous spoken story; vary sentence openings and let clauses flow across cuts."
        )
    if not mechanical["visual_variety_ok"]:
        problems.append(
            f"Movie repeats too much visually ({mechanical['unique_environment_count']} environments, "
            f"{mechanical['unique_camera_count']} camera framings)."
        )
        rewrite_instructions.append(
            "Use at least 4 clearly different in-game areas/set-pieces and 5 different camera framings. "
            "No two adjacent scenes should look like the same shot."
        )
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
        and scores["payoff"] >= 84
        and scores["coherence"] >= 84
        and scores["cause_effect"] >= 80
        and scores["setup_payoff"] >= 82
        and scores["dialogue"] >= 82
        and scores["game_specificity"] >= 82
        and scores["cringe_avoidance"] >= 85
        and all(
            mechanical[key]
            for key in (
                "scene_count_ok",
                "short_lines_ok",
                "word_count_ok",
                "arc_structure_ok",
                "arc_fields_ok",
                "single_narrator_ok",
                "natural_flow_ok",
                "visual_variety_ok",
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


def _rebuild_scene_visual_prompts(
    scene: dict[str, Any],
    characters: list[dict[str, Any]],
    game_name: str,
) -> None:
    cmap = _character_map(characters)
    identities = [
        cmap[cid]["visual_identity"]
        for cid in scene.get("characters", [])
        if cid in cmap
    ]
    environment = _clean(scene.get("environment"), 220)
    action = _clean(scene.get("action"), 260)
    camera = _clean(scene.get("camera"), 60) or "medium"
    emotion = _clean(scene.get("emotion"), 80)

    keyframe_prompt = (
        f"FRAME FROM A ROBLOX R15 GAMEPLAY MINI-MOVIE set inside the real Roblox experience {game_name}. "
        "The players must have unmistakable modern Roblox R15 avatar anatomy: softly beveled plastic head, "
        "classic Roblox face decal, R15 torso, separate upper/lower arms and legs with visible Roblox-style joints, "
        "catalog hair accessories and Roblox clothing textures. Never use voxel/Minecraft cube anatomy, LEGO proportions, "
        "Pixar/cartoon children or realistic humans. "
        f"Characters: {'; '.join(identities)}. THIS SHOT'S distinct in-game area/background: {environment}. "
        f"THIS SHOT'S action: {action}. Camera/framing: {camera}. Emotion through pose: {emotion}. "
        "Make this composition clearly different from adjacent shots while preserving character identity. "
        "Show enough of the game environment to make the location/obstacle/set-piece readable. "
        "Current polished Roblox-engine lighting, cinematic depth, vertical composition. "
        "ZERO typography in the generated picture: all signs, monitors, posters, boards and labels are blank or pictorial. "
        "No words, fake words, letters, numbers, usernames, UI text, captions, logos or watermarks. "
        "All readable English text is added later by the video editor."
    )
    motion_prompt = (
        f"Inside the real Roblox experience {game_name}: {action}. Camera movement/framing: {camera}. "
        "Preserve unmistakable Roblox R15 anatomy, exact avatar identity, catalog hair/clothing and this shot's environment. "
        f"Environment: {environment}. Emotion through Roblox-style pose/animation: {emotion}. "
        "Use one readable action and restrained game-like movement. No scene transformation, no human anatomy and no voxel/Minecraft look. "
        "Generate no writing, letters, numbers, usernames, captions, signs with text or UI; editor overlays all text later."
    )

    scene["visual_query"] = keyframe_prompt
    scene["keyframe_prompt"] = keyframe_prompt
    scene["motion_prompt"] = motion_prompt
    scene["edit_instruction"] = f"{camera} cinematic cut"


def _direct_story_shots(
    story: dict[str, Any],
    *,
    game_context: dict[str, Any],
) -> dict[str, Any]:
    """Separate movie direction from writing so every scene earns a new visual."""
    scenes = story.get("scenes") or []
    if not scenes:
        return story

    compact = [
        {
            "index": idx,
            "role": scene.get("role"),
            "narration": scene.get("narration"),
            "characters": scene.get("characters"),
            "current_environment": scene.get("environment"),
            "current_action": scene.get("action"),
            "current_camera": scene.get("camera"),
        }
        for idx, scene in enumerate(scenes)
    ]

    directed = chat_json(
        "You are a Roblox cinematic shot director. Return JSON only.",
        f"""
GAME: {game_context.get("game_name")}

VERIFIED GAME CONTEXT:
{story_game_prompt_context(game_context)}

LOCKED STORY BEATS:
{json.dumps(compact, ensure_ascii=False)}

Create a shot plan for these exact beats. Do NOT rewrite narration or plot.

Hard rules:
- Return exactly {len(scenes)} shots in the same order.
- Every shot must visibly communicate its narration beat.
- Use only locations, mechanics, props, enemies or objectives supported by VERIFIED GAME CONTEXT.
- The movie happens in one continuous game session, but it must VISIBLY MOVE FORWARD.
- Prefer 4-7 distinct game areas/set-pieces across the longer Short when the verified game supports them.
- Never give adjacent shots the same environment + camera combination.
- Use at least 6 camera/framing changes across the Short.
- Backgrounds must look like real Roblox game environments, not Minecraft voxel maps and not photoreal real-world film sets. Use Roblox-scale geometry, stylized materials, readable obstacle/gameplay layout and game-like lighting.
- Alternate useful visual scale: establishing/wide, medium action, close-up reaction/detail, follow/over-shoulder.
- Reuse an environment only when the story logically returns there, and then change angle/action/composition.
- Do not design text cards, fake UI, signs with writing, usernames or menus. Any sign/screen must be blank or pictorial.
- Do not ask the image/video model to spell anything.
- Keep actions simple enough for a 2-4 second AI-video shot. Longer scenes can continue on a still/keyframe with editor motion rather than asking the video model to invent extra action.
- Avoid vague directions like "he looks shocked"; include a physical action or visible game event.

Return exactly:
{{
  "shots":[
    {{
      "index":0,
      "environment":"specific verified game area/background/set-piece",
      "action":"one physical visible action",
      "camera":"wide|medium|close-up|over-shoulder|follow|low-angle|high-angle",
      "emotion":"short pose/emotion direction",
      "motion_priority":"high|medium|low",
      "visual_change":"what makes this shot visibly different from the previous shot"
    }}
  ]
}}
""",
        temperature=0.26,
    )

    shots = directed.get("shots") if isinstance(directed.get("shots"), list) else []
    by_index: dict[int, dict[str, Any]] = {}
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        try:
            idx = int(shot.get("index"))
        except Exception:
            continue
        by_index[idx] = shot

    cameras = ("wide", "medium", "close-up", "over-shoulder", "follow", "low-angle", "high-angle")
    for idx, scene in enumerate(scenes):
        shot = by_index.get(idx)
        if shot:
            env = _clean(shot.get("environment"), 220)
            action = _clean(shot.get("action"), 260)
            camera = _clean(shot.get("camera"), 60).lower()
            emotion = _clean(shot.get("emotion"), 90)
            priority = _clean(shot.get("motion_priority"), 12).lower()
            if env:
                scene["environment"] = env
            if action:
                scene["action"] = action
            if camera in cameras:
                scene["camera"] = camera
            if emotion:
                scene["emotion"] = emotion
            if priority in {"high", "medium", "low"}:
                scene["motion_priority"] = priority
            scene["visual_change"] = _clean(shot.get("visual_change"), 180)

        # Deterministic fallback: adjacent scenes can never keep the same camera.
        if idx and scene.get("camera") == scenes[idx - 1].get("camera"):
            current = str(scene.get("camera") or "medium")
            pos = cameras.index(current) if current in cameras else 1
            scene["camera"] = cameras[(pos + 2 + idx) % len(cameras)]

    characters = story.get("characters") or []
    game_name = _clean(story.get("game_name") or game_context.get("game_name"), 80)
    for scene in scenes:
        _rebuild_scene_visual_prompts(scene, characters, game_name)

    return story


def _polish_narration(
    story: dict,
    *,
    audience: str,
    target_seconds: int,
    game_context: dict[str, Any],
) -> dict:
    scenes = story.get("scenes") or []
    if not scenes:
        return story

    compact = [
        {
            "index": idx,
            "role": scene.get("role"),
            "event": scene.get("action"),
            "current_line": scene.get("narration"),
        }
        for idx, scene in enumerate(scenes)
    ]
    result = chat_json(
        "You are a human-sounding YouTube Shorts narration editor. Return JSON only.",
        f"""
AUDIENCE: {audience}
GAME: {game_context.get("game_name")}
TARGET RUNTIME: {target_seconds} seconds
TARGET SPOKEN WORDS: roughly {round(target_seconds * 2.05)}-{round(target_seconds * 2.35)} words

The visuals/events are LOCKED. Rewrite ONLY the narration so it sounds like one real person
casually telling a friend what happened while the gameplay/movie plays.

SCENES:
{json.dumps(compact, ensure_ascii=False)}

Rules:
- Return exactly {len(scenes)} lines, one per scene, same order.
- Preserve every event and the ending. Do not add new plot points.
- When all lines are joined with spaces, they must sound like ONE continuous spoken story.
- Usually 6-14 words per line. Use the longer runtime to tell more STORY, not to pad sentences.
- Total narration should land close to the target spoken-word range above.
- Use contractions: I'm, I'd, we're, didn't, couldn't, etc.
- Natural everyday wording, like a gamer telling a friend what happened five minutes ago.
- Include small human phrasing where natural: "I thought...", "we nearly...", "he just...", "for a second...", but do not force filler.
- Do not sound like a trailer, documentary, news reader, motivational speaker or AI narrator.
- Avoid restarting the story every scene.
- Do not repeatedly start with I / Then / And then / So / But then / Suddenly.
- Never say: little did I know, everything changed, what happened next, you won't believe,
  that's when everything changed, I couldn't believe my eyes.
- No fake hype and no moral.
- Punctuation should create natural breathing: commas for small pauses, periods only where a person would really stop.

Return exactly:
{{"lines":["line 1","line 2"]}}
""",
        temperature=0.28,
    )
    lines = result.get("lines") if isinstance(result.get("lines"), list) else []
    lines = [_clean(x, 180) for x in lines]
    if len(lines) != len(scenes) or any(not x for x in lines):
        return story

    for scene, line in zip(scenes, lines):
        scene["narration"] = line
    story["hook"] = scenes[0]["narration"]
    narration = " ".join(scene["narration"] for scene in scenes)
    story["narration"] = narration
    story["word_count"] = len(re.findall(r"\b[\w'-]+\b", narration))
    return story


def _finalize_story_quality(
    story: dict[str, Any],
    *,
    audience: str,
    target_seconds: int,
    game_context: dict[str, Any],
) -> dict[str, Any]:
    """Final cheap polish loop before any expensive audio/image/video generation starts."""
    best_story = story
    best_score: dict[str, Any] | None = None

    for _ in range(2):
        candidate = _direct_story_shots(
            best_story,
            game_context=game_context,
        )
        candidate = _polish_narration(
            candidate,
            audience=audience,
            target_seconds=target_seconds,
            game_context=game_context,
        )
        score = _score_story(
            candidate,
            audience,
            target_seconds,
            game_context,
        )
        candidate["story_score"] = score

        if best_score is None or float(score.get("total") or 0) >= float(best_score.get("total") or 0):
            best_story = candidate
            best_score = score

        if score.get("passed"):
            return candidate

    best_story["story_score"] = best_score or _score_story(
        best_story,
        audience,
        target_seconds,
        game_context,
    )
    return best_story


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
            return _finalize_story_quality(
                story,
                audience=audience,
                target_seconds=target_seconds,
                game_context=game_context,
            )

        rewritten = chat_json(
            "You are rewriting a Roblox mini-movie that failed a strict audience-retention review. Return JSON only.",
            f"""
AUDIENCE: {audience}
TARGET: {target_seconds} seconds
REAL GAME CONTEXT:
{story_game_prompt_context(game_context)}

CURRENT STORY:
{json.dumps(_writer_view(story), ensure_ascii=False)}

EDITOR SCORE:
{json.dumps(score, ensure_ascii=False)}

Rewrite the WHOLE story.
Preserve useful character identities, but fix the exact problems.
Start inside the conflict. Make it more recognisable to players of {game_context.get("game_name")}.
The problem and payoff must depend on real mechanics from the supplied game context.
Do not make it louder/randomer just to increase excitement.
No fake moral, no forced slang, no babyish wording.
Return ONLY the compact writer JSON shape used in CURRENT STORY.
Do not add character_visuals, keyframe_prompt, motion_prompt, visual_query, game_context,
retention, claims, warnings, source_ids, edit_instruction, pattern_interrupt or any other derived fields.
""",
            temperature=0.48,
        )
        retained_idea = story.get("idea_selection")
        story = _normalise_story(rewritten, target_seconds, game_context)
        if retained_idea:
            story["idea_selection"] = retained_idea

    return _finalize_story_quality(
        story,
        audience=audience,
        target_seconds=target_seconds,
        game_context=game_context,
    )
