from typing import List, Optional

from pydantic import BaseModel


class TrackingRun(BaseModel):
    name: str
    tracker: str
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
    frame: str
    boxes: List[BoundingBox]
    base_dir: Optional[str] = None
    output_dir: Optional[str] = None


class DeleteIdRequest(BaseModel):
    segment: str
    frame: str
    id: int
    scope: str = "global"
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
