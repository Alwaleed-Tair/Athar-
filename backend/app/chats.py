"""
Conversation (chat export) parsing, storage, search, summary statistics and
linking to other evidence.

SECURITY MODEL: message text is UNTRUSTED DATA. It is stored and rendered
as text only (the frontend escapes it), it is never executed, and when it
is shown to an AI model it is wrapped as inert data with explicit
instructions to ignore any instructions it contains (see analysis.py).

The original file is only ever read; parsed messages are stored in a
separate table together with `source_ref` (line / page / row) so every
extracted message can be traced back to its exact place in the original.
"""
import csv
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config, textindex

_BIDI = re.compile(r"[‎‏‪-‮⁦-⁩﻿]")
_AR_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_DATE = r"(\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4})"
_TIME = r"(\d{1,2}:\d{2}(?::\d{2})?)"
_AMPM = r"([AaPp]\.?[Mm]\.?|[صم])?"
# [12/31/23, 10:15:30 PM] Name: msg        (iOS style)
_RE_BRACKET = re.compile(rf"^\[{_DATE}[,،]?\s+{_TIME}\s*{_AMPM}\]\s*(.*)$")
# 12/31/23, 10:15 PM - Name: msg           (Android style)
_RE_DASH = re.compile(rf"^{_DATE}[,،]?\s+{_TIME}\s*{_AMPM}\s+[-–—]\s+(.*)$")
# generic "Name: text" with no timestamp
_RE_SPEAKER = re.compile(r"^([^\s:：][^:：\n]{0,40}?)\s*[:：]\s+(.+)$")

MAX_BODY = 20_000


def _clean(line: str) -> str:
    return _BIDI.sub("", line).translate(_AR_INDIC).replace("،", ",")


def _split_sender(rest: str) -> tuple[Optional[str], str]:
    # sender is everything before the first ": " -- if absent it is a system line
    m = re.match(r"^(.{1,60}?):\s(.*)$", rest, re.S)
    if m:
        return m.group(1).strip(), m.group(2)
    return None, rest


def _parse_date_parts(date_str: str) -> list[int]:
    return [int(x) for x in re.split(r"[/.\-]", date_str)]


