from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "workspace_data"
UPLOADS_ROOT = DATA_ROOT / "uploads"
OUTPUTS_ROOT = DATA_ROOT / "outputs"
FRONT_ROOT = APP_ROOT / "templates"
TMP_INPUTS_ROOT = APP_ROOT / "tmp_api_inputs"
WEIGHTS_ROOT = PROJECT_ROOT / "weights"
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}

TRACKER_MAP = {
    "bytetrack": "System A",
    "deepocsort": "DeepOCSORT",
    "strongsort": "StrongSORT",
    "botsort": "BoT-SORT",
}

UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUTS_ROOT.mkdir(parents=True, exist_ok=True)
