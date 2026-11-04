from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, integrity
from .database import init_db
from .routers import auth, cases, contact, evidence, reports, search

app = FastAPI(title="ATHAR - Digital Evidence Custody Platform", docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(search.router)
app.include_router(reports.router)
app.include_router(contact.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")
    elif request.url.path.startswith(("/js/", "/css/")) or request.url.path == "/":
        # Always revalidate the app's own code (cheap 304 when unchanged), so a new
        # deploy is picked up immediately instead of browsers running stale JS.
        h["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Never leak stack traces, SQL or paths to the client; details go to the server log only.
    print(f"[ATHAR] unhandled {type(exc).__name__} on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
def _startup():
    print(f"[ATHAR] Storage directory: {config.STORAGE_DIR}")
    init_db()
    if config.JWT_SECRET_SOURCE == "memory":
        print("[ATHAR] WARNING: no ATHAR_JWT_SECRET and storage is not writable; sessions end on every restart.")
    elif config.JWT_SECRET_SOURCE == "file":
        print("[ATHAR] Note: ATHAR_JWT_SECRET not set; using a generated secret persisted in the storage directory. "
              "Set ATHAR_JWT_SECRET explicitly in production.")
    if config.DEFAULT_ADMIN_PASSWORD == "ChangeMe123!":
        print("[ATHAR] WARNING: the bootstrap admin password is still the default 'ChangeMe123!'. Change it.")
    if not config.ATHAR_AI_KEY:
        print("[ATHAR] Note: ATHAR_AI_KEY is not set - AI evidence analysis is disabled.")
    if config.ATHAR_AI_KEY or config.VISION_KEY:
        vurl = config.VISION_URL or config.ATHAR_AI_URL
        print(f"[ATHAR] AI: text via {config.ATHAR_AI_URL.split('/')[2]} ({config.ATHAR_AI_MODEL}); "
              f"images via {vurl.split('/')[2]} ({config.ATHAR_AI_VISION_MODEL})")
    try:
        n = integrity.purge_expired()
        if n:
            print(f"[ATHAR] Retention: permanently removed {n} expired deleted-evidence file(s).")
    except Exception as exc:
        print(f"[ATHAR] Retention purge skipped: {type(exc).__name__}")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# Serve the frontend's static assets (css/js) and index.html on the SAME
# port as the API, as required: one run command, one URL.
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


@app.get("/")
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"), headers={"Cache-Control": "no-cache"})
