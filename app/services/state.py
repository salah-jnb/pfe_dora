import datetime
import threading
from typing import Any

_jobs: dict[str, dict[str, Any]] = {}
_job_lock = threading.Lock()

_corrector_logs: list[str] = []
_corrector_lock = threading.Lock()
_corrected_csv_lock = threading.Lock()


def register_job(jid: str, model: str, input_dir: str, output_dir: str) -> None:
    with _job_lock:
        _jobs[jid] = {
            "job_id": jid,
            "status": "queued",
            "progress": 0.0,
            "logs": [],
            "model": model,
            "input_dir": input_dir,
            "output_dir": output_dir,
            "started_at": datetime.datetime.now().isoformat(),
            "finished_at": None,
        }


def get_job(job_id: str) -> dict[str, Any] | None:
    with _job_lock:
        return _jobs.get(job_id)


def list_jobs() -> list[dict[str, Any]]:
    with _job_lock:
        return [
            {
                "job_id": j["job_id"],
                "status": j["status"],
                "started_at": j["started_at"],
                "finished_at": j.get("finished_at"),
                "model": j["model"],
                "input_dir": j["input_dir"],
                "output_dir": j.get("output_dir", ""),
            }
            for j in _jobs.values()
        ]


def set_job_status(job_id: str, status: str) -> None:
    with _job_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = status


def append_job_log(job_id: str, message: str) -> None:
    with _job_lock:
        if job_id in _jobs:
            _jobs[job_id]["logs"].append(message)


def set_job_progress(job_id: str, progress: float) -> None:
    with _job_lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = round(progress, 1)


def finish_job(job_id: str, success: bool) -> None:
    with _job_lock:
        if job_id in _jobs and _jobs[job_id]["status"] != "cancelled":
            _jobs[job_id]["status"] = "done" if success else "error"
            _jobs[job_id]["finished_at"] = datetime.datetime.now().isoformat()


def fail_job(job_id: str) -> None:
    with _job_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["finished_at"] = datetime.datetime.now().isoformat()


def is_job_cancelled(job_id: str) -> bool:
    with _job_lock:
        return bool(job_id in _jobs and _jobs[job_id]["status"] == "cancelled")


def get_corrected_csv_lock() -> threading.Lock:
    return _corrected_csv_lock


def log_corrector(message: str) -> None:
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    with _corrector_lock:
        _corrector_logs.append(line)
        if len(_corrector_logs) > 300:
            _corrector_logs.pop(0)


def get_corrector_logs(limit: int) -> list[str]:
    n = max(1, min(limit, 300))
    with _corrector_lock:
        return _corrector_logs[-n:]
