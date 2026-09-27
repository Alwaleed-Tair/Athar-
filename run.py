import os
import sys
from pathlib import Path

# Safe encoding configuration for Windows consoles (cp1256/cp1252)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"

# Ensure all child subprocesses (uvicorn reloader) inherit the backend in PYTHONPATH
existing_pythonpath = os.environ.get("PYTHONPATH", "")
if str(BACKEND_DIR) not in existing_pythonpath:
    os.environ["PYTHONPATH"] = str(BACKEND_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  Starting ATHAR Platform (منصة أثر الجنائية)...")
    print("  Access URL: http://localhost:8000")
    print("  Admin login: ATHAR_ADMIN_USERNAME / ATHAR_ADMIN_PASSWORD from backend/.env")
    print("               (defaults: admin / ChangeMe123!)")
    print("=" * 60)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, app_dir=str(BACKEND_DIR))
