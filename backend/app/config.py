"""
Central configuration for ATHAR backend.
All secrets are read from environment variables ONLY. Never hardcode secrets.
"""
import os
from pathlib import Path

# backend/app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Auto-load backend/.env if present (copy .env.example there). Silently
# does nothing if python-dotenv isn't installed or the file is absent.
try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass
STORAGE_DIR = Path(os.environ.get("ATHAR_STORAGE_DIR", str(BACKEND_DIR / "storage")))
EVIDENCE_DIR = STORAGE_DIR / "evidence"
DB_PATH = STORAGE_DIR / "athar.db"

# JWT secret must come from environment. We generate a random one at import
# time ONLY as a last-resort dev fallback so the app doesn't crash on first
# run, but this means tokens won't survive a restart unless ATHAR_JWT_SECRET
# is set explicitly. This is flagged clearly in the README.
JWT_SECRET = os.environ.get("ATHAR_JWT_SECRET")
if not JWT_SECRET:
    import secrets
    JWT_SECRET = secrets.token_hex(32)
    JWT_SECRET_IS_EPHEMERAL = True
else:
    JWT_SECRET_IS_EPHEMERAL = False

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("ATHAR_JWT_EXPIRE_MINUTES", "480"))

# AI analysis key - if absent, the AI analysis feature is disabled.
# Default provider is DeepSeek (OpenAI-compatible chat completions API).
# The API key goes in an Authorization: Bearer header -- see analysis.py.
ATHAR_AI_KEY = os.environ.get("ATHAR_AI_KEY")
ATHAR_AI_URL = os.environ.get("ATHAR_AI_URL", "https://api.deepseek.com/chat/completions")
# Check https://api-docs.deepseek.com/quick_start/pricing for current model ids
# (deepseek-chat and deepseek-reasoner are the two current ones as of writing).
ATHAR_AI_MODEL = os.environ.get("ATHAR_AI_MODEL", "deepseek-chat")
# Separate model for image analysis -- DeepSeek's text models reject image
# input with a 400 error; only this vision-specific model accepts it. It's
# labelled "-exp" (experimental) by DeepSeek with no GA date, so it may be
# renamed or retired -- override via ATHAR_AI_VISION_MODEL if it 404s.
ATHAR_AI_VISION_MODEL = os.environ.get("ATHAR_AI_VISION_MODEL", "deepseek-v4-flash-vision-exp")

# Upload limits
MAX_UPLOAD_BYTES = int(os.environ.get("ATHAR_MAX_UPLOAD_MB", "50")) * 1024 * 1024
BLOCKED_EXTENSIONS = {".exe", ".dll", ".bat", ".ps1", ".sh", ".js", ".jar"}

# Manual evidence categories (investigator-assigned, not AI-suggested).
# Add/remove entries here; i18n.py in the frontend has the display labels.
EVIDENCE_CATEGORIES = {
    "PHYSICAL_EVIDENCE",
    "TESTIMONY",
    "TECHNICAL_REPORT",
    "CORRESPONDENCE",
    "OFFICIAL_DOCUMENT",
    "OTHER",
}
DEFAULT_EVIDENCE_CATEGORY = "OTHER"

# Default bootstrap admin (only used if the users table is empty on startup)
DEFAULT_ADMIN_USERNAME = os.environ.get("ATHAR_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ATHAR_ADMIN_PASSWORD", "ChangeMe123!")

# Fixed timestamp format: UTC, no tzinfo, single consistent format used
# EVERYWHERE a timestamp is stored or hashed.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"

SUPPORTED_LANGS = {"en", "ar"}
DEFAULT_LANG = "en"