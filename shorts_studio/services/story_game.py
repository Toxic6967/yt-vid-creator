from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .ollama_client import chat_json
from .research import _clean, _domain, _fetch_page, _safe_search


FALLBACK_GAMES = (
    "DOORS",
    "Dandy's World",
    "Murder Mystery 2",
    "RIVALS",
    "Brookhaven RP",
    "Blox Fruits",
    "Tower of Hell",
    "99 Nights in the Forest",
)


def _dedupe_results(items: list[dict[str, Any]], limit: int = 16) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        title = _clean(item.get("title"), 180)
        url = str(item.get("href") or item.get("url") or "").strip()
        snippet = _clean(item.get("body") or item.get("snippet"), 420)
        if not title or not url:
            continue
        key = re.sub(r"\W+", "", title.lower())[:100]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "url": url,
                "domain": _domain(url),
                "snippet": snippet,
            }
        )
        if len(out) >= limit:
            break
    return out


def _choose_game(requested_idea: str | None, discovery: list[dict[str, str]]) -> dict[str, Any]:
    year = datetime.now(timezone.utc).year
    evidence_lines = "\n".join(
        f"[{idx}] {item['title']} | {item['domain']} | {item['snippet']}"
        for idx, item in enumerate(discovery[:14], start=1)
    )
    result = chat_json(
        "You commission Roblox story Shorts. Pick a REAL named Roblox experience, not a generic made-up game. Return JSON only.",
        f"""
YEAR: {year}
USER STORY IDEA: {requested_idea or 'none — choose automatically'}

SEARCH EVIDENCE:
{evidence_lines or 'No useful search evidence was available.'}

Pick ONE real Roblox experience that can support a coherent 45-70 second mini-movie with multiple visually distinct gameplay areas/set-pieces.

Rules:
- If the user clearly named a Roblox experience, prefer that exact game if the evidence supports it.
- Otherwise choose a recognisable game with simple visual mechanics young Roblox players understand.
- Do not return "Roblox" as the game name.
- Do not invent a game.
- Avoid choosing a game only because a random article mentions it once.

Return:
{{
  "game_name":"...",
  "why_it_fits":"...",
  "evidence_indexes":[1,2]
}}
""",
        temperature=0.16,
    )
    name = _clean(result.get("game_name"), 80)
    if not name or name.lower() == "roblox":
        name = FALLBACK_GAMES[0]
    return {
        "game_name": name,
        "why_it_fits": _clean(result.get("why_it_fits"), 260),
        "evidence_indexes": [
            int(x) for x in result.get("evidence_indexes", [])
            if str(x).isdigit()
        ],
    }


def research_story_game(requested_idea: str | None = None) -> dict[str, Any]:
    year = datetime.now(timezone.utc).year
    queries = []
    if requested_idea:
        queries.extend(
            (
                f"{requested_idea} Roblox game",
                f"{requested_idea} Roblox gameplay wiki",
                f"{requested_idea} Roblox guide mechanics",
            )
        )
    else:
        queries.extend(
            (
                f"popular Roblox games {year}",
                f"Roblox games players are playing {year}",
                "Roblox popular games horror survival obby roleplay",
            )
        )

    raw: list[dict[str, Any]] = []
    for query in queries:
        raw.extend(_safe_search(query, 8))
    discovery = _dedupe_results(raw, 18)
    selection = _choose_game(requested_idea, discovery)
    game_name = selection["game_name"]

    detail_raw: list[dict[str, Any]] = []
    for query in (
        f"{game_name} Roblox gameplay",
        f"{game_name} Roblox wiki mechanics",
        f"{game_name} Roblox guide items locations rounds",
    ):
        detail_raw.extend(_safe_search(query, 8))
    sources = _dedupe_results(detail_raw, 10)

    for item in sources[:6]:
        body = _fetch_page(item["url"])
        item["excerpt"] = body or item["snippet"]
    for item in sources[6:]:
        item["excerpt"] = item["snippet"]

    source_pack = "\n\n".join(
        f"SOURCE {idx}\nTITLE: {item['title']}\nURL: {item['url']}\nTEXT: {item.get('excerpt') or item['snippet']}"
        for idx, item in enumerate(sources[:8], start=1)
    )

    if len(sources) < 2:
        raise RuntimeError(
            f"Could not research enough reliable gameplay information for {game_name}. "
            "Story Studio will not invent game mechanics."
        )

    context = chat_json(
        "You extract gameplay context for a Roblox story writer. Never invent mechanics. Return JSON only.",
        f"""
GAME: {game_name}

SOURCE PACK:
{source_pack}

Extract only details clearly supported by the source pack.

We need enough detail to write a 45-70 SECOND FICTIONAL MINI-MOVIE that feels like it really happens
inside this game. Focus on mechanics players actually interact with, recognizable locations,
objectives, round structure, enemies/items/resources, failure conditions, common player
situations, and VISUALLY DISTINCT set-pieces that can make each movie scene look different.

Return:
{{
  "game_name":"{game_name}",
  "core_loop":"one short explanation",
  "mechanics":[
    {{"name":"...","description":"...","source_ids":[1,2]}}
  ],
  "locations":[
    {{"name":"...","description":"...","source_ids":[1]}}
  ],
  "player_situations":[
    {{"situation":"relatable thing that can genuinely happen because of the mechanics","source_ids":[1,2]}}
  ],
  "avoid_inventing":["things the sources do NOT establish"]
}}

Need at least 6 useful mechanics/locations/situations total and preferably 4+ visually distinct set-pieces/locations.
Do not invent decorative details that the sources do not support. Keep each item concise.
""",
        temperature=0.12,
    )

    mechanics = context.get("mechanics") if isinstance(context.get("mechanics"), list) else []
    locations = context.get("locations") if isinstance(context.get("locations"), list) else []
    setpieces = (
        context.get("visual_setpieces")
        if isinstance(context.get("visual_setpieces"), list)
        else []
    )
    situations = (
        context.get("player_situations")
        if isinstance(context.get("player_situations"), list)
        else []
    )
    if len(mechanics) + len(locations) + len(setpieces) + len(situations) < 6:
        raise RuntimeError(
            f"Research for {game_name} did not produce enough verified gameplay detail. "
            "Story Studio stopped instead of making up a generic Roblox story."
        )

    return {
        "topic": game_name,
        "game_name": game_name,
        "why_it_fits": selection.get("why_it_fits", ""),
        "core_loop": _clean(context.get("core_loop"), 420),
        "mechanics": mechanics[:8],
        "locations": locations[:8],
        "visual_setpieces": setpieces[:8],
        "player_situations": situations[:8],
        "avoid_inventing": context.get("avoid_inventing") or [],
        "sources": sources[:8],
        "source_domains": sorted({x["domain"] for x in sources if x.get("domain")}),
        "evidence_score": min(100, 45 + len(sources) * 6),
        "discovery_evidence": discovery[:12],
    }


def story_game_prompt_context(game_context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "game_name": game_context.get("game_name"),
            "core_loop": game_context.get("core_loop"),
            "mechanics": game_context.get("mechanics", []),
            "locations": game_context.get("locations", []),
            "visual_setpieces": game_context.get("visual_setpieces", []),
            "player_situations": game_context.get("player_situations", []),
            "avoid_inventing": game_context.get("avoid_inventing", []),
        },
        ensure_ascii=False,
        indent=2,
    )
