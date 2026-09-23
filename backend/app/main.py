from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import config
from .database import init_db
from .routers import auth, cases, evidence

app = FastAPI(title="ATHAR - Digital Evidence Custody Platform")

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(evidence.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@app.on_event("startup")
def _startup():
    print(f"[ATHAR] Storage directory: {config.STORAGE_DIR}")
    init_db()
    if config.JWT_SECRET_IS_EPHEMERAL:
        print(
            "[ATHAR] WARNING: ATHAR_JWT_SECRET is not set in the environment. "
            "Using a randomly generated in-memory secret, which means all "
            "sessions will be invalidated on restart. Set ATHAR_JWT_SECRET "
            "in your .env for a stable secret."
        )
    if not config.ATHAR_AI_KEY:
        print("[ATHAR] Note: ATHAR_AI_KEY is not set - AI evidence analysis is disabled.")


# Serve the frontend's static assets (css/js) and index.html on the SAME
# port as the API, as required: one run command, one URL.
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


@app.get("/")
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))