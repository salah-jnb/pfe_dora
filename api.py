"""
FastAPI Backend - Auto Annotator & Corrector
Bridges the Python pipeline (D_Annotator, E_Corrector) with the React (Lovable) frontend.

Install extra deps:
    pip install fastapi uvicorn python-multipart aiofiles

Run:
    .venv_desktop\Scripts\python.exe -m uvicorn api:app --reload --port 8000
"""

import os
import sys
import re
import glob
import shutil
import threading
import datetime
import pandas as pd
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="Annotation Pipeline API", version="2.0.0")

# ----------------------------------------------------------------
# CORS – allow React dev server (Lovable / localhost:3000) to call this API
# ----------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------
# GLOBAL STATE
# ----------------------------------------------------------------
_jobs: dict = {}
_job_lock = threading.Lock()
_corrector_logs: list[str] = []
_corrector_lock = threading.Lock()
_corrected_csv_lock = threading.Lock()

# Map frontend tracker keys -> D_Annotator sys_type values
TRACKER_MAP = {
    "bytetrack":  "System A",
    "deepocsort": "DeepOCSORT",
    "strongsort": "StrongSORT",
    "botsort":    "BoT-SORT",
}

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}
DATA_ROOT = Path(__file__).parent / "workspace_data"
UPLOADS_ROOT = DATA_ROOT / "uploads"
OUTPUTS_ROOT = DATA_ROOT / "outputs"
FRONT_ROOT = Path(__file__).parent / "server_front"

UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUTS_ROOT.mkdir(parents=True, exist_ok=True)

if FRONT_ROOT.exists():
    app.mount("/front-static", StaticFiles(directory=str(FRONT_ROOT)), name="front-static")


def _filename_to_frame_num(filename: str) -> int:
    """Convert 'frame_00042.png' -> 42. Falls back to 0 on parse error."""
    try:
        stem = Path(filename).stem          # 'frame_00042'
        return int(stem.split("_")[1])
    except Exception:
        m = re.search(r"(\d+)", filename)
        return int(m.group(1)) if m else 0


@app.get("/front", summary="Serve Nexus landing page")
def server_side_front():
    index_new_path = FRONT_ROOT / "index_new.html"
    if not index_new_path.exists():
        raise HTTPException(404, "Nexus landing page not found")
    return FileResponse(str(index_new_path))


@app.get("/front/annotateur", summary="Serve annotator upload page")
def server_side_annotateur_front():
    index_path = FRONT_ROOT / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "Annotator front not found")
    return FileResponse(str(index_path))


@app.get("/front/corrector", summary="Serve server-side corrector page")
def server_side_corrector_front():
    corrector_path = FRONT_ROOT / "corrector.html"
    if not corrector_path.exists():
        raise HTTPException(404, "Server-side corrector front not found")
    return FileResponse(str(corrector_path))


@app.get("/front/corrector/editor", summary="Serve server-side corrector editor page")
def server_side_corrector_editor_front():
    editor_path = FRONT_ROOT / "corrector_editor.html"
    if not editor_path.exists():
        raise HTTPException(404, "Server-side corrector editor front not found")
    return FileResponse(str(editor_path))


@app.get("/front/processing", summary="Serve processing status page")
def server_side_processing_front():
    processing_path = FRONT_ROOT / "processing.html"
    if not processing_path.exists():
        raise HTTPException(404, "Processing status page not found")
    return FileResponse(str(processing_path))


def _prepare_annotator_input(input_path: str, job_id: str, log_cb=None) -> str:
    """Return a directory path consumable by D_Annotator.

    If the user gives a single video file, copy it into a per-job staging folder.
    """
    p = Path(input_path)
    if p.is_dir():
        return str(p)

    if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
        staging_dir = Path(__file__).parent / "tmp_api_inputs" / job_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        dst = staging_dir / p.name
        shutil.copy2(p, dst)
        if log_cb:
            log_cb(f"Input file mode detected. Copied to staging directory: {staging_dir}")
        return str(staging_dir)

    raise ValueError(f"Invalid input path: {input_path}")


