"""
Full-text extraction, Arabic-aware normalisation, entity extraction and a
small TF-IDF similarity engine. Everything here is deterministic and runs
locally -- no data leaves the server. All of it is DERIVED from the
original evidence file (opened read-only) and stored separately.

Honest naming: the similarity score is classic lexical TF-IDF cosine, NOT
neural "semantic" search. It finds documents that share distinctive words;
it does not understand meaning or synonyms. The UI says so.
"""
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config

TEXT_LIKE = {".txt", ".md", ".csv", ".json", ".log", ".tsv"}

_AR_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭـ]")
_BIDI_MARKS = re.compile(r"[‎‏‪-‮⁦-⁩﻿]")
_AR_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize(text: str) -> str:
    """Case-fold, strip diacritics/tatweel/bidi marks, unify Arabic letter
    variants and digits, so searches match regardless of spelling variants."""
    if not text:
        return ""
    t = _BIDI_MARKS.sub("", text).translate(_AR_INDIC)
    t = _AR_DIACRITICS.sub("", t)
    t = (t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
          .replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي"))
    return t.lower()


# --- extraction -------------------------------------------------------------

def extract_full_text(path: str, ext: str) -> Optional[str]:
    """Reads the file read-only and returns its text (capped), or None."""
    ext = (ext or "").lower()
    cap = config.MAX_FULLTEXT_CHARS
    try:
        if ext in TEXT_LIKE:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(cap)
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(path)
            parts, total = [], 0
            for page in reader.pages:
                txt = page.extract_text() or ""
                parts.append(txt)
                total += len(txt)
                if total >= cap:
                    break
            out = "\n".join(parts)
            return out[:cap] if out.strip() else None
        if ext == ".docx":
            import docx

            d = docx.Document(path)
            parts = [p.text for p in d.paragraphs if p.text]
            for table in d.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            out = "\n".join(parts)
            return out[:cap] if out.strip() else None
    except Exception:
        return None
    return None


def ensure_text(conn, ev_row) -> str:
    """Cached full text for an evidence row ('' when none can be read)."""
    row = conn.execute("SELECT text FROM evidence_text WHERE evidence_id = ?", (ev_row["id"],)).fetchone()
    if row:
        return row["text"]
    path = config.EVIDENCE_DIR / ev_row["stored_name"]
    text = ""
    if path.exists():
        text = extract_full_text(str(path), Path(ev_row["filename"]).suffix) or ""
    conn.execute(
        "INSERT OR REPLACE INTO evidence_text (evidence_id, text, extracted_at) VALUES (?, ?, ?)",
        (ev_row["id"], text, datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)),
    )
    conn.commit()
    return text


# --- entities ------------------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"https?://[^\s<>\"')]+", re.I)
_IBAN = re.compile(r"\bSA\d{2}[0-9A-Z]{20}\b", re.I)
_PHONE = re.compile(r"(?<![\d.])(?:\+|00)?\d[\d \-]{7,15}\d(?![\d.])")
_DATE_ISO = re.compile(r"\b(20\d{2}|19\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b")
_DATE_DMY = re.compile(r"\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.](20\d{2}|19\d{2})\b")


def extract_entities(text: str) -> dict[str, set]:
    """Deterministic entities useful for linking evidence: e-mails, URLs,
    IBANs, phone numbers, calendar dates. (Person names are not guessed --
    conversation participants are added separately by the caller.)"""
    out: dict[str, set] = {"email": set(), "url": set(), "iban": set(), "phone": set(), "date": set()}
    if not text:
        return out
    t = _BIDI_MARKS.sub("", text).translate(_AR_INDIC)
    out["email"] = {m.lower() for m in _EMAIL.findall(t)}
    out["url"] = {m.rstrip(".,;").lower() for m in _URL.findall(t)}
    out["iban"] = {m.upper() for m in _IBAN.findall(t)}
    scrubbed = _IBAN.sub(" ", t)
    for m in _PHONE.findall(scrubbed):
        digits = re.sub(r"\D", "", m)
        if digits.startswith("00"):
            digits = digits[2:]
        # 9-15 digits; skip things that look like dates/timestamps
        if 9 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{6,}", digits):
            out["phone"].add(digits[-9:] if len(digits) > 9 else digits)  # compare on last 9 digits
    for y, mo, d in _DATE_ISO.findall(t):
        out["date"].add(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")
    for d, mo, y in _DATE_DMY.findall(t):
        out["date"].add(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")
    return out


# --- tokenising / TF-IDF ---------------------------------------------------------

_STOP = set("""
the and for that this with was were are you your from have has had not but all any can will just they them
their there what when where who how about into over than then also been being would could should
في من على الى إلى عن هذا هذه ذلك تلك التي الذي الذين هو هي هم هن انا انت نحن كان كانت يكون ما لا لم لن قد
او أو ثم كل بعد قبل بين حتى مع عند هنا هناك ايضا أيضا لكن بس يا ان إن أن اللي وش ايش شو
""".split())
_TOKEN = re.compile(r"[a-z0-9ء-ي]{3,}")


def tokens(text: str) -> list[str]:
    return [w for w in _TOKEN.findall(normalize(text)) if w not in _STOP and not w.isdigit()]


def tfidf_similarities(docs: dict[int, str], min_score: float = 0.2, top_terms: int = 5) -> dict:
    """docs: {id: text}. Returns {(a, b): (score, [shared top terms])} for
    pairs (a < b) with cosine >= min_score."""
    toks = {i: Counter(tokens(t[:200_000])) for i, t in docs.items() if t and t.strip()}
    toks = {i: c for i, c in toks.items() if sum(c.values()) >= 5}
    n = len(toks)
    if n < 2:
        return {}
    df: Counter = Counter()
    for c in toks.values():
        df.update(c.keys())
    idf = {w: math.log((1 + n) / (1 + d)) + 1.0 for w, d in df.items()}
    vecs, norms = {}, {}
    for i, c in toks.items():
        v = {w: (1 + math.log(cnt)) * idf[w] for w, cnt in c.items()}
        vecs[i] = v
        norms[i] = math.sqrt(sum(x * x for x in v.values())) or 1.0
    ids = sorted(vecs)
    out = {}
    for ai in range(len(ids)):
        for bi in range(ai + 1, len(ids)):
            a, b = ids[ai], ids[bi]
            va, vb = vecs[a], vecs[b]
            small, large = (va, vb) if len(va) < len(vb) else (vb, va)
            shared = [w for w in small if w in large]
            if not shared:
                continue
            dot = sum(va[w] * vb[w] for w in shared)
            score = dot / (norms[a] * norms[b])
            if score >= min_score:
                shared.sort(key=lambda w: va[w] * vb[w], reverse=True)
                out[(a, b)] = (round(score, 3), shared[:top_terms])
    return out


def snippet(text: str, query_norm: str, width: int = 90) -> str:
    """Excerpt of the ORIGINAL text around the first normalised match."""
    if not text:
        return ""
    norm = normalize(text)
    pos = norm.find(query_norm)
    if pos < 0 or len(norm) != len(text):
        # normalisation changed length (rare) -> fall back to a plain search
        pos = text.lower().find(query_norm)
    if pos < 0:
        return text[: width * 2].replace("\n", " ")
    start = max(0, pos - width)
    end = min(len(text), pos + len(query_norm) + width)
    return ("…" if start else "") + text[start:end].replace("\n", " ") + ("…" if end < len(text) else "")
