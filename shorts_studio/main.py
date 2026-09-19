from __future__ import annotations

import mimetypes
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import OUTPUT_DIR, ROOT_DIR, settings
from .db import (
    create_job,
    create_media_job,
    get_channel_profile,
    get_job,
    get_media_job,
    get_topic,
    init_db,
    latest_radar_run,
    list_generated_images,
    list_jobs,
    list_media_jobs,
    list_topics,
    save_channel_profile,
    start_radar_run,
    update_job,
    update_media_job,
)
from .models import (
    AIImageRequest,
    AIVideoRequest,
    ChannelProfileRequest,
    GenerateRequest,
    ImageRequest,
    RegenerateRequest,
)
from .services.comfyui_client import (
    health as comfyui_health,
    run_image_job,
    run_video_job,
)
from .services.editor import ffmpeg_health
from .services.image_studio import create_graphic
from .services.ollama_client import health as ollama_health
from .services.pipeline import run_pipeline
from .services.topic_radar import run_radar_job

app = FastAPI(title=settings.app_name, docs_url="/docs", redoc_url=None)
WEB_DIR = ROOT_DIR / "shorts_studio" / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"app_name": settings.app_name})


@app.get("/api/health")
def api_health() -> dict:
    return {
        "app": {"ok": True, "name": settings.app_name},
        "ollama": ollama_health(),
        "ffmpeg": ffmpeg_health(),
        "comfyui": comfyui_health(),
    }


def _queue_short(
    channel_name: str,
    niche: str,
    topic: str | None,
    voice: str,
    target_seconds: int,
    content_type: str = "auto",
) -> dict:
    job_id = uuid.uuid4().hex[:12]
    create_job(
        {
            "id": job_id,
            "channel_name": channel_name.strip(),
            "niche": niche.strip(),
            "requested_topic": topic,
            "content_type": content_type,
            "voice": voice,
            "target_seconds": target_seconds,
        }
    )
    threading.Thread(target=run_pipeline, args=(job_id,), daemon=True).start()
    return {"id": job_id, "status": "queued"}


@app.get("/api/profile")
def profile() -> dict:
    return get_channel_profile()


@app.put("/api/profile")
def update_profile(payload: ChannelProfileRequest) -> dict:
    return save_channel_profile(payload.model_dump())


@app.post("/api/auto-generate", status_code=202)
def auto_generate() -> dict:
    profile = get_channel_profile()
    return _queue_short(
        profile["channel_name"],
        profile["niche"],
        None,
        profile["voice"],
        int(profile["target_seconds"]),
        "auto",
    )


@app.get("/api/radar")
def radar_state() -> dict:
    return {"run": latest_radar_run(), "topics": list_topics(20)}


@app.post("/api/radar/scan", status_code=202)
def scan_radar() -> dict:
    current = latest_radar_run()
    if current and current["status"] == "running":
        return {"id": current["id"], "status": "running"}
    run_id = uuid.uuid4().hex[:12]
    start_radar_run(run_id)
    threading.Thread(target=run_radar_job, args=(run_id,), daemon=True).start()
    return {"id": run_id, "status": "running"}