def _register_job(jid: str, model: str, input_dir: str, output_dir: str):
    with _job_lock:
        _jobs[jid] = {
            "job_id":      jid,
            "status":      "queued",
            "progress":    0.0,
            "logs":        [],
            "model":       model,
            "input_dir":   input_dir,
            "output_dir":  output_dir,
            "started_at":  datetime.datetime.now().isoformat(),
            "finished_at": None,
        }


def _log_corrector(message: str):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    with _corrector_lock:
        _corrector_logs.append(line)
        if len(_corrector_logs) > 300:
            _corrector_logs.pop(0)


def _csv_path(base_dir: str, segment: str, output_dir=None) -> Path:
    """Return the path to the corrected (or original) CSV for a segment."""
    out = Path(output_dir or base_dir)
    corrected = out / segment / "trajectories" / f"{segment}_corrected.csv"
    if corrected.exists():
        return corrected
    originals = list(Path(base_dir, segment, "trajectories").glob("*.csv"))
    if originals:
        return originals[0]
    raise FileNotFoundError(f"No CSV found for segment '{segment}'")


def _ensure_corrected_csv(base_dir: str, segment: str, output_dir=None) -> Path:
    """Return corrected CSV path, creating it from original if needed."""
    out = Path(output_dir or base_dir)
    corrected = out / segment / "trajectories" / f"{segment}_corrected.csv"
    if corrected.exists():
        return corrected
    originals = list(Path(base_dir, segment, "trajectories").glob("*.csv"))
    corrected.parent.mkdir(parents=True, exist_ok=True)
    if not originals:
        pd.DataFrame(
            columns=["frame", "class", "id", "x_center", "y_center", "x", "y", "w", "h"]
        ).to_csv(corrected, index=False)
        return corrected
    shutil.copy2(originals[0], corrected)
    return corrected


def _safe_read_corrected_csv(csv_path: Path) -> pd.DataFrame:
    """Read corrected CSV defensively when concurrent writes may truncate temporarily."""
    columns = ["frame", "class", "id", "x_center", "y_center", "x", "y", "w", "h"]
    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)

    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA
    return df


# ================================================================
# PYDANTIC MODELS  (matching the React TypeScript types exactly)
# ================================================================

class TrackingRun(BaseModel):
    name: str
    tracker: str          # "bytetrack" | "deepocsort" | "strongsort" | "botsort"
    output_dir: str
    step: int = 1
    enabled: bool = True


class AnnotatorConfig(BaseModel):
    input_dir: str
    model: str = "yolo11l.pt"
    confidence: float = 0.23
    fps: str = "Original"
    tracking_runs: List[TrackingRun]


class BoundingBox(BaseModel):
    id: int
    class_name: str
    x: float
    y: float
    w: float
    h: float


class SaveFrameRequest(BaseModel):
    segment: str
    frame: str            # filename, e.g. "frame_00042.png"
    boxes: List[BoundingBox]
    base_dir: Optional[str] = None
    output_dir: Optional[str] = None


class DeleteIdRequest(BaseModel):
    segment: str
    frame: str            # filename
    id: int
    scope: str = "global"  # "global" | "frame"
    base_dir: Optional[str] = None
    output_dir: Optional[str] = None


class ChangeClassRequest(BaseModel):
    segment: str
    id: int
    new_class: str
    base_dir: Optional[str] = None
    output_dir: Optional[str] = None


class MergeIdsRequest(BaseModel):
    segment: str
    source_id: int
    target_id: int
    base_dir: Optional[str] = None
    output_dir: Optional[str] = None


# ================================================================
# 1.  ANNOTATOR  (D_Annotator logic via background thread)
# ================================================================

@app.post("/annotate/start", summary="Launch a batch annotation job")
def start_annotation(cfg: AnnotatorConfig, background_tasks: BackgroundTasks):
    raw_input = Path(cfg.input_dir)
    if not raw_input.exists():
        raise HTTPException(400, f"Input path not found: {cfg.input_dir}")
    if raw_input.is_file() and raw_input.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "If input path is a file, it must be a video (.mp4/.avi/.mov/.mkv/.m4v)")

    import uuid
    jid = str(uuid.uuid4())[:8]
    output_dir = cfg.tracking_runs[0].output_dir if cfg.tracking_runs else str(OUTPUTS_ROOT / jid)
    _register_job(jid, cfg.model, cfg.input_dir, output_dir)

    background_tasks.add_task(_run_annotator, jid, cfg)
    return {"job_id": jid, "message": "Annotation job started"}


