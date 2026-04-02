import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.core.config import UPLOADS_ROOT, VIDEO_EXTENSIONS
from app.models.schemas import AnnotatorConfig
from app.services import state
from app.services.job_runner import (
    build_upload_annotator_config,
    get_default_output_dir_for_job,
    run_annotator_job,
)

router = APIRouter()


@router.post("/annotate/start", summary="Launch a batch annotation job")
def start_annotation(cfg: AnnotatorConfig, background_tasks: BackgroundTasks):
    raw_input = Path(cfg.input_dir)
    if not raw_input.exists():
        raise HTTPException(400, f"Input path not found: {cfg.input_dir}")
    if raw_input.is_file() and raw_input.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "If input path is a file, it must be a video (.mp4/.avi/.mov/.mkv/.m4v)")

    jid = str(uuid.uuid4())[:8]
    output_dir = cfg.tracking_runs[0].output_dir if cfg.tracking_runs else str(get_default_output_dir_for_job(jid))
    state.register_job(jid, cfg.model, cfg.input_dir, output_dir)

    background_tasks.add_task(run_annotator_job, jid, cfg, Path(__file__).resolve().parents[2])
    return {"job_id": jid, "message": "Annotation job started"}


@router.post("/annotate/upload-start", summary="Upload a video and launch annotation")
async def annotate_upload_start(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form("yolo11l.pt"),
    confidence: float = Form(0.23),
    fps: str = Form("Original"),
    tracking_runs_json: str = Form(""),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "Uploaded file must be a video (.mp4/.avi/.mov/.mkv/.m4v)")

    jid = str(uuid.uuid4())[:8]
    upload_dir = UPLOADS_ROOT / jid
    output_dir = get_default_output_dir_for_job(jid)

    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or f"upload{ext}").name
    saved_path = upload_dir / filename
    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    state.register_job(jid, model, str(saved_path), str(output_dir))

    cfg = build_upload_annotator_config(upload_dir, model, confidence, fps, tracking_runs_json, output_dir)
    background_tasks.add_task(run_annotator_job, jid, cfg, Path(__file__).resolve().parents[2])

    return {"job_id": jid, "message": "Video uploaded and annotation started"}


@router.get("/annotate/status/{job_id}", summary="Poll job progress and logs")
def get_status(job_id: str):
    job = state.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "logs": job["logs"],
        "output_dir": job.get("output_dir", ""),
    }


@router.post("/annotate/cancel/{job_id}", summary="Cancel a running job")
def cancel_job(job_id: str):
    job = state.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    state.set_job_status(job_id, "cancelled")
    return {"message": "Cancellation requested"}


@router.get("/jobs", summary="List all jobs")
def list_jobs():
    return state.list_jobs()

