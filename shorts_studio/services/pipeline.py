from __future__ import annotations

import json
import shutil
import traceback
import zlib
from pathlib import Path

from ..config import OUTPUT_DIR, ASSET_DIR
from ..db import get_channel_profile, get_job, set_manifest, update_job
from .editor import render
from .research import (
    create_metadata,
    discover_topic,
    research_topic,
    write_fact_checked_script,
    write_relatable_script,
)
from .retention import optimize_retention
from .story_engine import create_story
from .story_game import research_story_game
from .ollama_client import unload_model
from .comfyui_client import free_models as free_comfyui_models
from .tts import render_scene, render_story_narration
from .visuals import prepare_visual, visual_similarity
from .roblox_reference import (
    build_cast_reference,
    build_environment_seed,
    compose_character_reference_sheet,
    compose_scene_previsualization,
)


def _stage(job_id: str, name: str, progress: int) -> None:
    update_job(job_id, status="running", stage=name, progress=progress, error=None)


def _ensure_polished_story_cast(
    job_dir: Path,
    characters: list[dict],
) -> dict[str, str]:
    """Create reusable FLUX-refined R15 identity sheets instead of feeding crude geometry into every scene."""
    from .comfyui_client import generate_story_keyframe

    persistent_dir = ASSET_DIR / "cast" / "r15_v5"
    persistent_dir.mkdir(parents=True, exist_ok=True)
    local_ref_dir = job_dir / "reference"
    local_ref_dir.mkdir(parents=True, exist_ok=True)

    refs: dict[str, str] = {}
    for character in characters[:3]:
        cid = str(character.get("id") or "").strip().lower()
        if not cid:
            continue

        persistent = persistent_dir / f"{cid}.png"
        if not persistent.exists():
            skeleton = build_cast_reference(
                [character],
                local_ref_dir / f"{cid}_r15_skeleton.png",
            )
            seed = zlib.crc32(f"shorts-studio-r15-v5:{cid}".encode("utf-8")) & 0x7FFFFFFF
            first_pass = generate_story_keyframe(
                prompt=(
                    "Create a polished full-body CHARACTER REFERENCE for one authentic current Roblox R15 player avatar. "
                    "This is a Roblox Studio/game avatar sheet, NOT a human portrait and NOT a movie scene. "
                    "Neutral light-grey studio background, full body visible head-to-feet, slight three-quarter game-render angle, relaxed pose. "
                    "Use unmistakable R15 construction: Roblox head proportions with softened bevels, flat classic face decal, "
                    "R15 upper torso/lower torso structure, separate upper/lower arms and legs, visible Roblox joint segmentation, "
                    "simple rounded Roblox hands with NO fingers, game-avatar feet and Roblox catalog hair/accessories. "
                    f"Character identity/outfit: {character.get('visual_identity','')}. "
                    "Clothing must look like Roblox catalog clothing mapped onto an R15 avatar, not real fabric on a human body. "
                    "Use polished current Roblox materials and lighting while keeping the avatar intentionally game-like. "
                    "Absolutely no Minecraft/voxel cube person, LEGO minifigure, Pixar child, realistic human anatomy, fingers, nose, lips or skin pores. "
                    "No props. No writing, letters, numbers, username, logo, UI, watermark or caption anywhere."
                ),
                reference_path=skeleton,
                seed=seed,
                job_id=f"castref_{cid}_v5a",
            )
            second_pass = generate_story_keyframe(
                prompt=(
                    "Audit and repair this avatar into an unmistakable polished Roblox R15 character reference. "
                    "Preserve the exact hair, outfit colours and overall identity. Correct any Minecraft/voxel, LEGO, human or Pixar drift. "
                    "Use classic Roblox face-decal styling, R15 torso proportions, visibly segmented upper/lower limbs and Roblox joints, "
                    "simple game-avatar hands without fingers, Roblox catalog hair/clothing and smooth game-plastic materials. "
                    "Keep a neutral light-grey studio background and the whole body visible. No text, username, logo, UI or props."
                ),
                reference_path=first_pass["path"],
                seed=(seed + 1709) & 0x7FFFFFFF,
                job_id=f"castref_{cid}_v5b",
            )
            shutil.copy2(second_pass["path"], persistent)

        refs[cid] = str(persistent)

    if not refs:
        raise RuntimeError("Could not build the persistent Roblox R15 cast references.")
    return refs


