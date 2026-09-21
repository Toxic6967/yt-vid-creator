from __future__ import annotations

import json
import re
from typing import Any

from .ollama_client import chat_json
from .story_game import story_game_prompt_context
from .asset_registry import power_prompt_context


def _power_mode(genre: str | None) -> bool:
    return str(genre or "").strip().lower() == "powers"


def _power_story_rules(genre: str | None) -> str:
    if not _power_mode(genre):
        return (
            "POWERS ARE NOT ENABLED. Do not invent magic, portals, energy attacks or sudden superpowers. "
            "Every unusual capability must come from the verified game context."
        )
    return (
        "POWER STORY MODE IS ENABLED. The recurring cast may use only the ORIGINAL FICTIONAL abilities below. "
        "These abilities are part of our animated channel universe, NOT claims about the real Roblox game's mechanics. "
        "Game locations, items, enemies, objectives and UI must still stay faithful to verified game context. "
        "Powers must have setup, limits and consequences; they cannot randomly solve the climax.\n"
        + power_prompt_context()
    )


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

POWER/FANTASY RULES:
{_power_story_rules(genre)}

REAL ROBLOX GAME CONTEXT:
{story_game_prompt_context(game_context)}

Create 12 DIFFERENT mini-movie ideas that happen inside the supplied Roblox world/context.

Every idea must:
- use the supplied locations, character abilities, threats or mechanics rather than inventing random filler;
- be understandable immediately even to a first-time viewer;
- have one specific character goal, one mistake/choice that worsens it, one earned turning point and one payoff;
- NEVER use "a random/another player chases us" as the central conflict;
- if this is the original Astra City universe, treat Max/Mia/Kai like recurring animated-series characters with relationships and power limits;
- if this is a real-game context, stay faithful to that game's verified mechanics;
- have enough CAUSAL STORY DEPTH to sustain 45-70 seconds without filler;
- naturally move through several visually different areas/set-pieces from the verified game context.

Make the 12 ideas genuinely different from one another. Mix structures such as:
- teammate mistake -> escalating recovery;
- greed/risk -> consequence -> clever recovery;
- scary close call -> failed escape -> clutch;
- underdog/underestimated player -> setback -> earned win;
- rare objective/item attempt -> loss -> second chance;
- betrayal/suspicion -> proof -> reversal;
- one-player-left survival;
- risky shortcut -> cost -> comeback.
Do not make all 12 "friend disappears" or "mysterious empty server" stories.

Good story energy: a character causes a problem, tries the obvious fix, pays a cost,
learns something useful, then earns the climax. For Astra City, use power limits, friendship tension,
a Core Drone/Rift/blackout, a rescue, a bad decision or a clever combination of abilities.
Never use a vague stranger/player chase as the entire story.

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
    ideas = [item for item in ideas if isinstance(item, dict)][:12]
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
WORLD/GAME: {game_context.get("game_name")}
ORIGINAL SERIES: {bool(game_context.get("is_original_universe"))}
CANDIDATES:
{json.dumps(ideas, ensure_ascii=False)}

Score each 0-100 for:
- immediate_hook
- relatability_to_real_players
- visual_movie_potential
- escalation
- payoff
- originality
- causal_depth: can this support a real 45-70 second goal->setback->turn->climax story without filler?
- visual_progression: can it naturally move through multiple different game areas/set-pieces?
- game_specificity: does this unmistakably belong in the supplied world/game? For Astra City, reward use of recurring cast powers, limits, locations and threats instead of random generic Roblox conflict.
- cringe_avoidance (100 = not cringe)

Pick the best idea for a 45-70 second cinematic Roblox mini-movie.
Do not reward random shock value. The best idea should be simple enough to understand
instantly but strong enough to make someone stay for the ending.

Return:
{{"best_index":0,"reason":"...","scores":[{{"index":0,"hook":0,"relatability":0,"visual":0,"escalation":0,"payoff":0,"originality":0,"causal_depth":0,"visual_progression":0,"game_specificity":0,"cringe_avoidance":0}}]}}
""",
        temperature=0.16,
    )
    try:
        index = int(judged.get("best_index", 0))
    except Exception:
        index = 0
    index = max(0, min(index, len(ideas) - 1))
    selected = dict(ideas[index])

    score_rows = judged.get("scores") if isinstance(judged.get("scores"), list) else []
    selected_score = next(
        (
            row for row in score_rows
            if isinstance(row, dict) and int(row.get("index", -1)) == index
        ),
        {},
    )
    weak_concept = any(
        int(float(selected_score.get(key, 0) or 0)) < threshold
        for key, threshold in {
            "hook": 80,
            "escalation": 76,
            "payoff": 80,
            "causal_depth": 78,
            "visual_progression": 75,
            "game_specificity": 82,
            "cringe_avoidance": 84,
        }.items()
    )
    if weak_concept:
        improved = chat_json(
            "You are a Roblox Shorts commissioning editor fixing a weak premise before screenplay writing. Return JSON only.",
            f"""
GAME CONTEXT:
{story_game_prompt_context(game_context)}

POWER/FANTASY RULES:
{_power_story_rules(genre)}

WEAK SELECTED CONCEPT:
{json.dumps(selected, ensure_ascii=False)}

SCORE:
{json.dumps(selected_score, ensure_ascii=False)}

Repair the CONCEPT, not the screenplay.
Keep the same game and general genre, but make the premise:
- instantly understandable in 1-2 seconds;
- driven by a real verified game mechanic;
- able to sustain 50-75 seconds through real cause-and-effect escalation;
- capable of moving through several visually distinct verified set-pieces;
- resolved by an earned player decision/skill/mechanic, not coincidence;
- relatable to real players and not cringe.

Return exactly:
{{"premise":"...","genre":"...","opening":"...","escalation":"...","payoff":"..."}}
""",
            temperature=0.34,
        )
        if isinstance(improved, dict) and _clean(improved.get("premise"), 260):
            selected.update({
                key: improved.get(key, selected.get(key))
                for key in ("premise", "genre", "opening", "escalation", "payoff")
            })

    selected["selection_reason"] = _clean(judged.get("reason"), 240)
    selected["selected_score"] = selected_score
    selected["candidate_scores"] = score_rows
    return selected

def _plan_story_arc(
    idea: str,
    *,
    audience: str,
    game_context: dict[str, Any],
    genre: str,
    target_seconds: int,
) -> dict[str, Any]:
    """Lock the causal plot before the screenplay writer expands it."""
    power_rules = _power_story_rules(genre)
    result = chat_json(
        "You are a Roblox story architect. Build simple causal plots, never random AI nonsense. Return JSON only.",
        f"""
AUDIENCE: {audience}
GAME: {game_context.get("game_name")}
GENRE: {genre}
TARGET: {target_seconds} seconds
PREMISE/IDEA: {idea}

VERIFIED GAME CONTEXT:
{story_game_prompt_context(game_context)}

POWER/FANTASY RULES:
{power_rules}

Design ONE coherent mini-movie arc.

Rules:
- One central player goal only.
- Every major problem must come from a VERIFIED game mechanic, player choice, earlier mistake, or (only in powers genre) an already-established approved fictional ability.
- Do not invent random hackers, secret weapons, mystery NPCs, fake items or lore. Follow POWER/FANTASY RULES exactly.
- The failed attempt must make the next problem worse or more urgent.
- The turning point must be something the player notices/decides/uses, not coincidence.
- The climax must resolve the same goal established near the beginning.
- The payoff must directly answer the hook and feel earned.
- Make the character choices emotionally understandable to a young Roblox audience.
- In the original Astra City universe, never make the central conflict "someone/another player is chasing us." Use an established threat, power mistake, rescue problem, rivalry within the cast, blackout, Core Drone or Rift consequence instead.
- Longer runtime means more escalation and character decisions, not extra unrelated subplots.