@app.post("/annotate/upload-start", summary="Upload a video and launch annotation")
async def annotate_upload_start(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form("yolo11n.pt"),
    confidence: float = Form(0.23),
    fps: str = Form("10"),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "Uploaded file must be a video (.mp4/.avi/.mov/.mkv/.m4v)")

    import uuid
    jid = str(uuid.uuid4())[:8]
    upload_dir = UPLOADS_ROOT / jid
    output_dir = OUTPUTS_ROOT / jid
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or f"upload{ext}").name
    saved_path = upload_dir / filename
    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    _register_job(jid, model, str(saved_path), str(output_dir))

    cfg = AnnotatorConfig(
        input_dir=str(upload_dir),
        model=model,
        confidence=confidence,
        fps=fps,
        tracking_runs=[
            TrackingRun(
                name="Run 1",
                tracker="bytetrack",
                output_dir=str(output_dir),
                step=1,
                enabled=True,
            )
        ],
    )

    background_tasks.add_task(_run_annotator, jid, cfg)
    return {"job_id": jid, "message": "Video uploaded and annotation started"}


@app.get("/annotate/status/{job_id}", summary="Poll job progress and logs")
def get_status(job_id: str):
    with _job_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id":   job["job_id"],
        "status":   job["status"],
        "progress": job["progress"],
        "logs":     job["logs"],
        "output_dir": job.get("output_dir", ""),
    }


@app.post("/annotate/cancel/{job_id}", summary="Cancel a running job")
def cancel_job(job_id: str):
    with _job_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job["status"] = "cancelled"
    return {"message": "Cancellation requested"}


@app.get("/jobs", summary="List all jobs")
def list_jobs():
    with _job_lock:
        return [
            {
                "job_id":      j["job_id"],
                "status":      j["status"],
                "started_at":  j["started_at"],
                "finished_at": j.get("finished_at"),
                "model":       j["model"],
                "input_dir":   j["input_dir"],
                "output_dir":  j.get("output_dir", ""),
            }
            for j in _jobs.values()
        ]


def _run_annotator(jid: str, cfg: AnnotatorConfig):
    def log(msg):
        with _job_lock:
            _jobs[jid]["logs"].append(msg)
        print(f"[{jid}] {msg}")

    def update_progress(val):
        with _job_lock:
            _jobs[jid]["progress"] = round(val, 1)

    def finished(success=True):
        with _job_lock:
            if _jobs[jid]["status"] != "cancelled":
                _jobs[jid]["status"] = "done" if success else "error"
                _jobs[jid]["finished_at"] = datetime.datetime.now().isoformat()

    with _job_lock:
        _jobs[jid]["status"] = "running"

    try:
        venv311_site = Path(__file__).parent / ".venv311" / "Lib" / "site-packages"
        if venv311_site.exists() and str(venv311_site) not in sys.path:
            # Ensure heavy ML deps are importable even when server starts outside venv activation.
            sys.path.insert(0, str(venv311_site))
        sys.path.insert(0, str(Path(__file__).parent))
        log(f"Python executable: {sys.executable}")
        log(f"Python prefix: {sys.prefix}")
        from D_Annotator import Processor  # type: ignore

        prepared_input_dir = _prepare_annotator_input(cfg.input_dir, jid, log)

        jobs_list = [
            {
                "name":       run.name,
                "sys_type":   TRACKER_MAP.get(run.tracker, "System A"),
                "output_dir": run.output_dir,
                "step":       run.step,
            }
            for run in cfg.tracking_runs
        ]

        common = {
            "input_dir":  prepared_input_dir,
            "model":      cfg.model,
            "conf":       cfg.confidence,
            "target_fps": cfg.fps,
        }

        proc = Processor(jobs_list, common, update_progress, log, finished)

        def watchdog():
            import time
            while proc.is_alive():
                with _job_lock:
                    if _jobs[jid]["status"] == "cancelled":
                        proc.stop()
                        break
                time.sleep(1)

        threading.Thread(target=watchdog, daemon=True).start()
        proc.start()
        proc.join()

    except Exception as e:
        log(f"FATAL: {e}")
        with _job_lock:
            _jobs[jid]["status"] = "error"
            _jobs[jid]["finished_at"] = datetime.datetime.now().isoformat()


