import json
import shutil
import sys
import threading
from pathlib import Path

from fastapi import HTTPException

from app.core.config import OUTPUTS_ROOT, TMP_INPUTS_ROOT, TRACKER_MAP, VIDEO_EXTENSIONS, WEIGHTS_ROOT
from app.models.schemas import AnnotatorConfig, TrackingRun
from app.services import state


def prepare_annotator_input(input_path: str, job_id: str, log_cb=None) -> str:
    p = Path(input_path)
    if p.is_dir():
        return str(p)

    if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
        staging_dir = TMP_INPUTS_ROOT / job_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        dst = staging_dir / p.name
        shutil.copy2(p, dst)
        if log_cb:
            log_cb(f"Input file mode detected. Copied to staging directory: {staging_dir}")
        return str(staging_dir)

    raise ValueError(f"Invalid input path: {input_path}")


def parse_tracking_runs_payload(tracking_runs_json: str, resolved_output_dir: Path) -> list[TrackingRun]:
    runs_payload = []
    if tracking_runs_json.strip():
        try:
            runs_payload = json.loads(tracking_runs_json)
            if not isinstance(runs_payload, list):
                raise ValueError("tracking_runs_json must be a JSON array")
        except Exception as e:
            raise HTTPException(400, f"Invalid tracking_runs_json: {e}")

    tracking_runs: list[TrackingRun] = []
    if runs_payload:
        for idx, run in enumerate(runs_payload, start=1):
            if not isinstance(run, dict):
                raise HTTPException(400, f"Run #{idx} must be an object")

            tracker = str(run.get("tracker", "")).strip().lower()
            if tracker not in TRACKER_MAP:
                raise HTTPException(400, f"Run #{idx} has unknown tracker '{tracker}'")

            run_step = int(run.get("step", 1) or 1)
            run_name = str(run.get("name", f"Run {idx}")).strip() or f"Run {idx}"

            tracking_runs.append(
                TrackingRun(
                    name=run_name,
                    tracker=tracker,
                    output_dir=str(resolved_output_dir),
                    step=max(1, run_step),
                    enabled=bool(run.get("enabled", True)),
                )
            )

    if not tracking_runs:
        tracking_runs = [
            TrackingRun(
                name="Run 1",
                tracker="bytetrack",
                output_dir=str(resolved_output_dir),
                step=1,
                enabled=True,
            )
        ]

    return tracking_runs


def resolve_annotator_model_path(model_value: str) -> str:
    model_candidate = Path(model_value)
    if model_candidate.exists():
        return str(model_candidate)

    bundled = WEIGHTS_ROOT / model_value
    if bundled.exists():
        return str(bundled)

    return model_value


def run_annotator_job(jid: str, cfg: AnnotatorConfig, project_root: Path) -> None:
    def log(msg: str) -> None:
        state.append_job_log(jid, msg)
        print(f"[{jid}] {msg}")

    def update_progress(val: float) -> None:
        state.set_job_progress(jid, val)

    def finished(success: bool = True) -> None:
        state.finish_job(jid, success)

    state.set_job_status(jid, "running")

    try:
        venv311_site = project_root / ".venv311" / "Lib" / "site-packages"
        if venv311_site.exists() and str(venv311_site) not in sys.path:
            sys.path.insert(0, str(venv311_site))
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        log(f"Python executable: {sys.executable}")
        log(f"Python prefix: {sys.prefix}")
        from app.models.annotator import Processor  # type: ignore

        prepared_input_dir = prepare_annotator_input(cfg.input_dir, jid, log)

        jobs_list = [
            {
                "name": run.name,
                "sys_type": TRACKER_MAP.get(run.tracker, "System A"),
                "output_dir": run.output_dir,
                "step": run.step,
            }
            for run in cfg.tracking_runs
        ]

        common = {
            "input_dir": prepared_input_dir,
            "model": cfg.model,
            "conf": cfg.confidence,
            "target_fps": cfg.fps,
        }

        proc = Processor(jobs_list, common, update_progress, log, finished)

        def watchdog() -> None:
            import time

            while proc.is_alive():
                if state.is_job_cancelled(jid):
                    proc.stop()
                    break
                time.sleep(1)

        threading.Thread(target=watchdog, daemon=True).start()
        proc.start()
        proc.join()

    except Exception as e:
        log(f"FATAL: {e}")
        state.fail_job(jid)


def build_upload_annotator_config(
    upload_dir: Path,
    model: str,
    confidence: float,
    fps: str,
    tracking_runs_json: str,
    output_dir: Path,
) -> AnnotatorConfig:
    tracking_runs = parse_tracking_runs_payload(tracking_runs_json, output_dir)
    return AnnotatorConfig(
        input_dir=str(upload_dir),
        model=resolve_annotator_model_path(model),
        confidence=confidence,
        fps=fps,
        tracking_runs=tracking_runs,
    )


def get_default_output_dir_for_job(job_id: str) -> Path:
    return OUTPUTS_ROOT / job_id
