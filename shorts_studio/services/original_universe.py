from __future__ import annotations

from typing import Any


WORLD_NAME = "Astra City"

WORLD_PREMISE = (
    "Astra City is an original Roblox-style animated world built for the channel. "
    "Max, Mia and Kai are ordinary friends who discovered unstable Core abilities. "
    "They still argue, mess up and help each other like real friends; the powers create problems as often as they solve them."
)

LOCATIONS = [
    {
        "name": "Astra Central Plaza",
        "description": "wide modern Roblox city plaza with a circular fountain, block-built shops, street lamps and an elevated rail visible between towers",
    },
    {
        "name": "Northline Station",
        "description": "bright Roblox metro station with tiled platforms, blue route lights, turnstiles, stairs and a stopped blocky train",
    },
    {
        "name": "Academy Courtyard",
        "description": "open Roblox school courtyard with concrete steps, basketball area, benches, trees and a glass-fronted school building",
    },
    {
        "name": "Academy Science Wing",
        "description": "clean Roblox school science corridor with blue lockers, lab windows, equipment carts and emergency shutters",
    },
    {
        "name": "Rooftop District",
        "description": "connected Roblox city rooftops with vents, billboards with blank faces, water tanks, railings and nearby towers",
    },
    {
        "name": "Old Power Station",
        "description": "large Roblox industrial hall with turbines, catwalks, thick cables, warning lights without readable text and a glowing Core chamber",
    },
    {
        "name": "Canal Underpass",
        "description": "concrete Roblox canal beneath a road with maintenance walkways, drainage tunnels, graffiti-like abstract shapes with no readable words and reflected city light",
    },
    {
        "name": "Warehouse Docks",
        "description": "Roblox cargo yard with stacked containers, loading ramps, cranes, forklifts and water beyond the dock",
    },
    {
        "name": "Forest Relay",
        "description": "small Roblox technology outpost in a pine forest with antenna towers, modular buildings, cables and a fenced generator pad",
    },
    {
        "name": "Skybridge",
        "description": "glass-and-metal Roblox pedestrian bridge between towers with city streets far below and emergency shutters at both ends",
    },
]

POWER_RULES = {
    "max": {
        "name": "Kinetic Charge",
        "abilities": ["kinetic_dash", "shockwave", "energy_orb"],
        "strength": "Max can store movement and release it as a short dash or close-range force pulse.",
        "limit": "The charge must build through movement; using too much at once throws off his balance and leaves him drained.",
    },
    "mia": {
        "name": "Vector Field",
        "abilities": ["shield", "telekinesis", "energy_orb"],
        "strength": "Mia can make short-lived barriers and move small nearby objects with focused force.",
        "limit": "She cannot move people or huge structures; a hard impact can crack the barrier and break her concentration.",
    },
    "kai": {
        "name": "Arc Current",
        "abilities": ["lightning", "energy_blast", "kinetic_dash"],
        "strength": "Kai can route short electrical bursts through nearby metal and make a brief speed-assisted movement.",
        "limit": "He needs a conductive path or charged device nearby; overloads can cut power to equipment he still needs.",
    },
}

RECURRING_THREATS = [
    {
        "name": "Core Drone",
        "description": "small angular Roblox security drone with a single glowing lens and folding arms",
        "use": "a clear physical obstacle that patrols, steals or protects Core technology; never appears without an established reason",
    },
    {
        "name": "Rift Surge",
        "description": "unstable glowing crack or energy storm caused by damaged Core equipment",
        "use": "environmental hazard with visible setup; never a random magic portal",
    },
    {
        "name": "City Blackout",
        "description": "power failure that shuts doors, trains, lights or elevators and creates a practical rescue/problem-solving story",
        "use": "must have an established electrical cause",
    },
]


def original_story_context() -> dict[str, Any]:
    setpieces = [
        {
            "name": item["name"],
            "appearance": item["description"],
            "story_use": "recurring original-series location",
            "source_ids": [],
        }
        for item in LOCATIONS
    ]
    return {
        "game_name": WORLD_NAME,
        "experience_url": "",
        "core_loop": WORLD_PREMISE,
        "mechanics": [
            {
                "name": data["name"],
                "description": f"{data['strength']} Limit: {data['limit']}",
                "source_ids": [],
            }
            for data in POWER_RULES.values()
        ],
        "locations": [
            {
                "name": item["name"],
                "description": item["description"],
                "source_ids": [],
            }
            for item in LOCATIONS
        ],
        "visual_setpieces": setpieces,
        "player_situations": [
            {"situation": "A power mistake creates a practical problem that the group has to repair together.", "source_ids": []},
            {"situation": "Two friends disagree on the safe plan and the wrong choice makes the situation worse.", "source_ids": []},
            {"situation": "One character hides a failing power until it becomes impossible to ignore.", "source_ids": []},
            {"situation": "A Core Drone takes something important and the group has to outthink it instead of just chasing it.", "source_ids": []},
            {"situation": "A blackout traps ordinary Roblox citizens somewhere and the group must combine abilities with the environment.", "source_ids": []},
            {"situation": "Someone tries to prove they can handle a power alone, fails, then has to trust the others during the climax.", "source_ids": []},
        ],
        "avoid_inventing": [
            "random hackers",
            "random players chasing the heroes",
            "mystery weapons appearing with no setup",
            "instant unlimited powers",
            "unexplained portals",
            "characters acting stupid only to extend the plot",
            "fake Roblox UI or currencies",
        ],
        "power_rules": POWER_RULES,
        "recurring_threats": RECURRING_THREATS,
        "is_original_universe": True,
        "evidence_score": 100,
        "sources": [],
        "source_domains": [],
        "note": "Original fictional Roblox-style channel universe; no claim that these powers or locations exist in a real Roblox experience.",
    }


def original_story_prompt_context() -> str:
    lines = [
        f"ORIGINAL WORLD: {WORLD_NAME}",
        f"SERIES PREMISE: {WORLD_PREMISE}",
        "",
        "RECURRING CAST POWERS:",
    ]
    for cid, data in POWER_RULES.items():
        lines.append(
            f"- {cid.title()} — {data['name']}: {data['strength']} LIMIT: {data['limit']}"
        )
    lines.extend(["", "REUSABLE LOCATIONS:"])
    for item in LOCATIONS:
        lines.append(f"- {item['name']}: {item['description']}")
    lines.extend(["", "RECURRING THREATS:"])
    for item in RECURRING_THREATS:
        lines.append(f"- {item['name']}: {item['description']}. Rule: {item['use']}")
    lines.extend(
        [
            "",
            "SERIES RULES:",
            "- This is an ORIGINAL animated Roblox-style universe, not a claim about a real Roblox game's mechanics.",
            "- Every episode needs one clear emotional/physical goal, one mistake or choice that worsens it, and an earned payoff.",
            "- Never use 'random player chases them' as the main conflict.",
            "- Never invent a threat in the middle just because the story needs excitement; establish it before it matters.",
            "- Powers have limits and should combine with the environment and friendship/decision-making.",
            "- Keep violence stylized, game-like and non-graphic.",
            "- Use 3-5 visually distinct locations/set-pieces for a normal Short.",
        ]
    )
    return "\n".join(lines)