def _to_iso(date_str: str, time_str: str, ampm: Optional[str], day_first: bool) -> Optional[str]:
    try:
        a, b, c = _parse_date_parts(date_str)
        if a > 31:       # YYYY-MM-DD
            y, mo, d = a, b, c
        elif day_first:
            d, mo, y = a, b, c
        else:
            mo, d, y = a, b, c
        if y < 100:
            y += 2000
        hh, mm, *ss = [int(x) for x in time_str.split(":")]
        sec = ss[0] if ss else 0
        if ampm:
            pm = ampm.lower().startswith("p") or ampm == "م"
            if pm and hh < 12:
                hh += 12
            if not pm and hh == 12:
                hh = 0
        return datetime(y, mo, d, hh, mm, sec).strftime("%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None


def _detect_day_first(date_strings: list[str]) -> tuple[bool, bool]:
    """Returns (day_first, assumed). dd/mm vs mm/dd is only knowable when a
    component exceeds 12; otherwise we assume day-first and flag it."""
    first_gt12 = second_gt12 = False
    for ds in date_strings:
        try:
            a, b, c = _parse_date_parts(ds)
        except ValueError:
            continue
        if a > 31:
            continue
        if a > 12:
            first_gt12 = True
        if b > 12:
            second_gt12 = True
    if first_gt12:
        return True, False
    if second_gt12:
        return False, False
    return True, True


def parse_timestamped_lines(lines: list[tuple[str, str]]) -> Optional[dict]:
    """lines: [(ref, text)]. Parses WhatsApp-style timestamped transcripts."""
    raw = []  # dicts with date_str/time_str/ampm/sender/body/ref
    cur = None
    for ref, line in lines:
        c = _clean(line.rstrip("\r\n"))
        m = _RE_BRACKET.match(c) or _RE_DASH.match(c)
        if m:
            if cur:
                raw.append(cur)
            date_s, time_s, ampm, rest = m.groups()
            sender, body = _split_sender(rest)
            cur = {"date": date_s, "time": time_s, "ampm": ampm, "sender": sender, "body": body, "ref": ref}
        elif cur is not None:
            cur["body"] += "\n" + c
    if cur:
        raw.append(cur)
    if len(raw) < 2:
        return None
    day_first, assumed = _detect_day_first([r["date"] for r in raw])
    msgs = []
    for r in raw[: config.MAX_CHAT_MESSAGES]:
        msgs.append({
            "sender": r["sender"],
            "ts": _to_iso(r["date"], r["time"], r["ampm"], day_first),
            "ts_raw": f"{r['date']} {r['time']}{(' ' + r['ampm']) if r['ampm'] else ''}",
            "body": r["body"].strip()[:MAX_BODY],
            "source_ref": r["ref"],
        })
    return {"messages": msgs, "truncated": len(raw) > config.MAX_CHAT_MESSAGES, "date_order_assumed": assumed}


def parse_speaker_lines(lines: list[tuple[str, str]]) -> Optional[dict]:
    """Un-timestamped 'Name: text' transcripts. Conservative to avoid
    treating ordinary notes as chats: needs >=3 messages, >=2 speakers and
    most non-empty lines to be speaker lines."""
    msgs, nonempty, cur = [], 0, None
    for ref, line in lines:
        c = _clean(line.rstrip("\r\n"))
        if not c.strip():
            continue
        nonempty += 1
        m = _RE_SPEAKER.match(c)
        if m:
            cur = {"sender": m.group(1).strip(), "ts": None, "ts_raw": "", "body": m.group(2), "source_ref": ref}
            msgs.append(cur)
        elif cur is not None:
            cur["body"] += "\n" + c
    speakers = {m["sender"] for m in msgs}
    if len(msgs) < 3 or len(speakers) < 2 or len(msgs) < 0.6 * nonempty or len(speakers) > 12:
        return None
    for m in msgs:
        m["body"] = m["body"].strip()[:MAX_BODY]
    return {"messages": msgs[: config.MAX_CHAT_MESSAGES], "truncated": len(msgs) > config.MAX_CHAT_MESSAGES,
            "date_order_assumed": False}


def _fix_mojibake(s: str) -> str:
    # Facebook/Instagram exports store UTF-8 bytes as latin-1 escapes.
    if s and any(0x80 <= ord(ch) <= 0xFF for ch in s) and all(ord(ch) <= 0xFF for ch in s):
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


_SENDER_KEYS = ("sender", "sender_name", "from", "author", "name", "user", "المرسل")
_TEXT_KEYS = ("text", "message", "body", "content", "msg", "الرسالة", "النص")
_TIME_KEYS = ("timestamp", "date", "time", "datetime", "timestamp_ms", "created_at", "sent_at", "التاريخ", "الوقت")


def _first(d: dict, keys):
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k in low and low[k] not in (None, ""):
            return low[k]
    return None


def _norm_ts(value) -> tuple[Optional[str], str]:
    if value is None:
        return None, ""
    raw = str(value)
    try:
        if isinstance(value, (int, float)) or re.fullmatch(r"\d{10,13}", raw):
            v = float(raw)
            if v > 1e11:
                v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), raw
        s = raw.replace("Z", "").replace(" ", "T", 1)
        return datetime.fromisoformat(s[:19]).strftime("%Y-%m-%dT%H:%M:%S"), raw
    except (ValueError, OverflowError, OSError):
        return None, raw


def _flatten_text(value) -> str:
    if isinstance(value, list):  # Telegram: mix of str and {"type","text"}
        return "".join(v if isinstance(v, str) else str(v.get("text", "")) for v in value if v)
    return "" if value is None else str(value)


def parse_json_chat(text: str) -> Optional[dict]:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    items = None
    if isinstance(data, dict):
        for k in ("messages", "chat", "conversation", "items"):
            if isinstance(data.get(k), list):
                items = data[k]
                break
    elif isinstance(data, list):
        items = data
    if not items or not all(isinstance(i, dict) for i in items[:20]):
        return None
    msgs = []
    for n, it in enumerate(items[: config.MAX_CHAT_MESSAGES]):
        sender = _first(it, _SENDER_KEYS)
        body = _flatten_text(_first(it, _TEXT_KEYS))
        if sender is None and not body:
            continue
        ts, raw = _norm_ts(_first(it, _TIME_KEYS))
        msgs.append({
            "sender": _fix_mojibake(str(sender)) if sender is not None else None,
            "ts": ts, "ts_raw": raw,
            "body": _fix_mojibake(body).strip()[:MAX_BODY],
            "source_ref": f"json[{n}]",
        })
    msgs = [m for m in msgs if m["body"] or m["sender"]]
    if len(msgs) < 2 or not any(m["body"] for m in msgs):
        return None
    return {"messages": msgs, "truncated": len(items) > config.MAX_CHAT_MESSAGES, "date_order_assumed": False}