@app.post("/api/topics/{topic_id}/make-short", status_code=202)
def make_topic_short(topic_id: str) -> dict:
    topic = get_topic(topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    profile = get_channel_profile()
    return _queue_short(
        profile["channel_name"],
        profile["niche"],
        topic["title"],
        profile["voice"],
        int(profile["target_seconds"]),
        (topic.get("evidence") or {}).get("content_type", "trend"),
    )


@app.get("/api/jobs")
def api_jobs() -> list[dict]:
    return list_jobs(60)


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs", status_code=202)
def api_generate(payload: GenerateRequest) -> dict:
    return _queue_short(
        payload.channel_name,
        payload.niche,
        payload.topic,
        payload.voice,
        payload.target_seconds,
        payload.content_type,
    )


@app.post("/api/jobs/{job_id}/approve")
def approve(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in {"ready", "review_needed"}:
        raise HTTPException(409, "Only rendered jobs can be approved")
    update_job(job_id, approved=1, stage="Approved")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/regenerate", status_code=202)
def regenerate(job_id: str, payload: RegenerateRequest) -> dict:
    old = get_job(job_id)
    if not old:
        raise HTTPException(404, "Job not found")
    return _queue_short(
        old["channel_name"],
        old["niche"],
        payload.topic or old.get("selected_topic") or old.get("requested_topic"),
        old["voice"],
        old["target_seconds"],
        old.get("content_type", "auto"),
    )


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    path = OUTPUT_DIR / job_id
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    update_job(job_id, status="deleted", stage="Deleted", output_path=None)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str):
    job = get_job(job_id)
    if not job or not job.get("output_path"):
        raise HTTPException(404, "Rendered video not found")
    path = Path(job["output_path"])
    if not path.exists():
        raise HTTPException(404, "Rendered video file is missing")
    return FileResponse(path, media_type="video/mp4", filename=f"shorts-studio-{job_id}.mp4")


@app.get("/api/jobs/{job_id}/manifest")
def job_manifest(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.get("manifest") or {}


@app.post("/api/images")
def create_image(payload: ImageRequest) -> dict:
    return create_graphic(payload.prompt, payload.headline, payload.aspect)


@app.get("/api/images")
def images() -> list[dict]:
    return list_generated_images(30)


@app.get("/api/images/{image_id}/file")
def image_file(image_id: str):
    image = next((item for item in list_generated_images(100) if item["id"] == image_id), None)
    if not image:
        raise HTTPException(404, "Image not found")
    path = Path(image["output_path"])
    if not path.exists():
        raise HTTPException(404, "Image file is missing")
    return FileResponse(path, media_type="image/jpeg", filename=f"shorts-studio-{image_id}.jpg")


@app.get("/api/media/health")
def media_health() -> dict:
    return comfyui_health()


@app.get("/api/media/jobs")
def media_jobs() -> list[dict]:
    return list_media_jobs(40)


@app.post("/api/media/image", status_code=202)
def generate_ai_image(payload: AIImageRequest) -> dict:
    base = payload.model_dump()
    job_ids = []
    for index in range(payload.variations):
        job_id = uuid.uuid4().hex[:12]
        request = dict(base)
        request["variations"] = 1
        if payload.seed is not None:
            request["seed"] = min(2147483647, int(payload.seed) + index)
        create_media_job(job_id, "image", payload.prompt)
        threading.Thread(
            target=run_image_job,
            args=(job_id, request),
            daemon=True,
        ).start()
        job_ids.append(job_id)
    return {"ids": job_ids, "status": "queued", "count": len(job_ids)}


@app.post("/api/media/video", status_code=202)
def generate_ai_video(payload: AIVideoRequest) -> dict:
    base = payload.model_dump()
    job_ids = []
    for index in range(payload.variations):
        job_id = uuid.uuid4().hex[:12]
        request = dict(base)
        request["variations"] = 1
        if payload.seed is not None:
            request["seed"] = min(2147483647, int(payload.seed) + index)
        create_media_job(job_id, "video", payload.prompt)
        threading.Thread(
            target=run_video_job,
            args=(job_id, request),
            daemon=True,
        ).start()
        job_ids.append(job_id)
    return {"ids": job_ids, "status": "queued", "count": len(job_ids)}


@app.get("/api/media/jobs/{job_id}/file")
def media_job_file(job_id: str):
    job = get_media_job(job_id)
    if not job or not job.get("output_path"):
        raise HTTPException(404, "Generated media file not found")
    path = Path(job["output_path"])
    if not path.exists():
        raise HTTPException(404, "Generated media file is missing")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.delete("/api/media/jobs/{job_id}")
def delete_media_job(job_id: str) -> dict:
    job = get_media_job(job_id)
    if not job:
        raise HTTPException(404, "Media job not found")
    output = job.get("output_path")
    if output:
        try:
            Path(output).unlink(missing_ok=True)
        except Exception:
            pass
    update_media_job(job_id, status="deleted", output_path=None)
    return {"ok": True}