# ================================================================
# 2.  CORRECTOR
# ================================================================

@app.get("/correct/segments", summary="List segments available for correction")
def list_segments(base_dir: str, output_dir: Optional[str] = None):
    if not os.path.exists(base_dir):
        raise HTTPException(400, f"Directory not found: {base_dir}")
    out = output_dir or base_dir
    result = []
    for p in sorted(Path(base_dir).iterdir()):
        if p.is_dir():
            corrected = Path(out) / p.name / "trajectories" / f"{p.name}_corrected.csv"
            result.append({
                "name":   p.name,
                "path":   str(p),
                "status": "done" if corrected.exists() else "todo",
            })
    return result


@app.get("/correct/segments_auto", summary="List all available segments from managed outputs")
def list_segments_auto():
    result = []
    for run_dir in sorted(OUTPUTS_ROOT.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not run_dir.is_dir():
            continue
        for seg_dir in sorted([p for p in run_dir.iterdir() if p.is_dir()]):
            traj_dir = seg_dir / "trajectories"
            if not traj_dir.exists():
                continue
            corrected = traj_dir / f"{seg_dir.name}_corrected.csv"
            result.append({
                "name": seg_dir.name,
                "path": str(seg_dir),
                "base_dir": str(run_dir),
                "status": "done" if corrected.exists() else "todo",
            })
    return result


@app.get("/correct/frames", summary="List frame images for a segment")
def list_frames(segment: str, base_dir: str, output_dir: Optional[str] = None):
    seg_path = Path(base_dir) / segment
    img_dir = seg_path / "raw_frames"
    if not img_dir.exists():
        img_dir = seg_path / "annotated_frames"
    if not img_dir.exists():
        raise HTTPException(404, f"No frames folder found for segment '{segment}'")

    exts = (".jpg", ".jpeg", ".png")
    filenames = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(exts)])
    frames = [{"filename": f, "index": _filename_to_frame_num(f)} for f in filenames]
    _log_corrector(f"Opened segment '{segment}' with {len(frames)} frame(s)")
    return {"img_dir": str(img_dir), "frames": frames}


@app.get("/correct/frame_image", summary="Serve a specific frame image")
def get_frame_image(img_dir: str, filename: str):
    # Security: prevent path traversal by using only the basename
    img_path = Path(img_dir).resolve() / Path(filename).name
    if not img_path.exists():
        raise HTTPException(404, "Frame not found")
    return FileResponse(str(img_path))


@app.get("/correct/trajectories", summary="Get trajectory data for a segment")
def get_trajectories(segment: str, base_dir: str, output_dir: Optional[str] = None):
    """
    Returns:
    { trajectories: [{frame: "frame_00001.png", boxes: [{id, class_name, x, y, w, h}]}] }
    """
    try:
        csv_path = _csv_path(base_dir, segment, output_dir)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    df = pd.read_csv(csv_path)
    if df.empty:
        return {"trajectories": []}

    traj_map: dict = {}
    for _, row in df.iterrows():
        fnum = int(row["frame"])
        box = {
            "id":         int(row["id"]),
            "class_name": str(row["class"]),
            "x":          float(row["x"]),
            "y":          float(row["y"]),
            "w":          float(row["w"]),
            "h":          float(row["h"]),
        }
        traj_map.setdefault(fnum, []).append(box)

    trajectories = [
        {"frame": f"frame_{fnum:05d}.png", "boxes": boxes}
        for fnum, boxes in sorted(traj_map.items())
    ]
    _log_corrector(f"Loaded trajectories for '{segment}' ({len(trajectories)} frame entries)")
    return {"trajectories": trajectories}