def parse_csv_chat(text: str) -> Optional[dict]:
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    except csv.Error:
        return None
    if len(rows) < 2 or not rows[0]:
        return None
    msgs = []
    for n, row in enumerate(rows[: config.MAX_CHAT_MESSAGES], start=2):  # row 1 is the header
        sender = _first(row, _SENDER_KEYS)
        body = _flatten_text(_first(row, _TEXT_KEYS))
        if not body:
            continue
        ts, raw = _norm_ts(_first(row, _TIME_KEYS))
        msgs.append({"sender": str(sender) if sender else None, "ts": ts, "ts_raw": raw,
                     "body": body.strip()[:MAX_BODY], "source_ref": f"row {n}"})
    if len(msgs) < 2 or not any(m["sender"] for m in msgs):
        return None
    return {"messages": msgs, "truncated": len(rows) > config.MAX_CHAT_MESSAGES, "date_order_assumed": False}


def _pdf_lines(path: str):
    from pypdf import PdfReader

    for pno, page in enumerate(PdfReader(path).pages, start=1):
        for ln, line in enumerate((page.extract_text() or "").splitlines(), start=1):
            yield f"p.{pno} l.{ln}", line


def _docx_lines(path: str):
    import docx

    for pno, para in enumerate(docx.Document(path).paragraphs, start=1):
        yield f"para {pno}", para.text


def parse_conversation(path: str, ext: str) -> Optional[dict]:
    """Returns {format, messages, truncated, date_order_assumed, participants}
    or None when the file is not (recognisably) a conversation."""
    ext = (ext or "").lower()
    result, fmt = None, None
    try:
        if ext in (".txt", ".log", ".md"):
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read(config.MAX_FULLTEXT_CHARS * 2)
            lines = [(f"line {i}", ln) for i, ln in enumerate(text.splitlines(), start=1)]
            result, fmt = parse_timestamped_lines(lines), "TEXT_TIMESTAMPED"
            if not result:
                result, fmt = parse_speaker_lines(lines), "TEXT_SPEAKERS"
        elif ext == ".json":
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                result, fmt = parse_json_chat(f.read(config.MAX_FULLTEXT_CHARS * 2)), "JSON"
        elif ext in (".csv", ".tsv"):
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                result, fmt = parse_csv_chat(f.read(config.MAX_FULLTEXT_CHARS * 2)), "CSV"
        elif ext == ".pdf":
            lines = list(_pdf_lines(path))
            result, fmt = parse_timestamped_lines(lines), "PDF_TEXT"
        elif ext == ".docx":
            lines = list(_docx_lines(path))
            result, fmt = parse_timestamped_lines(lines), "DOCX_TEXT"
    except Exception:
        return None
    if not result:
        return None
    participants = Counter(m["sender"] for m in result["messages"] if m["sender"])
    result["format"] = fmt
    result["participants"] = [{"name": n, "messages": c} for n, c in participants.most_common()]
    return result


# --- storage -----------------------------------------------------------------

def store_conversation(conn, evidence_id: int, parsed: dict) -> None:
    conn.execute("DELETE FROM chat_messages WHERE evidence_id = ?", (evidence_id,))
    msgs = parsed["messages"]
    conn.executemany(
        "INSERT INTO chat_messages (evidence_id, idx, sender, ts, ts_raw, body, source_ref) VALUES (?,?,?,?,?,?,?)",
        [(evidence_id, i + 1, m["sender"], m["ts"], m["ts_raw"], m["body"], m["source_ref"]) for i, m in enumerate(msgs)],
    )
    stamps = sorted(m["ts"] for m in msgs if m["ts"])
    conn.execute(
        "INSERT OR REPLACE INTO conversations "
        "(evidence_id, format, participants_json, message_count, first_ts, last_ts, truncated, parsed_at, summary_json) "
        "VALUES (?,?,?,?,?,?,?,?,NULL)",
        (evidence_id, parsed["format"], json.dumps(parsed["participants"], ensure_ascii=False), len(msgs),
         stamps[0] if stamps else None, stamps[-1] if stamps else None, 1 if parsed.get("truncated") else 0,
         datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)),
    )
    conn.commit()


def get_meta(conn, evidence_id: int) -> Optional[dict]:
    r = conn.execute("SELECT * FROM conversations WHERE evidence_id = ?", (evidence_id,)).fetchone()
    if not r:
        return None
    return {
        "format": r["format"],
        "participants": json.loads(r["participants_json"] or "[]"),
        "message_count": r["message_count"],
        "first_ts": r["first_ts"],
        "last_ts": r["last_ts"],
        "truncated": bool(r["truncated"]),
        "parsed_at": r["parsed_at"],
        "summary": json.loads(r["summary_json"]) if r["summary_json"] else None,
    }


