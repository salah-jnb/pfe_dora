import re
import shutil
from pathlib import Path

import pandas as pd

from app.services import state


COLUMNS = ["frame", "class", "id", "x_center", "y_center", "x", "y", "w", "h"]


def parse_frame_number_from_filename(filename: str) -> int:
    try:
        stem = Path(filename).stem
        return int(stem.split("_")[1])
    except Exception:
        m = re.search(r"(\d+)", filename)
        return int(m.group(1)) if m else 0


def get_segment_csv_path(base_dir: str, segment: str, output_dir: str | None = None) -> Path:
    out = Path(output_dir or base_dir)
    corrected = out / segment / "trajectories" / f"{segment}_corrected.csv"
    if corrected.exists():
        return corrected

    originals = list(Path(base_dir, segment, "trajectories").glob("*.csv"))
    if originals:
        return originals[0]

    raise FileNotFoundError(f"No CSV found for segment '{segment}'")


def ensure_segment_corrected_csv(base_dir: str, segment: str, output_dir: str | None = None) -> Path:
    out = Path(output_dir or base_dir)
    corrected = out / segment / "trajectories" / f"{segment}_corrected.csv"
    if corrected.exists():
        return corrected

    originals = list(Path(base_dir, segment, "trajectories").glob("*.csv"))
    corrected.parent.mkdir(parents=True, exist_ok=True)
    if not originals:
        pd.DataFrame(columns=COLUMNS).to_csv(corrected, index=False)
        return corrected

    shutil.copy2(originals[0], corrected)
    return corrected


def read_corrected_csv_safe(csv_path_value: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_path_value)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=COLUMNS)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def append_corrector_activity_log(message: str) -> None:
    state.log_corrector(message)


def list_corrector_activity_logs(limit: int) -> list[str]:
    return state.get_corrector_logs(limit)
