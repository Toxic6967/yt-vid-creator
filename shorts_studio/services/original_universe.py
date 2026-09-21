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


EPISODE_BLUEPRINTS = [
    {
        "title": "The Shield Crack",
        "cast": ["mia", "max", "kai"],
        "hook": "Mia's shield fractures while she is holding a failing Skybridge panel in place.",
        "goal": "Get the trapped people across the bridge before the emergency shutters lock.",
        "mistake": "Mia hides that her barrier is already damaged because she wants to prove she can hold it alone.",
        "escalation": "The blackout kills the bridge stabilizers and the damaged panel starts sliding.",
        "turning_point": "Max stops trying to brute-force the door and uses short kinetic bursts to move people while Kai powers one stabilizer at a time.",
        "climax": "Mia uses telekinesis on the loose support cable instead of forcing one giant shield.",
        "payoff": "The last person crosses just as Mia's barrier finally gives out behind them.",
        "locations": ["Skybridge", "Rooftop District", "Astra Central Plaza", "Northline Station"],
    },
    {
        "title": "Max Used Too Much",
        "cast": ["max", "mia", "kai"],
        "hook": "Max hits a kinetic dash indoors and instantly kills the lights in the Academy Science Wing.",
        "goal": "Restore power before the sealed lab doors lock the group inside.",
        "mistake": "Max keeps trying bigger charges instead of admitting the first dash overloaded the local Core relay.",
        "escalation": "Each failed attempt drains the backup system and wakes a security Core Drone.",
        "turning_point": "Kai notices the drone is following the same live cable Max overloaded.",
        "climax": "Mia holds the cable in place, Kai routes a controlled current, and Max releases one tiny stored pulse instead of another huge dash.",
        "payoff": "The lights return; Max celebrates, takes one step, and the exhausted charge drops him flat.",
        "locations": ["Academy Science Wing", "Academy Courtyard", "Canal Underpass", "Old Power Station"],
    },
    {
        "title": "The Drone Took the Core",
        "cast": ["kai", "max", "mia"],
        "hook": "A Core Drone rips the relay cell from Kai's hands and the whole station drops into emergency lighting.",
        "goal": "Recover the relay cell before the stopped train loses door power.",
        "mistake": "Kai tries to disable the drone with electricity and accidentally makes it switch to a faster emergency route.",
        "escalation": "The drone reaches the maintenance tunnel while the train doors begin cycling shut.",
        "turning_point": "Mia realizes the drone avoids loose metal objects because they interfere with its pathing sensors.",
        "climax": "Mia floats a line of tools into its path, Max forces one sharp turn with a kinetic pulse, and Kai catches the cell instead of firing again.",
        "payoff": "The train doors reopen with seconds left, and Kai quietly pockets the tool he nearly fried.",
        "locations": ["Northline Station", "Canal Underpass", "Old Power Station", "Astra Central Plaza"],
    },
    {
        "title": "One Jump Too Far",
        "cast": ["max", "mia"],
        "hook": "Max lands a rooftop dash perfectly, then realizes Mia never made the jump behind him.",
        "goal": "Reach Mia before the unstable rooftop access platform drops another level.",
        "mistake": "Max spent nearly all his kinetic charge showing off on the first jump.",
        "escalation": "The only safe path back is blocked by a Rift Surge that grows whenever loose metal crosses it.",
        "turning_point": "Max notices Mia can move the rooftop vents without throwing them through the surge.",
        "climax": "Mia builds a temporary stepping path with telekinesis while Max saves his final charge for one precise jump.",
        "payoff": "He reaches her, tries to act calm, and Mia points out he is still shaking.",
        "locations": ["Rooftop District", "Skybridge", "Astra Central Plaza", "Canal Underpass"],
    },
    {
        "title": "Kai's Shortcut",
        "cast": ["kai", "mia", "max"],
        "hook": "Kai powers a locked warehouse lift manually and the entire cargo platform starts moving the wrong direction.",
        "goal": "Stop the lift before it carries a Core battery into the water.",
        "mistake": "Kai bypasses the controller because he thinks waiting for Max is slower.",
        "escalation": "The bypass keeps feeding current even after the stop button loses power.",
        "turning_point": "Max realizes the lift motor is adding motion he can absorb as kinetic charge.",
        "climax": "Max drains the platform's motion, Mia holds the battery steady, and Kai cuts the current at the exact moment the lift stalls.",
        "payoff": "The battery survives; Kai says the shortcut worked, and both of them just stare at him.",
        "locations": ["Warehouse Docks", "Canal Underpass", "Old Power Station", "Astra Central Plaza"],
    },
    {
        "title": "Mia Wouldn't Drop It",
        "cast": ["mia", "kai"],
        "hook": "Mia catches a falling relay module with telekinesis and immediately realizes she cannot put it down.",
        "goal": "Carry the unstable module to the Forest Relay before her focus gives out.",
        "mistake": "She refuses Kai's help because moving it twice could trigger another surge.",
        "escalation": "The module starts pulling nearby metal toward itself, making every path harder.",
        "turning_point": "Kai stops trying to touch the module and instead powers lights ahead so Mia can see the safest route.",
        "climax": "Mia lets the module fall for half a second while Kai pulses the receiver open, then catches it again inside the cradle.",
        "payoff": "The relay stabilizes and every loose wrench drops at once around them.",
        "locations": ["Forest Relay", "Canal Underpass", "Warehouse Docks", "Old Power Station"],
    },
    {
        "title": "The Blackout Test",
        "cast": ["max", "mia", "kai"],
        "hook": "Every light in Astra Central Plaza dies while Max is halfway through showing off a new dash.",
        "goal": "Get the plaza emergency system online before the elevated rail reaches the dark station.",
        "mistake": "The trio initially split up, each assuming their own power is the fastest solution.",
        "escalation": "Max reaches the station but has no charge, Mia reaches a jammed shutter she cannot lift alone, and Kai has current but no safe circuit.",
        "turning_point": "They realize the same maintenance line connects all three problems.",
        "climax": "Mia clears the line, Kai energizes it, and Max uses the moving rail's vibration to build just enough kinetic charge to trigger the manual brake.",
        "payoff": "The train stops cleanly, and the plaza lights return one section at a time behind them.",
        "locations": ["Astra Central Plaza", "Northline Station", "Skybridge", "Old Power Station"],
    },
    {
        "title": "The Rift Was Their Fault",
        "cast": ["max", "mia", "kai"],
        "hook": "A thin Rift Surge opens across the Academy floor exactly where the trio tested their powers the night before.",
        "goal": "Close the surge before morning classes start and anyone gets near it.",
        "mistake": "They waste time arguing over whose power caused it instead of checking what the surge reacts to.",
        "escalation": "The surge grows whenever Max moves fast, Mia lifts metal near it, or Kai sends current through the floor.",
        "turning_point": "They finally notice the surge only calms when all three powers stop at the same time.",
        "climax": "They shut everything down, move the damaged Core fragment by hand, then use one carefully timed combined pulse from a safe distance.",
        "payoff": "The floor seals just as the first hallway lights switch on for the morning.",
        "locations": ["Academy Science Wing", "Academy Courtyard", "Old Power Station", "Astra Central Plaza"],
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
        "episode_blueprints": EPISODE_BLUEPRINTS,
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
    lines.extend(["", "EPISODE BLUEPRINTS — use these as quality references, not mandatory copies:"])
    for blueprint in EPISODE_BLUEPRINTS:
        lines.append(
            f"- {blueprint['title']}: hook={blueprint['hook']} goal={blueprint['goal']} "
            f"mistake={blueprint['mistake']} turn={blueprint['turning_point']} payoff={blueprint['payoff']}"
        )
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
