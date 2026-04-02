import os
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import OUTPUTS_ROOT
from app.models.corrector import (
    append_corrector_activity_log,
    ensure_segment_corrected_csv,
    get_segment_csv_path,
    list_corrector_activity_logs,
    parse_frame_number_from_filename,
    read_corrected_csv_safe,
)
from app.models.schemas import ChangeClassRequest, DeleteIdRequest, MergeIdsRequest, SaveFrameRequest
from app.services import state

router = APIRouter()


@router.get("/correct/segments", summary="List segments available for correction")
def list_segments(base_dir: str, output_dir: str | None = None):
    if not os.path.exists(base_dir):
        raise HTTPException(400, f"Directory not found: {base_dir}")

    out = output_dir or base_dir
    result = []
    for p in sorted(Path(base_dir).iterdir()):
        if p.is_dir():
            corrected = Path(out) / p.name / "trajectories" / f"{p.name}_corrected.csv"
            result.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "status": "done" if corrected.exists() else "todo",
                }
            )
    return result


@router.get("/correct/segments_auto", summary="List all available segments from managed outputs")
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
            result.append(
                {
                    "name": seg_dir.name,
                    "path": str(seg_dir),
                    "base_dir": str(run_dir),
                    "status": "done" if corrected.exists() else "todo",
                }
            )
    return result


@router.get("/correct/frames", summary="List frame images for a segment")
def list_frames(segment: str, base_dir: str, output_dir: str | None = None):
    seg_path = Path(base_dir) / segment
    img_dir = seg_path / "raw_frames"
    if not img_dir.exists():
        img_dir = seg_path / "annotated_frames"
    if not img_dir.exists():
        raise HTTPException(404, f"No frames folder found for segment '{segment}'")

    exts = (".jpg", ".jpeg", ".png")
    filenames = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(exts)])
    frames = [{"filename": f, "index": parse_frame_number_from_filename(f)} for f in filenames]
    append_corrector_activity_log(f"Opened segment '{segment}' with {len(frames)} frame(s)")
    return {"img_dir": str(img_dir), "frames": frames}


@router.get("/correct/frame_image", summary="Serve a specific frame image")
def get_frame_image(img_dir: str, filename: str):
    img_path = Path(img_dir).resolve() / Path(filename).name
    if not img_path.exists():
        raise HTTPException(404, "Frame not found")
    return FileResponse(str(img_path))


@router.get("/correct/trajectories", summary="Get trajectory data for a segment")
def get_trajectories(segment: str, base_dir: str, output_dir: str | None = None):
    try:
        csv_file = get_segment_csv_path(base_dir, segment, output_dir)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    df = pd.read_csv(csv_file)
    if df.empty:
        return {"trajectories": []}

    traj_map: dict[int, list[dict]] = {}
    for _, row in df.iterrows():
        fnum = int(row["frame"])
        box = {
            "id": int(row["id"]),
            "class_name": str(row["class"]),
            "x": float(row["x"]),
            "y": float(row["y"]),
            "w": float(row["w"]),
            "h": float(row["h"]),
        }
        traj_map.setdefault(fnum, []).append(box)

    trajectories = [{"frame": f"frame_{fnum:05d}.png", "boxes": boxes} for fnum, boxes in sorted(traj_map.items())]
    append_corrector_activity_log(f"Loaded trajectories for '{segment}' ({len(trajectories)} frame entries)")
    return {"trajectories": trajectories}


@router.post("/correct/save_frame", summary="Save corrected boxes for one frame")
def save_frame(payload: SaveFrameRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    frame_num = parse_frame_number_from_filename(payload.frame)
    corrected_csv = ensure_segment_corrected_csv(base, payload.segment, payload.output_dir)

    with state.get_corrected_csv_lock():
        df = read_corrected_csv_safe(corrected_csv)
        df = df[df["frame"] != frame_num]

        new_rows = [
            {
                "frame": frame_num,
                "class": b.class_name,
                "id": b.id,
                "x": b.x,
                "y": b.y,
                "w": b.w,
                "h": b.h,
                "x_center": b.x + b.w / 2,
                "y_center": b.y + b.h / 2,
            }
            for b in payload.boxes
        ]
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df = df.drop_duplicates(subset=["frame", "id"], keep="last")
        df.to_csv(corrected_csv, index=False)

    append_corrector_activity_log(
        f"Saved frame '{payload.frame}' in segment '{payload.segment}' with {len(payload.boxes)} box(es)"
    )
    return {"saved": True, "csv_path": str(corrected_csv)}


@router.post("/correct/delete_id", summary="Delete an object ID (frame or globally)")
def delete_id(payload: DeleteIdRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    corrected_csv = ensure_segment_corrected_csv(base, payload.segment, payload.output_dir)
    with state.get_corrected_csv_lock():
        df = read_corrected_csv_safe(corrected_csv)

        if payload.scope == "global":
            df = df[df["id"] != payload.id]
        else:
            frame_num = parse_frame_number_from_filename(payload.frame)
            df = df[~((df["frame"] == frame_num) & (df["id"] == payload.id))]

        df.to_csv(corrected_csv, index=False)

    append_corrector_activity_log(f"Deleted ID {payload.id} ({payload.scope}) in segment '{payload.segment}'")
    return {"deleted": True}


@router.post("/correct/change_class", summary="Change the class label of an object ID")
def change_class(payload: ChangeClassRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    corrected_csv = ensure_segment_corrected_csv(base, payload.segment, payload.output_dir)
    with state.get_corrected_csv_lock():
        df = read_corrected_csv_safe(corrected_csv)
        df.loc[df["id"] == payload.id, "class"] = payload.new_class
        df.to_csv(corrected_csv, index=False)

    append_corrector_activity_log(
        f"Changed class of ID {payload.id} to '{payload.new_class}' in segment '{payload.segment}'"
    )
    return {"updated": True}


@router.post("/correct/merge_ids", summary="Merge one tracking ID into another")
def merge_ids(payload: MergeIdsRequest):
    base = payload.base_dir or ""
    if not base:
        raise HTTPException(400, "base_dir is required")

    corrected_csv = ensure_segment_corrected_csv(base, payload.segment, payload.output_dir)
    with state.get_corrected_csv_lock():
        df = read_corrected_csv_safe(corrected_csv)

        target_rows = df[df["id"] == payload.target_id]
        target_class = target_rows["class"].iloc[0] if not target_rows.empty else None

        df.loc[df["id"] == payload.source_id, "id"] = payload.target_id
        if target_class:
            df.loc[df["id"] == payload.target_id, "class"] = target_class

        df = df.drop_duplicates(subset=["frame", "id"], keep="last")
        df.to_csv(corrected_csv, index=False)

    append_corrector_activity_log(f"Merged ID {payload.source_id} -> {payload.target_id} in segment '{payload.segment}'")
    return {"merged": True}


@router.get("/correct/logs", summary="Get recent Corrector activity logs")
def logs(limit: int = 150):
    return {"logs": list_corrector_activity_logs(limit)}
