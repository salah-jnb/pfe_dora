from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import FRONT_ROOT

router = APIRouter()


@router.get("/front", summary="Serve Nexus landing page")
def server_side_front():
    index_new_path = FRONT_ROOT / "index_new.html"
    if not index_new_path.exists():
        raise HTTPException(404, "Nexus landing page not found")
    return FileResponse(str(index_new_path))


@router.get("/front/annotateur", summary="Serve annotator upload page")
def server_side_annotateur_front():
    index_path = FRONT_ROOT / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "Annotator front not found")
    return FileResponse(str(index_path))


@router.get("/front/corrector", summary="Serve server-side corrector page")
def server_side_corrector_front():
    corrector_path = FRONT_ROOT / "corrector.html"
    if not corrector_path.exists():
        raise HTTPException(404, "Server-side corrector front not found")
    return FileResponse(str(corrector_path))


@router.get("/front/corrector/editor", summary="Serve server-side corrector editor page")
def server_side_corrector_editor_front():
    editor_path = FRONT_ROOT / "corrector_editor.html"
    if not editor_path.exists():
        raise HTTPException(404, "Server-side corrector editor front not found")
    return FileResponse(str(editor_path))


@router.get("/front/processing", summary="Serve processing status page")
def server_side_processing_front():
    processing_path = FRONT_ROOT / "processing.html"
    if not processing_path.exists():
        raise HTTPException(404, "Processing status page not found")
    return FileResponse(str(processing_path))
