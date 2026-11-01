"""
Optional "search by meaning". Disabled unless ATHAR_EMBED_KEY is set. Uses any
OpenAI-compatible /embeddings endpoint. When used, the user's query and chunks
of text from THEIR OWN evidence are sent to that provider (disclosed in the
privacy policy); vectors are cached in the database and removed when the
evidence is deleted. Only cases the user is a member of are ever searched.
"""
import hashlib
import json
import math
import urllib.error
import urllib.request

from . import config, relations, textindex

CHUNK_CHARS = 1200
MAX_CHUNKS = 5
BATCH = 16


def enabled() -> bool:
    return bool(config.EMBED_KEY)


class EmbeddingError(Exception):
    pass


def _embed(texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": config.EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        config.EMBED_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.EMBED_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    except Exception as exc:  # never leak provider details
        raise EmbeddingError(type(exc).__name__)


def _chunks(text: str) -> list[str]:
    text = " ".join((text or "").split())
    return [text[i:i + CHUNK_CHARS] for i in range(0, min(len(text), CHUNK_CHARS * MAX_CHUNKS), CHUNK_CHARS)]


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(conn, user_id: int, query: str, case_id: int | None = None, limit: int = 15) -> dict:
    if not enabled():
        return {"status": "DISABLED", "results": []}
    case_ids = relations.accessible_case_ids(conn, user_id)
    if case_id is not None:
        case_ids = [c for c in case_ids if c == case_id]
    if not case_ids:
        return {"status": "SUCCESS", "results": []}
    marks = ",".join("?" * len(case_ids))
    rows = conn.execute(
        f"SELECT e.*, c.name AS case_name FROM evidence e JOIN cases c ON c.id = e.case_id "
        f"WHERE e.case_id IN ({marks}) AND e.deleted_at IS NULL AND e.purged_at IS NULL", case_ids).fetchall()
    try:
        todo, texts = [], {}
        for r in rows:
            text = textindex.ensure_text(conn, r)
            texts[r["id"]] = text
            if not text.strip():
                continue
            h = hashlib.sha256((config.EMBED_MODEL + text[:CHUNK_CHARS * MAX_CHUNKS]).encode()).hexdigest()
            have = conn.execute("SELECT text_hash FROM evidence_embeddings WHERE evidence_id = ?", (r["id"],)).fetchone()
            if not have or have["text_hash"] != h:
                todo.append((r["id"], h, _chunks(text)))
        flat = [(eid, h, ch) for eid, h, chunks in todo for ch in chunks]
        vectors: dict[int, list] = {}
        for i in range(0, len(flat), BATCH):
            part = flat[i:i + BATCH]
            for (eid, _h, _c), vec in zip(part, _embed([c for _e, _h2, c in part])):
                vectors.setdefault(eid, []).append(vec)
        for eid, h, _chunks_ in todo:
            conn.execute("INSERT OR REPLACE INTO evidence_embeddings (evidence_id, model, text_hash, vector_json) VALUES (?,?,?,?)",
                         (eid, config.EMBED_MODEL, h, json.dumps(vectors.get(eid, []))))
        conn.commit()
        qv = _embed([query])[0]
    except EmbeddingError:
        return {"status": "FAILED", "results": []}

    results = []
    for r in rows:
        vr = conn.execute("SELECT vector_json FROM evidence_embeddings WHERE evidence_id = ?", (r["id"],)).fetchone()
        if not vr:
            continue
        vecs = json.loads(vr["vector_json"])
        if not vecs:
            continue
        best_i, best = max(enumerate(_cos(qv, v) for v in vecs), key=lambda t: t[1])
        if best >= config.SEMANTIC_MIN_SCORE:
            chunk = _chunks(texts[r["id"]])[best_i]
            results.append({"evidence_id": r["id"], "case_id": r["case_id"], "case_name": r["case_name"],
                            "filename": r["filename"], "title": r["title"], "score": round(best, 3),
                            "snippet": chunk[:260]})
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "SUCCESS", "results": results[:limit]}
