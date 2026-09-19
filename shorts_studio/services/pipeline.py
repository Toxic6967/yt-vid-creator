from __future__ import annotations

import json
import traceback
from pathlib import Path

from ..config import OUTPUT_DIR
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
from .tts import render_scene
from .visuals import prepare_visual


def _stage(job_id: str, name: str, progress: int) -> None:
    update_job(job_id, status="running", stage=name, progress=progress, error=None)


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
        "pipeline_version": "1.2.0",
    }

    try:
        _stage(job_id, "Discovering topic", 8)
        topic_pick = discover_topic(
            job["niche"],
            job.get("requested_topic"),
            job.get("content_type", "auto"),
        )
        selected_topic = topic_pick["topic"]
        content_type = topic_pick.get("content_type") or job.get("content_type", "trend")
        if content_type == "auto":
            content_type = "trend"
        manifest["topic_discovery"] = topic_pick
        manifest["content_type"] = content_type
        update_job(job_id, selected_topic=selected_topic, content_type=content_type)

        if content_type == "relatable":
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

        _stage(job_id, "Generating human-style narration", 55)
        audio_dir = job_dir / "audio"
        audio_dir.mkdir(exist_ok=True)
        scene_audio = []
        for idx, scene in enumerate(script["scenes"], start=1):
            audio = render_scene(
                scene["narration"],
                job["voice"],
                audio_dir / f"scene_{idx:02d}.mp3",
                role=scene.get("role", ""),
            )
            scene_audio.append(audio)
        manifest["audio"] = scene_audio

        _stage(job_id, "Directing scene visuals", 67)
        visuals = []
        for idx, scene in enumerate(script["scenes"], start=1):
            visuals.append(prepare_visual(scene, job_dir, idx, selected_topic))
        manifest["visuals"] = visuals

        _stage(job_id, "Editing video + captions", 81)
        render_info = render(job_dir, scene_audio, visuals)
        manifest["render"] = render_info

        _stage(job_id, "Creating metadata", 92)
        metadata = create_metadata(selected_topic, script)
        manifest["metadata"] = metadata

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
        fallback_visuals = [v for v in visuals if v["kind"] == "storyboard_fallback"]
        ai_visuals = [v for v in visuals if v["kind"] == "ai_generated_scene"]
        quality = {
            "duration_ok": 20 <= duration <= 45,
            "duration_seconds": duration,
            "sources_ok": (source_count >= 2) if require_citations else True,
            "source_count": source_count,
            "scene_citations_ok": missing_citations == 0,
            "missing_scene_citations": missing_citations,
            "visual_rights_ok": missing_attribution == 0,
            "external_visual_count": len(external_visuals),
            "ai_visual_count": len(ai_visuals),
            "fallback_visual_count": len(fallback_visuals),
            "visual_content_ok": len(fallback_visuals) == 0,
            "retention_ok": bool((script.get("retention") or {}).get("passed")),
            "retention_score": (script.get("retention") or {}).get("total"),
            "hook_score": ((script.get("retention") or {}).get("scores") or {}).get("hook"),
            "relatability_score": ((script.get("retention") or {}).get("scores") or {}).get("relatability"),
            "payoff_score": ((script.get("retention") or {}).get("scores") or {}).get("payoff"),
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
