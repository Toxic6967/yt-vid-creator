from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import OUTPUT_DIR, ROOT_DIR, settings
from .db import create_job, get_job, init_db, list_jobs, update_job
from .models import GenerateRequest, RegenerateRequest
from .services.editor import ffmpeg_health
from .services.ollama_client import health as ollama_health
from .services.pipeline import run_pipeline

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
    }


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
    job_id = uuid.uuid4().hex[:12]
    create_job(
        {
            "id": job_id,
            "channel_name": payload.channel_name.strip(),
            "niche": payload.niche.strip(),
            "requested_topic": payload.topic,
            "voice": payload.voice,
            "target_seconds": payload.target_seconds,
        }
    )
    threading.Thread(target=run_pipeline, args=(job_id,), daemon=True).start()
    return {"id": job_id, "status": "queued"}


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
    new_id = uuid.uuid4().hex[:12]
    create_job(
        {
            "id": new_id,
            "channel_name": old["channel_name"],
            "niche": old["niche"],
            "requested_topic": payload.topic or old.get("selected_topic") or old.get("requested_topic"),
            "voice": old["voice"],
            "target_seconds": old["target_seconds"],
        }
    )
    threading.Thread(target=run_pipeline, args=(new_id,), daemon=True).start()
    return {"id": new_id, "status": "queued"}


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