def _scene_polished_paths(
    scene: dict,
    polished_refs: dict[str, str],
) -> list[str]:
    visible = [
        str(cid).lower()
        for cid in (scene.get("characters") or [])
        if str(cid).lower() in polished_refs
    ]
    if not visible:
        visible = list(polished_refs.keys())[:1]
    return [polished_refs[cid] for cid in visible[:3]]


def _scene_polished_reference(
    scene: dict,
    polished_refs: dict[str, str],
    destination: Path,
) -> str:
    paths = _scene_polished_paths(scene, polished_refs)
    return str(compose_character_reference_sheet(paths, destination))



def _environment_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _scene_environment_key(scene: dict) -> str:
    return _environment_key(
        str(scene.get("environment_key") or scene.get("environment") or "")
    )


def _ensure_story_environment_plates(job_dir: Path, script: dict) -> dict[str, str]:
    from .comfyui_client import generate_story_keyframe

    scenes = script.get("scenes") or []
    game_name = str(script.get("game_name") or "Roblox").strip()
    game_context = script.get("game_context") or {}
    visual_setpieces = game_context.get("visual_setpieces") or []
    visual_context = json.dumps(visual_setpieces[:8], ensure_ascii=False)
    plate_dir = job_dir / "reference" / "environments"
    plate_dir.mkdir(parents=True, exist_ok=True)
    seed_ref = build_environment_seed(job_dir / "reference" / "environment_seed.png")
    plates: dict[str, str] = {}

    for idx, scene in enumerate(scenes, start=1):
        environment = str(scene.get("environment") or "").strip()
        key = _scene_environment_key(scene)
        if not key or key in plates:
            continue

        seed = zlib.crc32(f"roblox-env-v2|{game_name}|{key}".encode("utf-8")) & 0x7FFFFFFF
        first_plate = generate_story_keyframe(
            prompt=(
                f"Empty Roblox gameplay environment for {game_name}. "
                f"Location: {environment}. "
                f"Verified visual set-piece context: {visual_context}. "
                "Polished Roblox Studio map, readable game-scale geometry, smooth stylized materials, "
                "current Roblox lighting, clear depth and playable layout. "
                "No characters. No Minecraft voxel terrain. No photoreal real-world film set. "
                "Keep the center area open for Roblox avatars. No readable text, UI, logos or watermarks."
            ),
            reference_path=seed_ref,
            seed=seed,
            job_id=f"envplate_{idx}_{seed % 10000}_a",
        )
        polished_plate = generate_story_keyframe(
            prompt=(
                f"Polish this exact empty {game_name} Roblox environment plate for a cinematic gameplay scene. "
                f"The intended set-piece is: {environment}. Preserve the layout and recognisable landmarks, but make the materials, "
                "lighting, proportions and props look like a high-quality current Roblox Studio game map. "
                "Keep geometry readable and stylized, not Minecraft/voxel and not photoreal. No characters. "
                "All signs/screens/boards stay blank or pictorial; no letters, numbers, usernames, UI, logos or watermarks."
            ),
            reference_path=first_plate["path"],
            seed=(seed + 2309) & 0x7FFFFFFF,
            job_id=f"envplate_{idx}_{seed % 10000}_b",
        )
        destination = plate_dir / f"env_{len(plates) + 1:02d}.png"
        shutil.copy2(polished_plate["path"], destination)
        plates[key] = str(destination)

    if not plates:
        raise RuntimeError("Could not generate Story environment plates.")
    return plates