Return exactly:
{{
  "central_goal":"...",
  "stakes":"...",
  "hook_event":"...",
  "setup":"...",
  "first_obstacle":"...",
  "failed_attempt":"...",
  "escalation":"...",
  "turning_point":"...",
  "climax":"...",
  "payoff":"...",
  "verified_mechanics_used":["...", "..."],
  "do_not_invent":["..."]
}}
""",
        temperature=0.26,
    )
    required = (
        "central_goal",
        "stakes",
        "hook_event",
        "first_obstacle",
        "failed_attempt",
        "turning_point",
        "climax",
        "payoff",
    )
    if any(not _clean(result.get(key), 240) for key in required):
        raise RuntimeError("Story architect did not produce a complete causal plot.")
    return result


def _story_prompt(
    idea: str | None,
    audience: str,
    tone: str,
    target_seconds: int,
    genre: str,
    game_context: dict[str, Any],
    arc_plan: dict[str, Any],
) -> str:
    requested = idea.strip() if idea else "Use the selected premise supplied by the commissioning editor."
    recurring_cast = "\n".join(
        f"- {_default_character(i)['name']}: {_default_character(i)['visual_identity']}; personality: {_default_character(i)['personality']}"
        for i in range(3)
    )
    power_rules = _power_story_rules(genre)
    original_series = bool(game_context.get("is_original_universe"))
    narration_mode = (
        "This is an ORIGINAL RECURRING ANIMATED SERIES episode, not gameplay commentary. "
        "Narrate in natural third person about Max, Mia and Kai. Do not say 'I was playing', "
        "'another player', 'this guy', 'the server', or pretend the events happened to the narrator. "
        "A strong line sounds like: 'Max had one rule: never charge indoors. He broke it immediately.'"
        if original_series
        else
        "This is a story about events inside a real Roblox game. Keep the narration conversational and game-grounded."
    )
    return f"""
AUDIENCE: {audience}
CHANNEL TONE: {tone}
TARGET LENGTH: {target_seconds} seconds
GENRE: {genre}
USER IDEA: {requested}

REAL GAME CONTEXT — DO NOT INVENT OUTSIDE THIS:
{story_game_prompt_context(game_context)}

POWER/FANTASY RULES:
{power_rules}

LOCKED CAUSAL STORY ARC:
{json.dumps(arc_plan, ensure_ascii=False, indent=2)}

RECURRING CHANNEL CAST:
{recurring_cast}

NARRATION MODE:
{narration_mode}

Create a short cinematic mini-movie that takes place INSIDE {game_context.get("game_name")}.
Use 1-3 characters from the recurring cast whenever possible. Keep their names, exact
hair/clothing/colours and core personalities unchanged. A one-off side character is allowed
only when the plot genuinely needs one.

The audience is real young Roblox players, not toddlers. It must feel like a situation,
fear, joke, win, loss, betrayal, grind, teammate problem, rare-item moment, horror-game
moment, server moment, obby moment or friendship moment they can recognise.

NON-NEGOTIABLE:
- Hook in the FIRST 1-2 seconds. Start inside a SPECIFIC problem caused by a character choice, established threat or power failure; no introduction.
- If this is the original Astra City universe, the episode must feel like part of a recurring animated series, not fake gameplay commentary. Never make "running from another player/guy" the plot.
- Use about 10-13 purposeful scenes for a normal ~65 second Story. Aim for 12. Scale with runtime. Maximum 3 characters.
- Think in six macro beats first: hook/problem → goal/setup → first setback → escalation → turning point/climax → payoff.
- Do not split one event into multiple filler scenes just to hit a scene count.
- Each narration line should usually be 6-14 spoken words. The longer runtime is for MORE STORY, not filler.
- Follow the LOCKED CAUSAL STORY ARC above. Do not replace it with a different plot.
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
- Fill because_of and changes for every scene. Scene 2+ must be causally traceable to an earlier choice, event or verified game mechanic.
- Never use "randomly", "somehow", "out of nowhere", "for no reason" or coincidence to move the plot forward.
- Follow NARRATION MODE exactly. The voice should still sound casual and human, but original-series episodes are narrated as a story about the recurring cast, not fake first-person gameplay.
- Keep it inside ONE continuous game session, but the VIDEO must visibly progress.
- Use at least 4 visually different rooms, areas, obstacles, set-pieces or background compositions from the same game when the verified context allows it.
- The background must look like a polished ROBLOX GAME ENVIRONMENT: Roblox Studio-style materials, simple readable geometry, stylized game lighting and game-scale props. Never make a photoreal real-world movie set or a Minecraft voxel map.
- Never leave two adjacent scenes with the same environment AND the same camera framing. Each cut must reveal new visual information.
- Conflict must escalate every few seconds.
- Establish one clear central goal and keep it alive through the whole Short.
- Do not introduce random new villains, secret weapons, rare items or lore. Portals/powers are allowed ONLY when POWER/FANTASY RULES explicitly enable them, and they must be established early, limited, causal and relevant to the original goal.
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
- Use at least TWO supplied world/game-specific mechanics, powers, threats, locations or established props.
- Never invent a fake item, enemy, currency, room, objective or UI element outside the supplied context.

