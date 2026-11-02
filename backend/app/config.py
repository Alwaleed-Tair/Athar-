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

# JWT secret: taken from ATHAR_JWT_SECRET when set. Otherwise a random
# secret is generated ONCE and persisted in the storage directory
# (chmod 600) so sessions survive a restart. If the storage directory is
# not writable we fall back to an in-memory secret (sessions then end on
# restart) and say so at startup.
JWT_SECRET = os.environ.get("ATHAR_JWT_SECRET")
JWT_SECRET_SOURCE = "env"
if not JWT_SECRET:
    import secrets

    _secret_file = STORAGE_DIR / ".jwt_secret"
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        if _secret_file.exists():
            JWT_SECRET = _secret_file.read_text().strip()
        if not JWT_SECRET:
            JWT_SECRET = secrets.token_hex(32)
            _secret_file.write_text(JWT_SECRET)
            try:
                os.chmod(_secret_file, 0o600)
            except OSError:
                pass
        JWT_SECRET_SOURCE = "file"
    except OSError:
        JWT_SECRET = secrets.token_hex(32)
        JWT_SECRET_SOURCE = "memory"
JWT_SECRET_IS_EPHEMERAL = JWT_SECRET_SOURCE == "memory"

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
BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".msi", ".ps1", ".psm1",
    ".sh", ".js", ".mjs", ".vbs", ".vbe", ".jar", ".apk", ".app", ".lnk",
    ".reg", ".hta", ".cpl", ".php", ".py",
}

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
DEFAULT_ADMIN_FULL_NAME = os.environ.get("ATHAR_ADMIN_FULL_NAME", "System Administrator")

# Fixed timestamp format: UTC, no tzinfo, single consistent format used
# EVERYWHERE a timestamp is stored or hashed.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"

SUPPORTED_LANGS = {"en", "ar"}
DEFAULT_LANG = "en"


# --- Public URL / e-mail ------------------------------------------------
# Base URL used to build the e-mail verification link. Leave empty to
# derive it from the incoming request (works behind Render's proxy).
PUBLIC_URL = os.environ.get("ATHAR_PUBLIC_URL", "").rstrip("/")

# Outgoing e-mail (verification + contact form notifications). Plain SMTP
# so it works with any provider (Brevo, Mailgun, Gmail app password...).
# Nothing is faked: if SMTP_HOST is empty, mail is NOT sent and the API
# says so (see mailer.py); an admin can then activate accounts by hand.
SMTP_HOST = os.environ.get("ATHAR_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("ATHAR_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("ATHAR_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("ATHAR_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("ATHAR_SMTP_FROM", SMTP_USER)
SMTP_SECURITY = os.environ.get("ATHAR_SMTP_SECURITY", "starttls").lower()  # starttls | ssl | none
# Development only: print outgoing mail (incl. verification links) to the
# server log instead of sending. Never enable in production.
MAIL_CONSOLE = os.environ.get("ATHAR_MAIL_CONSOLE", "").lower() in ("1", "true", "yes")
CONTACT_TO = os.environ.get("ATHAR_CONTACT_TO", "")

EMAIL_TOKEN_TTL_HOURS = int(os.environ.get("ATHAR_EMAIL_TOKEN_TTL_HOURS", "24"))
EMAIL_RESEND_COOLDOWN_SECONDS = int(os.environ.get("ATHAR_EMAIL_RESEND_COOLDOWN", "60"))

# --- Login throttling ---------------------------------------------------
LOGIN_MAX_FAILURES = int(os.environ.get("ATHAR_LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCK_SECONDS = int(os.environ.get("ATHAR_LOGIN_LOCK_SECONDS", "900"))

# --- Evidence retention -------------------------------------------------
# Deleting evidence is a soft delete: it disappears from every list, map,
# search and report immediately, but the stored file and its hash are kept
# for this many days (custody integrity / recovery from mistakes) and are
# then permanently purged. The audit-log rows are never removed.
EVIDENCE_RETENTION_DAYS = int(os.environ.get("ATHAR_EVIDENCE_RETENTION_DAYS", "30"))

# Conversation parsing limits
MAX_CHAT_MESSAGES = 100_000
MAX_FULLTEXT_CHARS = 2_000_000

# --- Optional semantic search (embeddings) -------------------------------
# Any OpenAI-compatible /embeddings endpoint. Disabled unless a key is set.
# When used, text of the user's own evidence is sent to this provider.
EMBED_KEY = os.environ.get("ATHAR_EMBED_KEY", "")
EMBED_URL = os.environ.get("ATHAR_EMBED_URL", "https://api.openai.com/v1/embeddings")
EMBED_MODEL = os.environ.get("ATHAR_EMBED_MODEL", "text-embedding-3-small")
SEMANTIC_MIN_SCORE = float(os.environ.get("ATHAR_SEMANTIC_MIN_SCORE", "0.35"))

# --- Optional OCR -----------------------------------------------------------
# Local Tesseract is used when the `tesseract` binary exists (languages from
# OCR_LANGS); otherwise OCR falls back to the AI vision model if a key is set.
OCR_LANGS = os.environ.get("ATHAR_OCR_LANGS", "ara+eng")

# --- Separate provider for IMAGE features (OCR, image descriptions, authenticity) ---
# Reading images needs a vision-capable model. The text provider (DeepSeek by
# default) may not offer one, so images can use another OpenAI-compatible
# endpoint. Each setting falls back to the text-provider value when empty.
#   ATHAR_VISION_URL   e.g. https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
#   ATHAR_VISION_KEY   the key for that provider
#   ATHAR_AI_VISION_MODEL  the vision-capable model id at that provider
VISION_URL = os.environ.get("ATHAR_VISION_URL", "")
VISION_KEY = os.environ.get("ATHAR_VISION_KEY", "")
