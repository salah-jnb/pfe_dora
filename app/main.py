from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import FRONT_ROOT
from app.views.annotate import router as annotate_router
from app.views.corrector import router as corrector_router
from app.views.front import router as front_router
from app.views.utility import router as utility_router

app = FastAPI(title="Annotation Pipeline API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONT_ROOT.exists():
    app.mount("/front-static", StaticFiles(directory=str(FRONT_ROOT)), name="front-static")

app.include_router(front_router)
app.include_router(annotate_router)
app.include_router(corrector_router)
app.include_router(utility_router)