def get_messages(conn, evidence_id: int, offset: int = 0, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        "SELECT idx, sender, ts, ts_raw, body, source_ref FROM chat_messages WHERE evidence_id = ? "
        "ORDER BY idx LIMIT ? OFFSET ?", (evidence_id, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def search_messages(conn, evidence_id: int, query: str, limit: int = 100) -> list[dict]:
    q = textindex.normalize(query.strip())
    if not q:
        return []
    out = []
    for r in conn.execute(
        "SELECT idx, sender, ts, ts_raw, body, source_ref FROM chat_messages WHERE evidence_id = ? ORDER BY idx",
        (evidence_id,),
    ):
        hay = textindex.normalize(f"{r['sender'] or ''} {r['body']}")
        if q in hay:
            out.append(dict(r))
            if len(out) >= limit:
                break
    return out


# --- statistics (deterministic; always available, no AI) -----------------------

def compute_stats(conn, evidence_id: int) -> dict:
    rows = conn.execute(
        "SELECT idx, sender, ts, body FROM chat_messages WHERE evidence_id = ? ORDER BY idx", (evidence_id,)
    ).fetchall()
    per_day: Counter = Counter()
    words: Counter = Counter()
    entities: dict[str, set] = {"email": set(), "url": set(), "iban": set(), "phone": set()}
    for r in rows:
        if r["ts"]:
            per_day[r["ts"][:10]] += 1
        words.update(textindex.tokens(r["body"]))
        e = textindex.extract_entities(r["body"])
        for k in entities:
            entities[k] |= e[k]
    busiest = per_day.most_common(1)
    return {
        "message_count": len(rows),
        "top_terms": [{"term": w, "count": c} for w, c in words.most_common(12)],
        "busiest_day": {"date": busiest[0][0], "messages": busiest[0][1]} if busiest else None,
        "days_active": len(per_day),
        "entities": {k: sorted(v)[:20] for k, v in entities.items() if v},
    }


# --- linking to other evidence ---------------------------------------------------

def link_to_evidence(conn, evidence_id: int, case_id: int) -> list[dict]:
    """Messages that deterministically point at OTHER evidence in the SAME
    case: they name another file (or its title), describe its camera/device,
    or share an exact phone/e-mail/URL/IBAN found in that item's text."""
    others = conn.execute(
        "SELECT id, filename, title, exif_json FROM evidence "
        "WHERE case_id = ? AND id != ? AND deleted_at IS NULL", (case_id, evidence_id)).fetchall()
    if not others:
        return []
    other_entities = {}
    for o in others:
        text = conn.execute("SELECT text FROM evidence_text WHERE evidence_id = ?", (o["id"],)).fetchone()
        other_entities[o["id"]] = textindex.extract_entities(text["text"] if text else "")

    links = []
    for m in conn.execute("SELECT idx, body FROM chat_messages WHERE evidence_id = ? ORDER BY idx", (evidence_id,)):
        body_n = textindex.normalize(m["body"])
        ents = textindex.extract_entities(m["body"])
        for o in others:
            names = [n for n in {o["filename"], Path(o["filename"]).stem, o["title"]} if n and len(n) >= 4]
            hit = next((n for n in names if textindex.normalize(n) in body_n), None)
            if hit:
                links.append({"message_idx": m["idx"], "evidence_id": o["id"], "evidence_name": o["title"] or o["filename"],
                              "reason": "FILENAME_MENTION", "value": hit})
                continue
            try:
                exif = json.loads(o["exif_json"] or "{}")
            except ValueError:
                exif = {}
            model = str(exif.get("Model") or "").strip()
            if len(model) >= 4 and textindex.normalize(model) in body_n:
                links.append({"message_idx": m["idx"], "evidence_id": o["id"], "evidence_name": o["title"] or o["filename"],
                              "reason": "DEVICE_MENTION", "value": model})
                continue
            for kind in ("phone", "email", "url", "iban"):
                shared = ents[kind] & other_entities[o["id"]][kind]
                if shared:
                    links.append({"message_idx": m["idx"], "evidence_id": o["id"],
                                  "evidence_name": o["title"] or o["filename"],
                                  "reason": "SHARED_" + kind.upper(), "value": sorted(shared)[0]})
                    break
    return links