def run_pipeline(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    profile = get_channel_profile()
    audience = profile.get(
        "audience",
        "Kids / young Roblox players (roughly 8-14); energetic, clear, exciting, never babyish",
    )
    tone = profile.get("tone", "Fast, exciting Roblox gaming documentary")
    manifest: dict = {
        "job_id": job_id,
        "channel_name": job["channel_name"],
        "niche": job["niche"],
        "requested_topic": job.get("requested_topic"),
        "voice": job["voice"],
        "target_seconds": job["target_seconds"],
        "audience": audience,
        "tone": tone,
        "content_type": job.get("content_type", "auto"),
        "story_genre": job.get("story_genre", "auto"),
        "pipeline_version": "2.0.0",
    }

    try:
        requested_type = job.get("content_type", "auto")
        if requested_type == "story":
            selected_topic = job.get("requested_topic") or "Auto-generated relatable Roblox mini-movie"
            content_type = "story"
            topic_pick = {
                "topic": selected_topic,
                "content_type": "story",
                "reason": "Cinematic story mode selected.",
                "candidates": [],
            }
        else:
            _stage(job_id, "Discovering topic", 8)
            topic_pick = discover_topic(
                job["niche"],
                job.get("requested_topic"),
                requested_type,
            )
            selected_topic = topic_pick["topic"]
            content_type = topic_pick.get("content_type") or requested_type or "trend"
            if content_type == "auto":
                content_type = "trend"

        manifest["topic_discovery"] = topic_pick
        manifest["content_type"] = content_type
        update_job(job_id, selected_topic=selected_topic, content_type=content_type)

        if content_type == "story":
            _stage(job_id, "Choosing a real Roblox game + mechanics", 14)
            idea_hint = None if selected_topic.startswith("Auto-generated") else selected_topic
            research = research_story_game(idea_hint)

            _stage(job_id, f"Writing story inside {research.get('game_name','Roblox')}", 30)
            story_tone = (
                "Natural conversational Roblox story told like a real young gaming creator recounting "
                "what just happened to a friend; casual, specific, lightly expressive, never documentary, "
                "never announcer-like and never fake-hype."
            )
            script = create_story(
                idea_hint,
                audience=audience,
                tone=story_tone,
                target_seconds=int(job["target_seconds"]),
                game_context=research,
                genre=job.get("story_genre", "auto"),
            )
            manifest["story_tone"] = story_tone
            selected_topic = (
                f"{script.get('game_name')}: {script.get('title')}"
                if script.get("game_name")
                else (script.get("title") or selected_topic)
            )
            update_job(job_id, selected_topic=selected_topic)
            story_score = script.get("story_score") or {}
            story_scores = story_score.get("scores") or {}
            if not story_score.get("passed"):
                problems = "; ".join(str(x) for x in (story_score.get("problems") or [])[:5])
                raise RuntimeError(
                    "Story writing/directing quality gate did not pass, so expensive media generation was stopped. "
                    + (f"Problems: {problems}" if problems else "The script needs another rewrite.")
                )
            script["retention"] = {
                "passed": bool(story_score.get("passed")),
                "total": story_score.get("total"),
                "scores": {
                    "hook": story_scores.get("hook"),
                    "relatability": story_scores.get("relatability"),
                    "escalation": story_scores.get("escalation"),
                    "payoff": story_scores.get("payoff"),
                    "coherence": story_scores.get("coherence"),
                    "cause_effect": story_scores.get("cause_effect"),
                    "setup_payoff": story_scores.get("setup_payoff"),
                    "arc_fidelity": story_scores.get("arc_fidelity"),
                    "naturalness": story_scores.get("dialogue"),
                    "visual_pacing": story_scores.get("movie_clarity"),
                    "character_consistency": story_scores.get("character_consistency"),
                    "visual_variety": story_scores.get("visual_variety"),
                    "game_specificity": story_scores.get("game_specificity"),
                    "cringe_avoidance": story_scores.get("cringe_avoidance"),
                },
                "issues": story_score.get("problems") or [],
            }
            require_citations = False
        elif content_type == "relatable":
            _stage(job_id, "Planning relatable scenario", 20)
            research = {
                "topic": selected_topic,
                "sources": [],
                "evidence_score": 0,
                "source_domains": [],
                "note": "Relatable scenario: factual research is not required unless specific factual claims are introduced.",
            }
            _stage(job_id, "Writing relatable hook + story", 34)
            script = write_relatable_script(
                selected_topic,
                job["niche"],
                int(job["target_seconds"]),
                audience=audience,
                tone=tone,
            )
            require_citations = False
        else:
            _stage(job_id, "Researching sources", 20)
            research = research_topic(selected_topic)
            _stage(job_id, "Writing + fact checking", 34)
            script = write_fact_checked_script(
                selected_topic,
                job["niche"],
                research,
                int(job["target_seconds"]),
                audience=audience,
                tone=tone,
            )
            require_citations = True

        manifest["research"] = research

        if content_type != "story":
            _stage(job_id, "Optimizing hook + retention", 45)
            script = optimize_retention(
                script,
                selected_topic,
                job["niche"],
                research,
                int(job["target_seconds"]),
                audience=audience,
                tone=tone,
                content_type=content_type,
                require_citations=require_citations,
            )
        manifest["script"] = script
        manifest["retention"] = script.get("retention", {})

        _stage(job_id, "Creating metadata", 52)
        metadata = create_metadata(selected_topic, script)
        manifest["metadata"] = metadata

        # Writing is complete. Free both local-AI runtimes before the
        # higher-quality narration model gets temporary GPU ownership.
        unload_model()
        if content_type == "story":
            free_comfyui_models()

        _stage(job_id, "Generating one continuous human narration take", 58)
        audio_dir = job_dir / "audio"
        audio_dir.mkdir(exist_ok=True)
        master_audio = None

        if content_type == "story":
            master_audio = render_story_narration(
                script["scenes"],
                job["voice"],
                audio_dir / "story_narration.wav",
            )
            scene_audio = master_audio["scene_audio"]
            manifest["narration_master"] = {
                key: value
                for key, value in master_audio.items()
                if key != "scene_audio"
            }
        else:
            scene_audio = []
            character_voices = {
                c.get("id"): c.get("voice_profile")
                for c in script.get("characters", [])
                if c.get("id") and c.get("voice_profile")
            }
            for idx, scene in enumerate(script["scenes"], start=1):
                speaker = str(scene.get("speaker") or "narrator").lower()
                scene_voice = character_voices.get(speaker, job["voice"])
                audio = render_scene(
                    scene["narration"],
                    scene_voice,
                    audio_dir / f"scene_{idx:02d}.wav",
                    role=scene.get("role", ""),
                    require_human=False,
                )
                audio["speaker"] = speaker
                scene_audio.append(audio)

        manifest["audio"] = scene_audio

        if content_type == "story":
            from .comfyui_client import health as comfyui_health
            story_media_state = comfyui_health()
            if not story_media_state.get("story_video_ready"):
                missing_story = ", ".join(
                    story_media_state.get("missing_story_video_models") or []
                )
                raise RuntimeError(
                    "Cinematic Story mode needs the keyframe-to-video backend before rendering. "
                    "Run install_story_video_models.bat, restart ComfyUI, then regenerate."
                    + (f" Missing: {missing_story}." if missing_story else "")
                )

        _stage(job_id, "Building polished Roblox R15 cast", 64)
        visuals = []
        channel_cast_reference = None
        polished_cast_refs: dict[str, str] = {}
        environment_plates: dict[str, str] = {}
        if content_type == "story":
            polished_cast_refs = _ensure_polished_story_cast(
                job_dir,
                script.get("characters", []),
            )
            channel_cast_reference = str(
                compose_character_reference_sheet(
                    list(polished_cast_refs.values()),
                    job_dir / "reference" / "channel_cast_reference.png",
                )
            )
            manifest["polished_cast_references"] = polished_cast_refs

            _stage(job_id, "Building Roblox game environments", 68)
            environment_plates = _ensure_story_environment_plates(job_dir, script)
            manifest["environment_plates"] = environment_plates

        previous_story_frame = None
        duplicate_retry_count = 0
        if content_type == "story":
            _stage(job_id, "Composing cinematic Roblox scenes", 72)

        for idx, (scene, audio) in enumerate(zip(script["scenes"], scene_audio), start=1):
            scene_reference = None
            if content_type == "story":
                scene_reference = _scene_polished_reference(
                    scene,
                    polished_cast_refs,
                    job_dir / "reference" / f"scene_{idx:02d}_cast.png",
                )

            environment_reference = None
            if content_type == "story":
                environment_reference = environment_plates.get(
                    _scene_environment_key(scene)
                )
                if environment_reference:
                    environment_reference = str(
                        compose_scene_previsualization(
                            environment_reference,
                            _scene_polished_paths(scene, polished_cast_refs),
                            job_dir / "reference" / f"scene_{idx:02d}_previs.png",
                            camera=str(scene.get("camera") or "medium"),
                        )
                    )

            visual = prepare_visual(
                scene,
                job_dir,
                idx,
                selected_topic,
                duration=float(audio["duration"]),
                reference_image=scene_reference if content_type == "story" else None,
                identity_reference=scene_reference if content_type == "story" else None,
                environment_reference=environment_reference,
            )

            if content_type == "story":
                def frame_path(item: dict) -> str | None:
                    value = item.get("keyframe_path")
                    if value:
                        return str(value)
                    if item.get("kind") == "ai_generated_scene" and item.get("path"):
                        return str(item["path"])
                    return None

                candidate_frame = frame_path(visual)
                similarity = (
                    visual_similarity(previous_story_frame, candidate_frame)
                    if previous_story_frame and candidate_frame
                    else 0.0
                )

                # If adjacent shots are visually near-identical, automatically
                # regenerate with a different seed/composition instruction.
                if similarity >= 0.82:
                    best_visual = visual
                    best_frame = candidate_frame
                    best_similarity = similarity
                    for attempt in (1, 2):
                        retry = prepare_visual(
                            scene,
                            job_dir,
                            idx,
                            selected_topic,
                            duration=float(audio["duration"]),
                            reference_image=scene_reference,
                            identity_reference=scene_reference,
                            environment_reference=environment_reference,
                            variation_attempt=attempt,
                        )
                        retry_frame = frame_path(retry)
                        retry_similarity = (
                            visual_similarity(previous_story_frame, retry_frame)
                            if previous_story_frame and retry_frame
                            else 0.0
                        )
                        duplicate_retry_count += 1
                        if retry_similarity < best_similarity:
                            best_visual = retry
                            best_frame = retry_frame
                            best_similarity = retry_similarity
                        if retry_similarity < 0.78:
                            break
                    visual = best_visual
                    candidate_frame = best_frame
                    similarity = best_similarity

                visual["previous_frame_similarity"] = round(similarity, 3)
                if candidate_frame:
                    previous_story_frame = candidate_frame

            if channel_cast_reference:
                visual["channel_cast_reference"] = channel_cast_reference
            visuals.append(visual)

        manifest["duplicate_scene_regenerations"] = duplicate_retry_count

        real_video_count = sum(1 for v in visuals if v.get("kind") == "ai_generated_video")
        ltx_video_count = sum(
            1 for v in visuals
            if v.get("kind") == "ai_generated_video" and v.get("backend") == "ltx_i2v"
        )
        if content_type == "story":
            required_story_motion = max(
                5,
                min(8, round(len(script.get("scenes", [])) * 0.60)),
            )
            if ltx_video_count < required_story_motion:
                raise RuntimeError(
                    f"Story render stopped because only {ltx_video_count} cinematic motion shots completed; "
                    f"this story needs at least {required_story_motion}. "
                    "This prevents a slideshow or weak fallback video from being marked finished."
                )
        if content_type != "story" and "roblox" in job["niche"].lower() and real_video_count < 3:
            from .comfyui_client import health as comfyui_health
            media_state = comfyui_health()
            missing = ", ".join(media_state.get("missing_video_models") or [])
            raise RuntimeError(
                "This Short does not have enough genuine video clips yet. "
                "Full Auto now requires at least 3 real AI video scenes for Roblox Shorts."
                + (f" Missing Wan files: {missing}." if missing else "")
            )

        manifest["visuals"] = visuals

        _stage(job_id, "Editing video + captions", 85)
        render_info = render(
            job_dir,
            scene_audio,
            visuals,
            scenes=script.get("scenes"),
            master_audio=master_audio,
        )
        manifest["render"] = render_info

        _stage(job_id, "Running quality checks", 96)
        duration = float(render_info["duration"])
        source_count = len(research.get("sources", []))
        missing_citations = (
            sum(1 for s in script.get("scenes", []) if not s.get("source_ids"))
            if require_citations
            else 0
        )
        external_visuals = [v for v in visuals if v["kind"] == "wikimedia_commons"]
        missing_attribution = sum(1 for v in external_visuals if not v.get("attribution"))
        fallback_visuals = [v for v in visuals if v.get("kind") == "storyboard_fallback"]
        ai_visuals = [v for v in visuals if v.get("kind") == "ai_generated_scene"]
        ai_videos = [v for v in visuals if v.get("kind") == "ai_generated_video"]
        adjacent_similarities = [
            float(v.get("previous_frame_similarity", 0.0))
            for v in visuals
            if v.get("previous_frame_similarity") is not None
        ]
        max_adjacent_similarity = max(adjacent_similarities, default=0.0)
        retention_scores = (script.get("retention") or {}).get("scores") or {}
        environment_plate_count = len(manifest.get("environment_plates") or {})
        quality = {
            "duration_ok": (
                42 <= duration <= 75
                if content_type == "story"
                else 20 <= duration <= 45
            ),
            "duration_seconds": duration,
            "sources_ok": (source_count >= 2) if require_citations else True,
            "source_count": source_count,
            "scene_citations_ok": missing_citations == 0,
            "missing_scene_citations": missing_citations,
            "visual_rights_ok": missing_attribution == 0,
            "external_visual_count": len(external_visuals),
            "ai_visual_count": len(ai_visuals),
            "ai_video_count": len(ai_videos),
            "cinematic_i2v_count": sum(1 for v in ai_videos if v.get("backend") == "ltx_i2v"),
            "fallback_visual_count": len(fallback_visuals),
            "max_adjacent_visual_similarity": round(max_adjacent_similarity, 3),
            "visual_variety_ok": (
                max_adjacent_similarity < 0.84 if content_type == "story" else True
            ),
            "polished_cast_ok": (
                bool(manifest.get("polished_cast_references"))
                if content_type == "story"
                else True
            ),
            "environment_plate_count": environment_plate_count,
            "environment_variety_ok": (
                4 <= environment_plate_count <= 8 if content_type == "story" else True
            ),
            "visual_content_ok": len(fallback_visuals) == 0 and (
                (
                    content_type == "story"
                    and sum(1 for v in ai_videos if v.get("backend") == "ltx_i2v") >= 3
                )
                or (
                    content_type != "story"
                    and ("roblox" not in job["niche"].lower() or len(ai_videos) >= 3)
                )
            ),
            "retention_ok": bool((script.get("retention") or {}).get("passed")),
            "retention_score": (script.get("retention") or {}).get("total"),
            "hook_score": retention_scores.get("hook"),
            "relatability_score": retention_scores.get("relatability"),
            "escalation_score": retention_scores.get("escalation"),
            "payoff_score": retention_scores.get("payoff"),
            "coherence_score": retention_scores.get("coherence"),
            "cause_effect_score": retention_scores.get("cause_effect"),
            "setup_payoff_score": retention_scores.get("setup_payoff"),
            "arc_fidelity_score": retention_scores.get("arc_fidelity"),
            "naturalness_score": retention_scores.get("naturalness"),
            "character_consistency_score": retention_scores.get("character_consistency"),
            "visual_variety_score": retention_scores.get("visual_variety"),
            "game_specificity_score": retention_scores.get("game_specificity"),
            "output_exists": Path(render_info["path"]).exists(),
            "output_bytes": Path(render_info["path"]).stat().st_size if Path(render_info["path"]).exists() else 0,
        }
        quality["passed"] = all(
            quality[key]
            for key in (
                "duration_ok",
                "sources_ok",
                "scene_citations_ok",
                "visual_rights_ok",
                "visual_content_ok",
                "visual_variety_ok",
                "polished_cast_ok",
                "environment_variety_ok",
                "retention_ok",
                "output_exists",
            )
        )
        manifest["quality"] = quality
        manifest_path = job_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        set_manifest(job_id, manifest, render_info["path"])
        update_job(
            job_id,
            status="ready" if quality["passed"] else "review_needed",
            stage="Ready for review" if quality["passed"] else "Review needed",
            progress=100,
        )
    except Exception as exc:
        manifest["error"] = str(exc)
        manifest["traceback"] = traceback.format_exc()
        try:
            (job_dir / "manifest_error.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass
        update_job(job_id, status="failed", stage="Failed", error=str(exc), progress=100)