Return JSON exactly:
{{
  "title":"working story title",
  "game_name":"{game_context.get('game_name')}",
  "genre":"funny|horror|mystery|action|relatable|sad|powers",
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
      "because_of":"brief cause from the previous beat/choice/mechanic; for the hook use 'opening situation'",
      "changes":"what is now different after this beat and what pressure/opportunity it creates next",
      "camera":"wide|medium|close-up|over-shoulder|follow|low-angle|high-angle",
      "emotion":"...",
      "on_screen_emphasis":"0-4 words only",
      "sfx_cue":"optional",
      "motion_priority":"high|medium|low"
    }}
  ]
}}
"""


def _required_scene_count(target_seconds: int) -> tuple[int, int]:
    # 65 seconds works best around 12 substantial beats. Requiring 14+ tiny
    # scenes made the local 8B writer truncate JSON and encouraged filler.
    minimum = max(9, min(11, round(target_seconds / 6.5)))
    desired = min(13, max(minimum + 2, round(target_seconds / 5.5)))
    return minimum, desired


def _scene_list_from_writer(raw: Any) -> list[Any]:
    """Accept harmless scene wrappers/shapes commonly emitted by small local models."""
    if not isinstance(raw, dict):
        return []

    candidates: list[Any] = [
        raw.get("scenes"),
        raw.get("shots"),
        raw.get("beats"),
        raw.get("story_beats"),
    ]
    for wrapper in ("story", "screenplay", "script", "result", "output"):
        nested = raw.get(wrapper)
        if isinstance(nested, dict):
            candidates.extend(
                [
                    nested.get("scenes"),
                    nested.get("shots"),
                    nested.get("beats"),
                    nested.get("story_beats"),
                ]
            )

    numbered = [
        value
        for key, value in sorted(raw.items())
        if re.fullmatch(r"scene[_ -]?\d+", str(key), re.I)
        and isinstance(value, (dict, str))
    ]
    if numbered:
        candidates.append(numbered)

    for candidate in candidates:
        # Some local-model replies serialize the scene array one extra time.
        if isinstance(candidate, str):
            text = candidate.strip()
            if text.startswith("[") or text.startswith("{"):
                try:
                    candidate = json.loads(text)
                except Exception:
                    candidate = [candidate]

        if isinstance(candidate, dict):
            # Accept {"1": {...}, "2": {...}} or {"scene_1": "..."}.
            ordered = []
            for key, value in sorted(candidate.items(), key=lambda kv: str(kv[0])):
                if isinstance(value, (dict, str)):
                    ordered.append(value)
            candidate = ordered

        if isinstance(candidate, list):
            usable = [
                item for item in candidate
                if isinstance(item, (dict, str)) and (not isinstance(item, str) or item.strip())
            ]
            if usable:
                return usable
    return []


def _coerce_writer_scene(scene: Any, index: int) -> dict[str, Any]:
    if isinstance(scene, str):
        text = _clean(scene, 260)
        item: dict[str, Any] = {
            "role": "hook" if index == 0 else "build",
            "speaker": "narrator",
            "narration": text,
            "action": text,
        }
    elif isinstance(scene, dict):
        item = dict(scene)
    else:
        return {}

    if not _clean(item.get("narration"), 240):
        for key in ("voiceover", "voice_over", "line", "dialogue", "spoken", "text"):
            if _clean(item.get(key), 240):
                item["narration"] = item.get(key)
                break

    if not _clean(item.get("environment"), 220):
        for key in ("location", "setting", "area", "background"):
            if _clean(item.get(key), 220):
                item["environment"] = item.get(key)
                break

    if not _clean(item.get("action"), 260):
        for key in ("visual", "visual_action", "event", "beat", "what_happens"):
            if _clean(item.get(key), 260):
                item["action"] = item.get(key)
                break

    if not _clean(item.get("because_of"), 180):
        for key in ("cause", "caused_by", "because", "reason"):
            if _clean(item.get(key), 180):
                item["because_of"] = item.get(key)
                break

    if not _clean(item.get("changes"), 200):
        for key in ("result", "consequence", "effect", "outcome", "changes_next"):
            if _clean(item.get(key), 200):
                item["changes"] = item.get(key)
                break

    if not item.get("characters"):
        for key in ("character", "actors", "players"):
            value = item.get(key)
            if isinstance(value, list):
                item["characters"] = value
                break
            if isinstance(value, str) and value.strip():
                item["characters"] = [value]
                break

    if not _clean(item.get("role"), 20):
        item["role"] = "hook" if index == 0 else "build"

    return item


def _coerce_writer_object(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    current = dict(raw)
    for wrapper in ("story", "screenplay", "script", "result", "output"):
        nested = current.get(wrapper)
        if isinstance(nested, dict) and _scene_list_from_writer(nested):
            merged = dict(current)
            merged.update(nested)
            current = merged
            break

    scenes = _scene_list_from_writer(current)
    if scenes:
        current["scenes"] = [
            item
            for idx, scene in enumerate(scenes[:14])
            for item in [_coerce_writer_scene(scene, idx)]
            if item
        ]
    return current


def _usable_raw_scene_count(raw: dict[str, Any]) -> int:
    current = _coerce_writer_object(raw)
    return sum(
        1
        for scene in (current.get("scenes") or [])
        if isinstance(scene, dict) and _clean(scene.get("narration"), 240)
    )


def _fallback_scene_scaffold(
    *,
    desired: int,
    game_context: dict[str, Any],
    arc_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Last-resort causal scaffold. Later scoring/rewrites still have to approve it."""
    beats = [
        ("hook", arc_plan.get("hook_event")),
        ("setup", arc_plan.get("central_goal")),
        ("setup", arc_plan.get("setup")),
        ("build", arc_plan.get("first_obstacle")),
        ("build", arc_plan.get("first_obstacle")),
        ("build", arc_plan.get("failed_attempt")),
        ("build", arc_plan.get("failed_attempt")),
        ("build", arc_plan.get("escalation")),
        ("build", arc_plan.get("escalation")),
        ("reveal", arc_plan.get("turning_point")),
        ("build", arc_plan.get("turning_point")),
        ("build", arc_plan.get("climax")),
        ("reveal", arc_plan.get("climax")),
        ("build", arc_plan.get("climax")),
        ("payoff", arc_plan.get("payoff")),
        ("payoff", arc_plan.get("payoff")),
        ("payoff", arc_plan.get("payoff")),
        ("payoff", arc_plan.get("payoff")),
    ]
    setpieces = [
        _clean(item.get("name") or item.get("description"), 180)
        for item in [
            *(game_context.get("visual_setpieces") or []),
            *(game_context.get("locations") or []),
        ]
        if isinstance(item, dict)
        and _clean(item.get("name") or item.get("description"), 180)
    ]
    if not setpieces:
        setpieces = [f"recognisable {game_context.get('game_name') or 'Roblox'} gameplay area"]

    cameras = ("wide","medium","over-shoulder","follow","close-up","low-angle","high-angle")
    scenes: list[dict[str, Any]] = []
    previous = "opening situation"
    for idx in range(desired):
        role, beat = beats[min(idx, len(beats)-1)]
        text = _clean(beat, 220) or _clean(arc_plan.get("central_goal"), 220) or "The run gets harder."
        if idx and text == _clean(scenes[-1].get("narration"), 240):
            if role == "payoff":
                text = f"That finally settles it: {text}"
            elif role == "reveal":
                text = f"That changes the plan: {text}"
            else:
                text = f"That makes the next move harder: {text}"

        environment = setpieces[idx % min(len(setpieces), 6)]
        scenes.append(
            {
                "role": "hook" if idx == 0 else ("payoff" if idx == desired-1 else role),
                "speaker": "narrator",
                "narration": text,
                "characters": ["max"],
                "environment": environment,
                "action": text,
                "because_of": "opening situation" if idx == 0 else previous,
                "changes": (
                    _clean(beats[min(idx+1, len(beats)-1)][1], 180)
                    or "the next decision becomes more urgent"
                ),
                "camera": cameras[idx % len(cameras)],
                "emotion": "focused" if idx < desired-2 else "relieved",
                "on_screen_emphasis": "",
                "sfx_cue": "",
                "motion_priority": "high" if idx in {0, desired-3, desired-1} else "medium",
            }
        )
        previous = text
    return scenes


def _generate_scene_batches(
    *,
    target_seconds: int,
    game_context: dict[str, Any],
    genre: str,
    arc_plan: dict[str, Any],
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate a longer screenplay in small batches so an 8B local model cannot truncate the whole JSON."""
    minimum, desired = _required_scene_count(target_seconds)
    scaffold = _fallback_scene_scaffold(
        desired=desired,
        game_context=game_context,
        arc_plan=arc_plan,
    )
    collected: list[dict[str, Any]] = []
    existing = [
        _coerce_writer_scene(scene, idx)
        for idx, scene in enumerate(existing or [])
        if isinstance(scene, (dict, str))
    ]

    # Three compact calls are slower, but dramatically more reliable than asking
    # Qwen 8B for a large 12-14 scene JSON object in one response.
    batch_size = 4
    for start in range(0, desired, batch_size):
        end = min(desired, start + batch_size)
        count = end - start
        previous = collected[-2:] if collected else existing[-2:]
        fallback_batch = scaffold[start:end]
        try:
            result = chat_json(
                "You write one compact section of a coherent Roblox screenplay. Return JSON only.",
                f"""
TARGET RUNTIME: {target_seconds} seconds
GAME: {game_context.get("game_name")}
GENRE: {genre}
THIS BATCH: scenes {start + 1}-{end} of {desired}
RETURN EXACTLY: {count} scenes

VERIFIED GAME CONTEXT:
{story_game_prompt_context(game_context)}

POWER/FANTASY RULES:
{_power_story_rules(genre)}

LOCKED CAUSAL ARC:
{json.dumps(arc_plan, ensure_ascii=False)}

PREVIOUS TWO SCENES FOR CONTINUITY:
{json.dumps(previous, ensure_ascii=False)}

FALLBACK BEAT INTENT FOR THIS SECTION:
{json.dumps(fallback_batch, ensure_ascii=False)}

Write ONLY this section of the same story.

Each scene must contain:
role, speaker, narration, characters, environment, action, because_of, changes,
camera, emotion, on_screen_emphasis, sfx_cue, motion_priority.

Rules:
- narration is natural spoken English, normally 6-14 words;
- speaker is narrator;
- use recurring ids max, mia, kai;
- every beat is caused by an earlier action, choice, mistake or verified mechanic;
- keep the one central goal and locked payoff;
- use real verified game locations/mechanics; powers only when POWER/FANTASY RULES allow them;
- no filler, coincidence, fake lore, random secrets or unrelated twists;
- continue naturally from PREVIOUS TWO SCENES;
- vary camera and visual action;
- do not return title, explanation, markdown or derived visual prompts.

Return exactly {{"scenes":[...]}}.
""",
                temperature=0.26,
            )
            batch = _coerce_writer_object(result).get("scenes") or []
            batch = [
                _coerce_writer_scene(scene, start + idx)
                for idx, scene in enumerate(batch[:count])
            ]
            batch = [
                scene for scene in batch
                if scene and _clean(scene.get("narration"), 240)
            ]
        except Exception:
            batch = []

        # Never let one malformed local-model batch destroy the entire story.
        # Fill only the missing slots with the deterministic causal scaffold;
        # later editor + logic passes must still rewrite/approve them.
        if len(batch) < count:
            batch.extend(fallback_batch[len(batch):count])
        collected.extend(batch[:count])

    if len(collected) < minimum:
        collected = scaffold[:desired]
    return collected[:desired]


def _repair_scene_count(
    raw: dict[str, Any],
    *,
    target_seconds: int,
    game_context: dict[str, Any],
    genre: str,
    arc_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Repair scene count without repeatedly asking Qwen to regenerate a huge object."""
    minimum, desired = _required_scene_count(target_seconds)
    current = _coerce_writer_object(raw)
    if _usable_raw_scene_count(current) >= minimum:
        return current

    arc = arc_plan or {}
    existing = current.get("scenes") if isinstance(current.get("scenes"), list) else []

    # One compact whole-array repair is cheap enough to try first.
    try:
        repaired = chat_json(
            "You repair only the scene array of a Roblox screenplay. Return compact JSON only.",
            f"""
TARGET RUNTIME: {target_seconds} seconds
RETURN EXACTLY: {desired} scenes
GAME: {game_context.get("game_name")}
GENRE: {genre}

VERIFIED GAME CONTEXT:
{story_game_prompt_context(game_context)}

POWER/FANTASY RULES:
{_power_story_rules(genre)}

LOCKED CAUSAL ARC:
{json.dumps(arc, ensure_ascii=False)}

EXISTING USABLE SCENES:
{json.dumps(existing[:14], ensure_ascii=False)}

Create the COMPLETE scene array from scene 1 through scene {desired}.
Keep fields compact: role, speaker, narration, characters, environment, action,
because_of, changes, camera, emotion, on_screen_emphasis, sfx_cue, motion_priority.

Every narration must be non-empty natural English, normally 6-14 words.
Scene 1 is hook; final scene is payoff. One central goal. Real cause-and-effect.
No filler/coincidence. Use verified game facts and approved powers only.
Return ONLY {{"scenes":[...]}}.
""",
            temperature=0.24,
        )
        repaired = _coerce_writer_object(repaired)
        repaired_scenes = repaired.get("scenes") if isinstance(repaired.get("scenes"), list) else []
        if repaired_scenes:
            current["scenes"] = repaired_scenes[:14]
            existing = current["scenes"]
        if _usable_raw_scene_count(current) >= minimum:
            return current
    except Exception:
        pass

    # If the local model truncated the long array (including producing zero
    # usable scenes), rebuild it in several small continuity-aware batches.
    current["scenes"] = _generate_scene_batches(
        target_seconds=target_seconds,
        game_context=game_context,
        genre=genre,
        arc_plan=arc,
        existing=existing,
    )

    # Absolute safety net: Story generation may NEVER leave this function with
    # zero/too-few scenes just because Qwen returned malformed/truncated JSON.
    # The deterministic scaffold is intentionally plain; later editor/narration
    # passes still have to improve it before production.
    if _usable_raw_scene_count(current) < minimum:
        current["scenes"] = _fallback_scene_scaffold(
            desired=desired,
            game_context=game_context,
            arc_plan=arc,
        )[:desired]

    current.setdefault("game_name", game_context.get("game_name"))
    current.setdefault("genre", genre)
    current.setdefault("story_goal", arc.get("central_goal"))
    current.setdefault("stakes", arc.get("stakes"))
    current.setdefault("turning_point", arc.get("turning_point"))
    current.setdefault("payoff", arc.get("payoff"))
    current.setdefault("premise", arc.get("central_goal"))
    current.setdefault("title", f"{game_context.get('game_name') or 'Roblox'} Story")
    return current

def _normalise_story(
    raw: dict,
    target_seconds: int,
    game_context: dict[str, Any],
) -> dict:
    raw = _coerce_writer_object(raw)
    characters = _normalise_characters(raw.get("characters"))
    cmap = _character_map(characters)

    scenes_raw = raw.get("scenes") if isinstance(raw.get("scenes"), list) else []
    scenes: list[dict[str, Any]] = []

    for idx, item in enumerate(scenes_raw[:14]):
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
        because_of = _clean(item.get("because_of"), 180)
        changes = _clean(item.get("changes"), 200)
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
                "because_of": because_of,
                "changes": changes,
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

    required_minimum, _ = _required_scene_count(target_seconds)
    if len(scenes) < required_minimum:
        raise RuntimeError(
            f"Story normalization only retained {len(scenes)} usable scenes; "
            f"this {target_seconds}-second Story needs at least {required_minimum}."
        )

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
            "visual_setpieces": game_context.get("visual_setpieces", []),
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
                "because_of": scene.get("because_of"),
                "changes": scene.get("changes"),
                "camera": scene.get("camera"),
                "emotion": scene.get("emotion"),
                "on_screen_emphasis": scene.get("on_screen_emphasis"),
                "sfx_cue": scene.get("sfx_cue"),
                "motion_priority": scene.get("motion_priority"),
            }
            for scene in (story.get("scenes") or [])[:14]
        ],
    }