@app.post("/correct/save_frame", summary="Save corrected boxes for one frame")
def save_frame(payload: SaveFrameRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    frame_num = _filename_to_frame_num(payload.frame)
    corrected_csv = _ensure_corrected_csv(base, payload.segment, payload.output_dir)

    with _corrected_csv_lock:
        df = _safe_read_corrected_csv(corrected_csv)
        df = df[df["frame"] != frame_num]

        new_rows = [
            {
                "frame":    frame_num,
                "class":    b.class_name,
                "id":       b.id,
                "x":        b.x,
                "y":        b.y,
                "w":        b.w,
                "h":        b.h,
                "x_center": b.x + b.w / 2,
                "y_center": b.y + b.h / 2,
            }
            for b in payload.boxes
        ]
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df = df.drop_duplicates(subset=["frame", "id"], keep="last")
        df.to_csv(corrected_csv, index=False)
    _log_corrector(f"Saved frame '{payload.frame}' in segment '{payload.segment}' with {len(payload.boxes)} box(es)")
    return {"saved": True, "csv_path": str(corrected_csv)}


@app.post("/correct/delete_id", summary="Delete an object ID (frame or globally)")
def delete_id(payload: DeleteIdRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    corrected_csv = _ensure_corrected_csv(base, payload.segment, payload.output_dir)
    with _corrected_csv_lock:
        df = _safe_read_corrected_csv(corrected_csv)

        if payload.scope == "global":
            df = df[df["id"] != payload.id]
        else:
            frame_num = _filename_to_frame_num(payload.frame)
            df = df[~((df["frame"] == frame_num) & (df["id"] == payload.id))]

        df.to_csv(corrected_csv, index=False)
    _log_corrector(f"Deleted ID {payload.id} ({payload.scope}) in segment '{payload.segment}'")
    return {"deleted": True}


@app.post("/correct/change_class", summary="Change the class label of an object ID")
def change_class(payload: ChangeClassRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    corrected_csv = _ensure_corrected_csv(base, payload.segment, payload.output_dir)
    with _corrected_csv_lock:
        df = _safe_read_corrected_csv(corrected_csv)
        df.loc[df["id"] == payload.id, "class"] = payload.new_class
        df.to_csv(corrected_csv, index=False)
    _log_corrector(f"Changed class of ID {payload.id} to '{payload.new_class}' in segment '{payload.segment}'")
    return {"updated": True}


@app.post("/correct/merge_ids", summary="Merge one tracking ID into another")
def merge_ids(payload: MergeIdsRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    corrected_csv = _ensure_corrected_csv(base, payload.segment, payload.output_dir)
    with _corrected_csv_lock:
        df = _safe_read_corrected_csv(corrected_csv)

        target_rows = df[df["id"] == payload.target_id]
        target_class = target_rows["class"].iloc[0] if not target_rows.empty else None

        df.loc[df["id"] == payload.source_id, "id"] = payload.target_id
        if target_class:
            df.loc[df["id"] == payload.target_id, "class"] = target_class

        df = df.drop_duplicates(subset=["frame", "id"], keep="last")
        df.to_csv(corrected_csv, index=False)
    _log_corrector(f"Merged ID {payload.source_id} -> {payload.target_id} in segment '{payload.segment}'")
    return {"merged": True}


@app.get("/correct/logs", summary="Get recent Corrector activity logs")
def get_corrector_logs(limit: int = 150):
    n = max(1, min(limit, 300))
    with _corrector_lock:
        return {"logs": _corrector_logs[-n:]}


@app.get("/ui/pick-folder", summary="Open native folder picker on server host")
def ui_pick_folder(title: str = "Select folder"):
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title=title) or ""
        root.destroy()
        return {"path": selected}
    except Exception as e:
        raise HTTPException(500, f"Folder picker error: {e}")


@app.get("/ui/pick-video", summary="Open native video picker on server host")
def ui_pick_video(title: str = "Select video"):
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.m4v"),
                ("All files", "*.*"),
            ],
        ) or ""
        root.destroy()
        return {"path": selected}
    except Exception as e:
        raise HTTPException(500, f"Video picker error: {e}")


# ================================================================
# 3.  UTILITY
# ================================================================

@app.get("/health", summary="API health check")
def health():
    return {"status": "ok", "time": datetime.datetime.now().isoformat()}