def _deterministic_story_checks(
    story: dict,
    target_seconds: int,
    game_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        re.sub(
            r"\s+",
            " ",
            str(
                scene.get("environment_key")
                or scene.get("environment")
                or ""
            ).strip().lower(),
        )
        for scene in scenes
        if str(scene.get("environment_key") or scene.get("environment") or "").strip()
    }
    unique_cameras = {
        str(scene.get("camera") or "").strip().lower()
        for scene in scenes
        if str(scene.get("camera") or "").strip()
    }
    max_words = max(scene_word_counts, default=0)
    total_words = len(re.findall(r"\b[\w'-]+\b", narration))
    required_scene_min, desired_scene_count = _required_scene_count(target_seconds)
    required_scene_max = min(14, max(desired_scene_count + 2, required_scene_min))
    expected_min = max(80, round(target_seconds * 1.65))
    expected_max = min(175, round(target_seconds * 2.30))
    banned_hits = [phrase for phrase in BANNED_STORY_PATTERNS if phrase in lower]
    original_universe = bool((game_context or {}).get("is_original_universe"))
    original_bad_conflict_patterns = (
        r"running from (?:a|another|some|random) player",
        r"(?:another|random|mystery|unknown) player .{0,35}(?:chase|follow|hunt)",
        r"(?:a|some) guy .{0,35}(?:chase|follow|hunt)",
        r"player was chasing",
    )
    original_bad_conflict_hits = (
        [
            pattern
            for pattern in original_bad_conflict_patterns
            if re.search(pattern, lower)
        ]
        if original_universe
        else []
    )

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

    causal_links = [
        bool(str(scene.get("because_of") or "").strip())
        and bool(str(scene.get("changes") or "").strip())
        for scene in scenes
    ]
    causal_chain_ok = bool(causal_links) and all(causal_links)
    random_bridge_terms = (
        "randomly",
        "somehow",
        "out of nowhere",
        "for no reason",
        "all of a sudden",
    )
    random_bridge_hits = [
        phrase for phrase in random_bridge_terms
        if phrase in lower
    ]
    coincidence_free_ok = not random_bridge_hits

    return {
        "scene_count_ok": required_scene_min <= len(scenes) <= required_scene_max,
        "required_scene_range": [required_scene_min, required_scene_max],
        "short_lines_ok": max_words <= 16,
        "arc_structure_ok": arc_structure_ok,
        "arc_fields_ok": arc_fields_ok,
        "causal_chain_ok": causal_chain_ok,
        "coincidence_free_ok": coincidence_free_ok,
        "random_bridge_hits": random_bridge_hits,
        "word_count_ok": expected_min <= total_words <= expected_max,
        "single_narrator_ok": narrator_lines == len(scenes),
        "natural_flow_ok": natural_flow_ok,
        "mechanical_start_count": mechanical_start_count,
        "line_starters": line_starters,
        "visual_variety_ok": 4 <= len(unique_environments) <= 8 and len(unique_cameras) >= 5,
        "unique_environment_count": len(unique_environments),
        "unique_camera_count": len(unique_cameras),
        "banned_phrase_ok": not banned_hits and not original_bad_conflict_hits,
        "banned_hits": banned_hits,
        "original_conflict_ok": not original_bad_conflict_hits,
        "original_bad_conflict_hits": original_bad_conflict_hits,
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
    mechanical = _deterministic_story_checks(story, target_seconds, game_context)
    result = chat_json(
        "You are a ruthless short-form story editor for a successful Roblox channel. Return JSON only.",
        f"""
AUDIENCE: {audience}
REAL GAME CONTEXT:
{story_game_prompt_context(game_context)}

LOCKED CAUSAL ARC:
{json.dumps(story.get("arc_plan") or {}, ensure_ascii=False)}

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
- arc_fidelity: does the screenplay actually follow the locked causal arc without inventing unrelated twists?
- dialogue: does the ONE narrator sound conversational and human rather than like an AI/documentary announcer?
- movie_clarity: can every beat be understood visually?
- character_consistency: are characters simple and reusable across shots?
- visual_variety: do consecutive scenes visibly change framing, area, obstacle or set-piece instead of repeating one backdrop?
- game_specificity: does this clearly happen inside the named game using real mechanics/locations rather than generic Roblox? In powers genre, approved fictional character powers are allowed but must not replace game-specific setting/mechanics.
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
  "arc_fidelity":0,
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
        "arc_fidelity",
        "dialogue",
        "movie_clarity",
        "character_consistency",
        "visual_variety",
        "game_specificity",
        "cringe_avoidance",
    )
    scores = {k: max(0, min(100, int(float(result.get(k, 0) or 0)))) for k in keys}
    total = round(
        scores["hook"] * 0.10
        + scores["relatability"] * 0.09
        + scores["escalation"] * 0.08
        + scores["payoff"] * 0.10
        + scores["coherence"] * 0.09
        + scores["cause_effect"] * 0.07
        + scores["setup_payoff"] * 0.05
        + scores["arc_fidelity"] * 0.08
        + scores["dialogue"] * 0.08
        + scores["movie_clarity"] * 0.06
        + scores["character_consistency"] * 0.04
        + scores["visual_variety"] * 0.06
        + scores["game_specificity"] * 0.08
        + scores["cringe_avoidance"] * 0.02,
        1,
    )
    problems = list(result.get("problems") or [])
    rewrite_instructions = list(result.get("rewrite_instructions") or [])
    if not mechanical["scene_count_ok"]:
        problems.append(
            f"Story has {len(story.get('scenes') or [])} scenes; this runtime needs "
            f"{mechanical['required_scene_range'][0]}-{mechanical['required_scene_range'][1]} purposeful scenes."
        )
        rewrite_instructions.append(
            "Add or consolidate causal story beats so each scene advances the same goal; do not add filler."
        )
    if not mechanical["short_lines_ok"]:
        problems.append(f"Some spoken beats are too long ({mechanical['max_scene_words']} words).")
        rewrite_instructions.append("Keep every spoken beat at 16 words or fewer; most should be 6-14 words.")
    if not mechanical["arc_structure_ok"] or not mechanical["arc_fields_ok"]:
        problems.append("The story does not have a complete goal → obstacle → turn → climax → payoff arc.")
        rewrite_instructions.append(
            "Rebuild the plot around one central goal. Establish stakes, make setbacks causal, create a turning point, "
            "then resolve the original problem through a character choice or verified game mechanic."
        )
    if not mechanical["causal_chain_ok"]:
        problems.append("One or more story beats are disconnected instead of being caused by the previous action/mechanic.")
        rewrite_instructions.append(
            "Give every scene a concrete because_of and changes field. Make each beat create the next problem, clue, opportunity or decision."
        )
    if not mechanical["coincidence_free_ok"]:
        problems.append("The plot uses coincidence/randomness as a bridge: " + ", ".join(mechanical["random_bridge_hits"]))
        rewrite_instructions.append(
            "Replace coincidence with a character choice, established setup or verified game mechanic."
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
            f"Movie set-piece plan is weak ({mechanical['unique_environment_count']} environment groups, "
            f"{mechanical['unique_camera_count']} camera framings)."
        )
        rewrite_instructions.append(
            "Use 4-8 clearly different in-game areas/set-pieces and at least 5 camera framings. "
            "Reuse the same stable environment_key when the story remains in one location; "
            "do not create a brand-new map for every single shot."
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
    if not mechanical.get("original_conflict_ok", True):
        problems.append("Original-series conflict is generic/random-player chase filler.")
        rewrite_instructions.append(
            "Replace the random player/guy chase with a specific Astra City conflict caused by a cast choice, power limit, Core Drone, Rift Surge, blackout or rescue problem."
        )

    # "passed" is intentionally demanding, but not perfection-only. The old
    # thresholds caused endless rewrites where an otherwise understandable
    # story was thrown away for one 79/100 sub-score.
    # Hard-stop only genuinely broken stories. Hook wording, narrator polish and
    # shot variety have dedicated later passes, so they should not endlessly
    # reject an otherwise coherent screenplay by a few subjective points.
    # Keep a strong editorial TARGET, but separate it from the production gate.
    # The writer/director still aims for these higher standards and repair passes
    # use the exact problems below. Production should only stop for genuinely
    # broken stories, not because a subjective reviewer gave an otherwise usable
    # hook/dialogue/visual score a few points under target.
    quality_target_met = (
        total >= 76
        and scores["hook"] >= 74
        and scores["payoff"] >= 74
        and scores["coherence"] >= 76
        and scores["cause_effect"] >= 75
        and scores["setup_payoff"] >= 73
        and scores["arc_fidelity"] >= 76
        and scores["dialogue"] >= 72
        and scores["game_specificity"] >= 80
        and scores["cringe_avoidance"] >= 82
        and all(
            mechanical[key]
            for key in (
                "scene_count_ok",
                "short_lines_ok",
                "arc_structure_ok",
                "arc_fields_ok",
                "causal_chain_ok",
                "coincidence_free_ok",
                "single_narrator_ok",
                "banned_phrase_ok",
                "original_conflict_ok",
            )
        )
    )

    # Temporary production gate: deliberately more forgiving while V3 is being
    # tuned. These are the standards that must be non-broken before we spend time
    # on narration/FLUX/Blender. Softer creative scores remain guidance, not blockers.
    passed = (
        total >= 62
        and scores["coherence"] >= 62
        and scores["cause_effect"] >= 60
        and scores["setup_payoff"] >= 58
        and scores["arc_fidelity"] >= 62
        and scores["game_specificity"] >= 68
        and scores["cringe_avoidance"] >= 68
        and all(
            mechanical[key]
            for key in (
                "scene_count_ok",
                "arc_structure_ok",
                "arc_fields_ok",
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
        "quality_target_met": quality_target_met,
        "passed": passed,
    }


def _logic_audit(
    story: dict[str, Any],
    *,
    game_context: dict[str, Any],
) -> dict[str, Any]:
    """Independent red-team pass: reject stories that technically score well but make no sense."""
    result = chat_json(
        "You are a skeptical Roblox player reviewing a story for plot holes. Return JSON only.",
        f"""
GAME: {game_context.get("game_name")}
STORY GENRE: {story.get("genre")}

POWER/FANTASY RULES:
{_power_story_rules(story.get("genre"))}

VERIFIED GAME CONTEXT:
{story_game_prompt_context(game_context)}

LOCKED ARC:
{json.dumps(story.get("arc_plan") or {}, ensure_ascii=False)}

STORY:
{json.dumps(_writer_view(story), ensure_ascii=False)}

Try to DISPROVE that this is a good story. Check:
- causal_logic: does each meaningful event follow from an earlier action, mistake, clue or verified mechanic?
- player_behavior: do the characters act like believable players, or do they become stupid just so the plot can happen?
- game_truth: are game mechanics/locations/items used consistently with verified context? If powers genre is enabled, approved fictional character powers are allowed and must NOT be mistaken for real game mechanics.
- central_goal: is the same goal still driving the middle and climax?
- escalation: do setbacks genuinely increase pressure rather than repeat the same problem?
- turning_point: does a character notice/decide/use something that earns the change in direction?
- ending_logic: does the climax/payoff actually resolve the hook and goal without coincidence?
- filler: are there any scenes that could disappear with no effect on the story?

Return exactly:
{{
  "causal_logic":0,
  "player_behavior":0,
  "game_truth":0,
  "central_goal":0,
  "escalation":0,
  "turning_point":0,
  "ending_logic":0,
  "filler":0,
  "fatal_problems":[],
  "notes":[]
}}

For filler, 100 means NO filler.
For player_behavior, 100 means believable decisions.
""",
        temperature=0.10,
    )
    keys = (
        "causal_logic",
        "player_behavior",
        "game_truth",
        "central_goal",
        "escalation",
        "turning_point",
        "ending_logic",
        "filler",
    )
    scores = {
        key: max(0, min(100, int(float(result.get(key, 0) or 0))))
        for key in keys
    }
    fatal = [
        _clean(item, 220)
        for item in (result.get("fatal_problems") or [])
        if _clean(item, 220)
    ][:6]
    # Keep the critic ambitious, but only block production when the plot is
    # genuinely incoherent or unfaithful to the researched game.
    quality_target_met = (
        scores["causal_logic"] >= 76
        and scores["player_behavior"] >= 72
        and scores["game_truth"] >= 82
        and scores["central_goal"] >= 76
        and scores["escalation"] >= 72
        and scores["turning_point"] >= 72
        and scores["ending_logic"] >= 78
        and scores["filler"] >= 74
        and not fatal
    )
    severe_logic_failure = (
        scores["causal_logic"] < 52
        or scores["game_truth"] < 58
        or scores["central_goal"] < 52
        or scores["ending_logic"] < 52
    )
    passed = (
        not severe_logic_failure
        and scores["causal_logic"] >= 60
        and scores["game_truth"] >= 66
        and scores["central_goal"] >= 60
        and scores["ending_logic"] >= 60
    )
    return {
        "scores": scores,
        "fatal_problems": fatal,
        "notes": [
            _clean(item, 220)
            for item in (result.get("notes") or [])
            if _clean(item, 220)
        ][:8],
        "quality_target_met": quality_target_met,
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

    raw_setpieces = list(game_context.get("visual_setpieces") or [])
    if len(raw_setpieces) < 4:
        raw_setpieces.extend(game_context.get("locations") or [])

    setpiece_catalog = []
    seen_setpieces: set[str] = set()
    for item in raw_setpieces:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"), 100)
        if not name:
            continue
        key = re.sub(r"\s+", " ", name.lower()).strip()
        if key in seen_setpieces:
            continue
        seen_setpieces.add(key)
        setpiece_catalog.append(
            {
                "index": len(setpiece_catalog),
                "name": name,
                "appearance": _clean(
                    item.get("appearance") or item.get("description"),
                    260,
                ),
                "story_use": _clean(item.get("story_use"), 200),
            }
        )
        if len(setpiece_catalog) >= 8:
            break

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

ALLOWED VISUAL SET-PIECES (use these IDs; do not invent new locations):
{json.dumps(setpiece_catalog, ensure_ascii=False)}

LOCKED STORY BEATS:
{json.dumps(compact, ensure_ascii=False)}

Create a shot plan for these exact beats. Do NOT rewrite narration or plot.

Hard rules:
- Return exactly {len(scenes)} shots in the same order.
- Every shot must visibly communicate its narration beat.
- Use only locations, mechanics, props, enemies or objectives supported by VERIFIED GAME CONTEXT.
- For every shot choose a valid setpiece_index from ALLOWED VISUAL SET-PIECES whenever that list is non-empty.
- Do not rename an allowed set-piece into a fake room/location.
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
      "setpiece_index":0,
      "environment_key":"short stable set-piece name reused when scenes share the same location",
      "environment":"specific verified game area/background/set-piece with useful visual detail",
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
            env_key = _clean(shot.get("environment_key"), 80).lower()
            env = _clean(shot.get("environment"), 220)

            if setpiece_catalog:
                try:
                    setpiece_index = int(shot.get("setpiece_index"))
                except Exception:
                    setpiece_index = -1
                if 0 <= setpiece_index < len(setpiece_catalog):
                    chosen = setpiece_catalog[setpiece_index]
                    env_key = _clean(chosen.get("name"), 80).lower()
                    appearance = _clean(chosen.get("appearance"), 220)
                    env = (
                        f"{chosen.get('name')}: {appearance}"
                        if appearance
                        else str(chosen.get("name") or env)
                    )

            action = _clean(shot.get("action"), 260)
            camera = _clean(shot.get("camera"), 60).lower()
            emotion = _clean(shot.get("emotion"), 90)
            priority = _clean(shot.get("motion_priority"), 12).lower()
            if env_key:
                scene["environment_key"] = env_key
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
    original_series = bool(game_context.get("is_original_universe"))
    narration_style = (
        "Natural third-person animated-series storyteller. Use Max/Mia/Kai by name. "
        "Do not pretend the narrator is a player in the scene. Avoid 'I was playing', 'this guy', "
        "'another player', 'the server' and generic gameplay recap language."
        if original_series
        else
        "Natural first-person/observer gamer recap where appropriate."
    )
    result = chat_json(
        "You are a human-sounding YouTube Shorts narration editor. Return JSON only.",
        f"""
AUDIENCE: {audience}
WORLD/GAME: {game_context.get("game_name")}
NARRATION STYLE: {narration_style}
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
- Natural everyday wording. Follow NARRATION STYLE exactly.
- For original-series episodes, favour specific character phrasing like "Max knew...", "Mia caught it...", "Kai had one shot..." instead of fake first-person gameplay.
- Use small human phrasing where natural, but never add filler just to sound casual.
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


def _repair_story_from_editor_score(
    story: dict[str, Any],
    *,
    audience: str,
    target_seconds: int,
    game_context: dict[str, Any],
    score: dict[str, Any],
    logic_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rewrite the actual screenplay when the quality gate finds weak hook/payoff/arc/dialogue."""
    audit = logic_audit or {}
    result = chat_json(
        "You are a senior Roblox Shorts story editor repairing a screenplay after a failed quality review. Return JSON only.",
        f"""
AUDIENCE: {audience}
TARGET RUNTIME: {target_seconds} seconds
GAME: {game_context.get("game_name")}

VERIFIED GAME CONTEXT:
{story_game_prompt_context(game_context)}

POWER/FANTASY RULES:
{_power_story_rules(story.get("genre"))}

LOCKED CAUSAL ARC — FOLLOW THIS, DO NOT INVENT A DIFFERENT PLOT:
{json.dumps(story.get("arc_plan") or {}, ensure_ascii=False)}

CURRENT STORY:
{json.dumps(_writer_view(story), ensure_ascii=False)}

EDITOR SCORE / PROBLEMS:
{json.dumps(score, ensure_ascii=False)}

LOGIC AUDIT:
{json.dumps(audit, ensure_ascii=False)}

Rewrite the WHOLE compact screenplay so it actually passes the review.

Priority order:
1. HOOK: scene 1 starts at the problem, danger, mistake, impossible choice or immediate game pressure. No setup sentence before the conflict.
2. CENTRAL ARC: every scene serves the SAME goal in LOCKED CAUSAL ARC. Remove unrelated twists and side plots.
3. CAUSE/EFFECT: each scene happens because of the previous choice, failure, discovery or verified game mechanic.
4. PAYOFF: the final 2-3 scenes use something established earlier to resolve the original hook and goal.
5. HUMAN NARRATION: write like a real gamer recounting what happened, with contractions and varied sentence openings. No documentary/trailer voice.
6. VISUAL PROGRESSION: use 4-8 VERIFIED game set-pieces/areas across the movie and at least 5 useful camera framings. Do not repeat one backdrop for the whole story.
7. GAME TRUTH: no fake Brookhaven/Roblox mechanics, secret weapons, NPC lore, rooms or UI unless VERIFIED GAME CONTEXT supports them.
8. LENGTH: keep the required number of purposeful scenes for {target_seconds} seconds. No filler.

Hard requirements:
- Keep the same recurring character identities.
- Keep one narrator.
- Every scene has non-empty narration, environment, action, because_of and changes.
- Scene 1 role=hook; final scene role=payoff.
- Include setup/build/reveal progression between them.
- Most narration lines 6-14 words, max 16.
- Preserve compact writer JSON only; do not add derived visual fields.

Return ONLY the repaired compact writer JSON.
""",
        temperature=0.32,
    )

    result = _repair_scene_count(
        result,
        target_seconds=target_seconds,
        game_context=game_context,
        genre=str(story.get("genre") or "auto"),
        arc_plan=story.get("arc_plan") or {},
    )
    repaired = _normalise_story(result, target_seconds, game_context)
    repaired["arc_plan"] = story.get("arc_plan") or {}
    repaired["genre"] = story.get("genre") or repaired.get("genre")
    if story.get("idea_selection"):
        repaired["idea_selection"] = story.get("idea_selection")
    return repaired


def _repair_story_logic(
    story: dict[str, Any],
    *,
    audience: str,
    target_seconds: int,
    game_context: dict[str, Any],
    audit: dict[str, Any],
) -> dict[str, Any]:
    """Targeted rewrite for plot holes found by the independent logic critic."""
    result = chat_json(
        "You are a continuity editor repairing a Roblox mini-movie. Return JSON only.",
        f"""
AUDIENCE: {audience}
TARGET RUNTIME: {target_seconds} seconds
GAME: {game_context.get("game_name")}

VERIFIED GAME CONTEXT:
{story_game_prompt_context(game_context)}

POWER/FANTASY RULES:
{_power_story_rules(story.get("genre"))}

LOCKED ARC:
{json.dumps(story.get("arc_plan") or {}, ensure_ascii=False)}

CURRENT STORY:
{json.dumps(_writer_view(story), ensure_ascii=False)}

INDEPENDENT LOGIC AUDIT:
{json.dumps(audit, ensure_ascii=False)}

Repair the story instead of making it louder or more random.

Hard rules:
- Preserve the same central goal and general premise unless the audit proves they are impossible.
- Every scene after the hook must clearly happen because of an earlier player choice, failure, discovery or VERIFIED game mechanic.
- Fix characters acting stupid for plot convenience.
- Remove filler scenes rather than padding them.
- Replace coincidence with setup, skill, mistake, risk or a mechanic established earlier.
- The turning point must be an earned decision/discovery.
- The climax must use something established earlier and resolve the original goal.
- The payoff must directly answer the hook.
- Do not invent items, enemies, powers, rooms, currencies, UI or lore outside VERIFIED GAME CONTEXT.
- Keep about 10-13 purposeful scenes for a normal ~65 second Story, scaled to the requested runtime.
- Prefer combining weak adjacent beats over adding filler.
- Preserve the compact CURRENT STORY JSON shape.
- Keep because_of and changes for every scene.
- Do not add generated visual prompt fields.

Return ONLY the repaired compact story JSON.
""",
        temperature=0.30,
    )

    result = _repair_scene_count(
        result,
        target_seconds=target_seconds,
        game_context=game_context,
        genre=str(story.get("genre") or "auto"),
        arc_plan=story.get("arc_plan") or {},
    )
    repaired = _normalise_story(result, target_seconds, game_context)
    repaired["arc_plan"] = story.get("arc_plan") or {}
    if story.get("idea_selection"):
        repaired["idea_selection"] = story.get("idea_selection")
    return repaired


def _production_safe_score(score: dict[str, Any]) -> bool:
    """Minimum structural bar for V3 test renders; soft creative scores stay visible as warnings."""
    mechanical = score.get("mechanical") or {}
    logic = score.get("logic_audit") or {}
    logic_scores = logic.get("scores") or {}
    scores = score.get("scores") or {}

    hard_structure = all(
        bool(mechanical.get(key))
        for key in (
            "scene_count_ok",
            "arc_structure_ok",
            "arc_fields_ok",
            "single_narrator_ok",
            "banned_phrase_ok",
        )
    )
    no_severe_logic = not (
        float(logic_scores.get("causal_logic") or 100) < 46
        or float(logic_scores.get("game_truth") or 100) < 52
        or float(logic_scores.get("central_goal") or 100) < 46
        or float(logic_scores.get("ending_logic") or 100) < 46
    )
    return (
        hard_structure
        and no_severe_logic
        and float(score.get("total") or 0) >= 48
        and float(scores.get("coherence") or 0) >= 46
        and float(scores.get("game_specificity") or 0) >= 52
        and float(scores.get("cringe_avoidance") or 0) >= 56
    )


def _deterministic_story_cleanup(
    story: dict[str, Any],
    *,
    game_context: dict[str, Any],
) -> dict[str, Any]:
    """Force structural sanity before asking subjective critics to judge the story."""
    scenes = story.get("scenes") or []
    if not scenes:
        return story

    arc = story.get("arc_plan") or {}
    setpieces = [
        _clean(item.get("name") or item.get("description"), 160)
        for item in [
            *(game_context.get("visual_setpieces") or []),
            *(game_context.get("locations") or []),
        ]
        if isinstance(item, dict)
        and _clean(item.get("name") or item.get("description"), 160)
    ]
    setpieces = list(dict.fromkeys(x for x in setpieces if x))[:8]

    random_replacements = {
        "out of nowhere": "right after that",
        "all of a sudden": "seconds later",
        "for no reason": "because of the last mistake",
        "somehow": "after another attempt",
        "randomly": "during the next move",
    }

    count = len(scenes)
    reveal_index = max(4, min(count - 2, round(count * 0.68)))
    setup_indexes = {1, 2} if count >= 8 else {1}

    # Map the screenplay onto the locked causal spine. Key moments get explicit
    # arc actions so repeated/derailed local-model scenes cannot survive repairs.
    def arc_action(idx: int) -> str:
        progress = idx / max(1, count - 1)
        if idx == 0:
            return _clean(arc.get("hook_event"), 220)
        if idx == count - 1:
            return _clean(arc.get("payoff"), 220)
        if idx == count - 2:
            return _clean(arc.get("climax"), 220)
        if idx == reveal_index:
            return _clean(arc.get("turning_point"), 220)
        if progress < 0.22:
            return _clean(arc.get("setup") or arc.get("central_goal"), 220)
        if progress < 0.42:
            return _clean(arc.get("first_obstacle"), 220)
        if progress < 0.58:
            return _clean(arc.get("failed_attempt"), 220)
        if progress < 0.74:
            return _clean(arc.get("escalation"), 220)
        return _clean(arc.get("climax"), 220)

    # If the writer collapsed almost everything into one backdrop, rebuild the
    # environment sequence from verified locations. We intentionally avoid
    # adjacent repeats while still allowing later returns to an earlier area.
    current_envs = [
        re.sub(r"\s+", " ", str(scene.get("environment") or "").strip().lower())
        for scene in scenes
        if str(scene.get("environment") or "").strip()
    ]
    unique_envs = set(current_envs)
    adjacent_env_repeats = sum(
        1
        for idx in range(1, len(current_envs))
        if current_envs[idx] == current_envs[idx - 1]
    )
    force_environment_plan = bool(
        setpieces
        and (
            len(unique_envs) < min(4, len(setpieces))
            or adjacent_env_repeats >= 2
        )
    )

    if setpieces:
        usable_setpieces = setpieces[: min(6, len(setpieces))]
    else:
        usable_setpieces = [
            f"recognisable {game_context.get('game_name') or 'Roblox'} gameplay area"
        ]

    # Spread locations forward through the story rather than ping-ponging every
    # cut. If we must reuse one, the return occurs later in the movie.
    environment_plan: list[str] = []
    if usable_setpieces:
        for idx in range(count):
            bucket = min(
                len(usable_setpieces) - 1,
                int((idx / max(1, count - 1)) * len(usable_setpieces)),
            )
            environment_plan.append(usable_setpieces[bucket])
        # Remove adjacent repeats when enough verified alternatives exist.
        if len(usable_setpieces) >= 4:
            for idx in range(1, count):
                if environment_plan[idx] == environment_plan[idx - 1]:
                    next_idx = (usable_setpieces.index(environment_plan[idx]) + 1) % len(usable_setpieces)
                    environment_plan[idx] = usable_setpieces[next_idx]

    camera_cycle = (
        "wide",
        "medium",
        "over-shoulder",
        "follow",
        "close-up",
        "low-angle",
        "high-angle",
    )

    seen_lines: dict[str, int] = {}
    for idx, scene in enumerate(scenes):
        # Roles are deterministic. This prevents multiple payoff/reveal labels
        # from confusing both the scorer and the animation director.
        if idx == 0:
            scene["role"] = "hook"
        elif idx == count - 1:
            scene["role"] = "payoff"
        elif idx == reveal_index:
            scene["role"] = "reveal"
        elif idx in setup_indexes:
            scene["role"] = "setup"
        else:
            scene["role"] = "build"

        line = re.sub(r"\s+", " ", str(scene.get("narration") or "")).strip()
        lower = line.lower()
        for bad, good in random_replacements.items():
            if bad in lower:
                line = re.sub(re.escape(bad), good, line, flags=re.I)
                lower = line.lower()

        intended_action = arc_action(idx)
        action = _clean(scene.get("action"), 220)
        previous_action = _clean(scenes[idx - 1].get("action"), 220) if idx else ""
        # Key arc beats and obvious duplicates are re-anchored to the locked plot.
        if intended_action and (
            idx in {0, reveal_index, count - 2, count - 1}
            or not action
            or (idx and action.lower() == previous_action.lower())
        ):
            action = intended_action
        scene["action"] = action or intended_action or line

        normalized_line = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
        duplicate_index = seen_lines.get(normalized_line, 0) if normalized_line else 0
        if normalized_line:
            seen_lines[normalized_line] = duplicate_index + 1
        if not line or duplicate_index:
            # Use the unique locked event as temporary narration. The later
            # narration-polish pass will turn this into natural spoken English.
            line = _clean(scene.get("action"), 180) or "The next move changes the situation."
        scene["narration"] = line

        if force_environment_plan and environment_plan:
            scene["environment"] = environment_plan[idx]
        elif not _clean(scene.get("environment"), 180) and environment_plan:
            scene["environment"] = environment_plan[idx]

        # Guarantee visual framing variety even when the writer keeps returning
        # "medium" for every scene.
        camera = _clean(scene.get("camera"), 60).lower()
        if camera not in camera_cycle:
            camera = camera_cycle[idx % len(camera_cycle)]
        if idx and camera == str(scenes[idx - 1].get("camera") or "").lower():
            camera = camera_cycle[(idx + 2) % len(camera_cycle)]
        scene["camera"] = camera

    # Rebuild the causal links from the cleaned action spine, making each beat
    # explicitly depend on the previous one and point at the next one.
    for idx, scene in enumerate(scenes):
        if idx == 0:
            scene["because_of"] = "opening situation"
        else:
            scene["because_of"] = _clean(
                scenes[idx - 1].get("changes")
                or scenes[idx - 1].get("action")
                or scenes[idx - 1].get("narration"),
                180,
            )

        if idx + 1 < count:
            scene["changes"] = _clean(
                f"This forces the next move: {scenes[idx + 1].get('action') or scenes[idx + 1].get('narration')}",
                200,
            )
        else:
            scene["changes"] = "The opening problem and central goal are resolved."

    # Keep top-level arc fields aligned with the locked arc even after multiple
    # model rewrites.
    story["story_goal"] = _clean(
        arc.get("central_goal") or story.get("story_goal"),
        220,
    )
    story["stakes"] = _clean(arc.get("stakes") or story.get("stakes"), 220)
    story["turning_point"] = _clean(
        arc.get("turning_point") or story.get("turning_point"),
        240,
    )
    story["payoff"] = _clean(arc.get("payoff") or story.get("payoff"), 240)

    story["scenes"] = scenes
    story["hook"] = scenes[0].get("narration") or story.get("hook")
    narration = " ".join(str(s.get("narration") or "").strip() for s in scenes).strip()
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
    """Repair, re-direct and re-score before any expensive media generation starts."""
    working_story = story
    best_story = story
    best_score: dict[str, Any] | None = None

    # Aim for the strong quality target, but do not endlessly reject a usable
    # story. Two focused repair cycles are enough before we accept a production-
    # safe script and let the user judge the actual rendered result.
    for attempt in range(5):
        working_story = _deterministic_story_cleanup(
            working_story,
            game_context=game_context,
        )
        candidate = _direct_story_shots(
            working_story,
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
        logic_audit = _logic_audit(
            candidate,
            game_context=game_context,
        )
        score["logic_audit"] = logic_audit

        if not logic_audit.get("passed"):
            score["passed"] = False
            audit_problems = logic_audit.get("fatal_problems") or logic_audit.get("notes") or []
            if audit_problems:
                score.setdefault("problems", []).extend(
                    ["Logic audit: " + str(x) for x in audit_problems[:4]]
                )
            score.setdefault("rewrite_instructions", []).append(
                "Repair the causal chain, player motivation and payoff using only verified game mechanics; remove filler and coincidence."
            )

        candidate["story_score"] = score
        if best_score is None or float(score.get("total") or 0) >= float(best_score.get("total") or 0):
            best_story = candidate
            best_score = score

        strong_target_met = (
            bool(score.get("quality_target_met"))
            and bool(logic_audit.get("quality_target_met"))
        )
        if strong_target_met:
            return candidate

        # Once we've given the editor a couple of real rewrite attempts, allow a
        # structurally sound screenplay through for a V3 render even when the
        # subjective critic is still asking for more polish. Keep all warnings.
        if (
            attempt >= 2
            and not game_context.get("is_original_universe")
            and _production_safe_score(score)
        ):
            score["passed"] = True
            score["accepted_below_target"] = True
            score["production_safe"] = True
            candidate["story_score"] = score
            return candidate

        # If both normal gates already pass, one improvement pass is enough.
        if (
            score.get("passed")
            and logic_audit.get("passed")
            and attempt >= 1
            and not game_context.get("is_original_universe")
        ):
            score["accepted_below_target"] = True
            score["production_safe"] = True
            candidate["story_score"] = score
            return candidate

        # IMPORTANT: any failed/under-target quality score rewrites the screenplay itself.
        # Previously hook/dialogue/payoff/arc failures just re-ran directing on the
        # same weak script and could never improve.
        try:
            working_story = _repair_story_from_editor_score(
                candidate,
                audience=audience,
                target_seconds=target_seconds,
                game_context=game_context,
                score=score,
                logic_audit=logic_audit,
            )
        except Exception:
            # If the broad editor repair fails, fall back to the narrower logic repair.
            if not logic_audit.get("passed"):
                try:
                    working_story = _repair_story_logic(
                        candidate,
                        audience=audience,
                        target_seconds=target_seconds,
                        game_context=game_context,
                        audit=logic_audit,
                    )
                except Exception:
                    working_story = candidate
            else:
                working_story = candidate

        # Last attempt: make the hook/payoff mechanically explicit rather than
        # repeatedly returning an almost-good script that fails on the same weakness.
        if attempt in {2, 4}:
            scenes = working_story.get("scenes") or []
            if scenes:
                arc = working_story.get("arc_plan") or {}
                hook_event = _clean(arc.get("hook_event"), 180)
                payoff = _clean(arc.get("payoff"), 180)
                if hook_event:
                    scenes[0]["action"] = hook_event
                    scenes[0]["because_of"] = "opening situation"
                    scenes[0]["changes"] = _clean(
                        f"The central problem is now active: {arc.get('stakes') or arc.get('central_goal')}",
                        200,
                    )
                if payoff:
                    scenes[-1]["action"] = payoff
                    scenes[-1]["because_of"] = _clean(
                        f"The climax resolves the central goal: {arc.get('central_goal')}",
                        180,
                    )
                    scenes[-1]["changes"] = "The opening problem is resolved and the story ends."
                working_story["scenes"] = scenes

    best_story["story_score"] = best_score or _score_story(
        best_story,
        audience,
        target_seconds,
        game_context,
    )
    # Final temporary V3 policy: if the best repaired candidate is production-safe
    # according to the relaxed gate, allow it through even when the aspirational
    # target was not reached. Problems remain attached for review/debugging.
    if best_story["story_score"].get("passed"):
        best_story["story_score"]["accepted_below_target"] = not bool(
            best_story["story_score"].get("quality_target_met")
        )
        best_story["story_score"]["production_safe"] = True
    elif (
        not game_context.get("is_original_universe")
        and _production_safe_score(best_story["story_score"])
    ):
        best_story["story_score"]["passed"] = True
        best_story["story_score"]["accepted_below_target"] = True
        best_story["story_score"]["production_safe"] = True
    if best_story.get("story_score") and not best_story["story_score"].get("passed"):
        best_story["story_score"]["production_safe"] = False
        best_story["story_score"]["final_gate_note"] = (
            "Story failed only after deterministic arc/environment/cause-effect repair and five editor passes."
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

    arc_plan = _plan_story_arc(
        idea,
        audience=audience,
        game_context=game_context,
        genre=genre,
        target_seconds=target_seconds,
    )

    # Do NOT ask the local 8B model for one huge 65-second screenplay object.
    # Build the screenplay in small continuity-aware batches from the start.
    # This removes the truncation failure that previously produced 0 usable scenes.
    _, desired_scene_count = _required_scene_count(target_seconds)
    draft = {
        "title": f"{game_context.get('game_name') or 'Roblox'} Story",
        "game_name": game_context.get("game_name"),
        "genre": genre,
        "premise": idea,
        "story_goal": arc_plan.get("central_goal"),
        "stakes": arc_plan.get("stakes"),
        "turning_point": arc_plan.get("turning_point"),
        "payoff": arc_plan.get("payoff"),
        "characters": [_default_character(i) for i in range(3)],
        "scenes": _generate_scene_batches(
            target_seconds=target_seconds,
            game_context=game_context,
            genre=genre,
            arc_plan=arc_plan,
            existing=None,
        )[:desired_scene_count],
    }
    draft = _repair_scene_count(
        draft,
        target_seconds=target_seconds,
        game_context=game_context,
        genre=genre,
        arc_plan=arc_plan,
    )
    story = _normalise_story(draft, target_seconds, game_context)
    if genre != "auto":
        story["genre"] = genre
    story["arc_plan"] = arc_plan
    if selected_idea:
        story["idea_selection"] = selected_idea

    for _ in range(3):
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

POWER/FANTASY RULES:
{_power_story_rules(genre)}

LOCKED CAUSAL ARC:
{json.dumps(story.get("arc_plan") or {}, ensure_ascii=False)}

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
        retained_arc_plan = story.get("arc_plan") or arc_plan
        rewritten = _repair_scene_count(
            rewritten,
            target_seconds=target_seconds,
            game_context=game_context,
            genre=genre,
            arc_plan=retained_arc_plan,
        )
        story = _normalise_story(rewritten, target_seconds, game_context)
        if genre != "auto":
            story["genre"] = genre
        story["arc_plan"] = retained_arc_plan
        if retained_idea:
            story["idea_selection"] = retained_idea

    return _finalize_story_quality(
        story,
        audience=audience,
        target_seconds=target_seconds,
        game_context=game_context,
    )
