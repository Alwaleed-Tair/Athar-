"""
AI-assisted analysis layer.

Two independent capabilities:

1. Real EXIF extraction via Pillow. Always runs, no external dependency.
   Status is one of SUCCESS / NO_METADATA / FAILED.

2. Cross-evidence correlation via DeepSeek's API (same device, same
   hash, time proximity, conflicting timestamps, matching document/image
   content). This ONLY runs if ATHAR_AI_KEY is set in the environment. If
   it is not set, the feature returns a clearly-labelled "disabled"
   result -- it never fabricates a result. Every result returned by this
   module (when it does run) is tagged as an automated estimate that
   needs human review; the frontend is responsible for rendering that
   label prominently. Image content is described via a separate
   vision-capable model (see describe_image) since DeepSeek's text
   models reject image input outright.
"""
import json
import re
import urllib.error
import urllib.request
from typing import Optional

from PIL import Image
from PIL import ExifTags

from . import config

# Registers a Pillow "opener" for HEIC/HEIF (the default format iPhones
# save photos in, even when the file is named .jpg). After this call,
# Image.open() transparently handles .heic/.heif files -- no other code
# here needs to know the difference. Safe to skip if the optional
# dependency isn't installed: HEIC files then correctly report FAILED
# instead of crashing the app.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

AI_MODEL = config.ATHAR_AI_MODEL


def extract_exif(file_path: str) -> tuple[str, dict]:
    """Returns (status, exif_dict). status in SUCCESS / NO_METADATA / FAILED."""
    try:
        with Image.open(file_path) as img:
            raw = img.getexif()
            if not raw or len(raw) == 0:
                return "NO_METADATA", {}
            decoded = {}
            for tag_id, value in raw.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                if isinstance(value, bytes):
                    try:
                        value = value.decode("utf-8", errors="replace")
                    except Exception:
                        value = repr(value)
                # Keep it JSON-serialisable
                try:
                    json.dumps(value)
                except TypeError:
                    value = str(value)
                decoded[str(tag)] = value
            if not decoded:
                return "NO_METADATA", {}
            return "SUCCESS", decoded
    except Exception as exc:  # not an image, corrupt file, unsupported format, etc.
        # UnidentifiedImageError subclasses OSError/Exception; any failure
        # to open as an image is reported as FAILED, not silently ignored.
        return "FAILED", {"error": str(exc)}


def ai_enabled() -> bool:
    return bool(config.ATHAR_AI_KEY)


MAX_TEXT_EXCERPT_CHARS = 4000
TEXT_LIKE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log"}


def extract_text_excerpt(file_path: str, ext: str) -> Optional[str]:
    """
    Reads actual text content out of a plain-text file, a PDF, or a Word
    (.docx) document, truncated
    to MAX_TEXT_EXCERPT_CHARS. This is what lets the AI correlation
    features actually use what a report/note SAYS (e.g. "this photo was
    taken on the victim's phone") instead of only structural metadata
    (hash, timestamp, EXIF) -- those alone can miss exactly this kind of
    connection. Returns None for file types this can't read, or on any
    read error (never raises).
    """
    ext = (ext or "").lower()
    try:
        if ext in TEXT_LIKE_EXTENSIONS:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(MAX_TEXT_EXCERPT_CHARS + 1)[:MAX_TEXT_EXCERPT_CHARS]

        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                # Optional dependency not installed -- degrade to no
                # content excerpt rather than crashing the request.
                return None
            reader = PdfReader(file_path)
            chunks = []
            total = 0
            for page in reader.pages:
                text = page.extract_text() or ""
                chunks.append(text)
                total += len(text)
                if total >= MAX_TEXT_EXCERPT_CHARS:
                    break
            return "\n".join(chunks)[:MAX_TEXT_EXCERPT_CHARS] or None

        if ext == ".docx":
            try:
                import docx
            except ImportError:
                return None
            document = docx.Document(file_path)
            chunks = []
            total = 0
            for para in document.paragraphs:
                if para.text:
                    chunks.append(para.text)
                    total += len(para.text)
                    if total >= MAX_TEXT_EXCERPT_CHARS:
                        break
            return "\n".join(chunks)[:MAX_TEXT_EXCERPT_CHARS] or None
    except Exception:
        return None
    return None


MAX_VISION_IMAGE_BYTES = 8 * 1024 * 1024  # keep requests small/fast; not a hard API limit


def _encode_image_for_vision(file_path: str):
    """
    Detects the REAL image format from content via Pillow (not the
    filename extension -- a HEIC photo renamed to .jpg, very common from
    iPhones, must still be recognized as HEIC and converted, or it would
    be sent to the vision API mislabeled and likely rejected/misread).
    Converts HEIC/HEIF (or anything else Pillow can open but the vision
    API can't) to JPEG. Returns (mime, base64_str) or None if the file
    can't be opened as an image or is too large.
    """
    try:
        import base64
        import io

        with Image.open(file_path) as img:
            real_format = (img.format or "").upper()
            if real_format in ("JPEG", "PNG", "GIF", "WEBP"):
                mime = {
                    "JPEG": "image/jpeg",
                    "PNG": "image/png",
                    "GIF": "image/gif",
                    "WEBP": "image/webp",
                }[real_format]
                buf = io.BytesIO()
                img.save(buf, format=real_format)
                raw = buf.getvalue()
            else:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=85)
                raw = buf.getvalue()
                mime = "image/jpeg"

        if len(raw) > MAX_VISION_IMAGE_BYTES:
            return None

        return mime, base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


def _extract_json_object(text: str):
    """
    Best-effort JSON object extraction. The text-model calls elsewhere in
    this file set response_format: json_object, which reliably forces
    pure JSON, but the vision model call does not support that
    parameter, so it sometimes wraps its JSON in prose despite being
    told not to -- prose BEFORE the object ("Based on the image, here is
    my assessment: {...}"), prose AFTER it (extra commentary following a
    complete, valid object), or both. Strips code fences first, then
    falls back to a proper brace-depth scan that finds the FIRST
    complete, balanced {...} object and stops there, ignoring anything
    after it. This is string-aware (a "}" or "{" inside a quoted string
    value, e.g. in the Arabic explanation text, does not affect the
    depth count), unlike a naive find-first-"{"/find-last-"}" approach,
    which breaks as soon as trailing commentary happens to contain its
    own unrelated "}" character. Returns the parsed dict, or None if no
    valid JSON object could be found at all.
    """
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def _call_vision_model(prompt: str, mime: str, b64: str, max_tokens: int = 600):
    """
    Shared vision-model call. Returns (text, finish_reason). finish_reason
    (e.g. "stop", "length", "content_filter") lets a caller distinguish a
    genuinely empty/refused response (the provider's own safety system
    blocking generation, which shows up as empty content with
    finish_reason "content_filter" on many providers) from an ordinary
    parsing problem. Raises on a network/HTTP failure.

    deepseek-v4-flash-vision-exp has "thinking" (hidden chain-of-thought)
    ALWAYS ON by default, and that reasoning is billed against the same
    max_tokens budget as the visible answer -- a harder-to-judge image
    (an AI-generated one especially) can consume the entire budget on
    reasoning and return empty content with finish_reason "length" no
    matter how high max_tokens is raised, since there's no fixed ceiling
    that's guaranteed to be enough for every image. The documented fix
    is to disable thinking outright via extra_body, so the full budget
    goes to the actual answer -- this is far more reliable than chasing
    an ever-larger max_tokens value.
    """
    body = json.dumps(
        {
            "model": config.ATHAR_AI_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        config.ATHAR_AI_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.ATHAR_AI_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = data["choices"][0]
    text = (choice.get("message", {}).get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    return text, finish_reason


def describe_image(file_path: str, ext: str) -> Optional[str]:
    """
    Describes what is actually visible in an image using DeepSeek's
    vision-capable model, so the correlation features can use real visual
    content (a scene, an object, visible text) instead of only EXIF
    metadata.

    Returns None (never raises) if AI is disabled, the file can't be
    opened as an image, it's too large, or the request fails for any
    reason -- callers must treat that as "no visual description
    available", not an error.
    """
    if not ai_enabled():
        return None

    encoded = _encode_image_for_vision(file_path)
    if not encoded:
        return None
    mime, b64 = encoded

    prompt = (
        "Describe ONLY what is factually visible in this image for a "
        "digital forensics record: setting/location type, visible "
        "objects, any visible text, and notable details (e.g. a visible "
        "device, a visible timestamp overlay). Do not guess who any "
        "person is, do not speculate about intent, and do not describe "
        "anything not actually visible. Keep it to 2-3 short sentences."
    )

    try:
        text, _finish_reason = _call_vision_model(prompt, mime, b64, max_tokens=600)
        return text or None
    except Exception:
        # Vision call failing (e.g. the "-exp" model got renamed/retired)
        # must never break the rest of the analysis -- it just means no
        # visual_description for this item this time.
        return None


def analyze_evidence(target: dict, related: list[dict], lang: str = "en") -> dict:
    """
    target / related: plain dicts with at least filename, sha256, exif
    (dict). Correlates target against `related` evidence in the same
    case for: same device, same hash, EXIF DateTime (real capture time)
    proximity, timestamp conflicts. Callers must NOT include uploaded_at
    in these dicts -- it's an administrative artifact of when a file was
    added to this system, not forensic evidence, and past testing showed
    the model would use it as a correlation signal whenever it was
    present, even when explicitly told not to; the reliable fix is to
    not hand it over at all rather than rely on the model resisting the
    temptation to use it.

    Returns {"status": "DISABLED"} if no key is configured -- no
    fabricated findings are ever produced in that case.
    """
    if not ai_enabled():
        return {
            "status": "DISABLED",
            "message_en": "AI analysis is disabled: no ATHAR_AI_KEY configured.",
            "message_ar": "تحليل الذكاء الاصطناعي معطّل: لم يتم ضبط ATHAR_AI_KEY.",
        }

    lang_instruction = (
        'Write the "summary" field and every "explanation" field in Arabic. '
        "Keep the JSON keys themselves and the \"type\" values in English."
        if lang == "ar"
        else 'Write the "summary" field and every "explanation" field in English.'
    )

    prompt = (
        "You are assisting a digital forensics investigator. You are given "
        "one target piece of evidence and a list of other evidence items in "
        "the same case, each with filename, sha256 hash, any extracted "
        "EXIF metadata (including a DateTime field when available -- the "
        "item's real capture timestamp), -- for text files, PDFs, and "
        "Word documents -- a content_excerpt with the item's actual "
        "extracted text content, and -- for images -- a visual_description "
        "of what is actually visible in the photo. TIMING RULE, "
        "IMPORTANT: the only timing signal you are given is the EXIF "
        "DateTime field (when present), which is the item's real-world "
        "capture time. There is no other timestamp available to you, "
        "and none should be assumed or inferred. When DateTime is "
        "missing for one or both items being compared, treat timing as "
        "completely unknown for that pair -- do not reason about or "
        "mention timing at all in that case. Identify concrete "
        "correlations: identical "
        "device/camera model, identical sha256 hash (duplicate file), "
        "close DateTime proximity between items that both have it, a "
        "DateTime that conflicts with what content/context implies, "
        "anything a content_excerpt explicitly states or "
        "references about another item, a device, a person, or an event, "
        "and anything a visual_description shares with another item's "
        "visual_description or content_excerpt (e.g. same visible scene, "
        "same object, same visible text). Text and visual content are "
        "often the strongest signal and must not be ignored just because "
        "there is no metadata match. Do not speculate beyond the given "
        "data. BE CONCISE: each \"explanation\" must be ONE short sentence "
        "(max ~20 words), and \"summary\" must be ONE short sentence (max "
        "~25 words) -- no multi-sentence paragraphs. " + lang_instruction +
        ' Respond ONLY with a JSON object: '
        '{"correlations": [{"evidence_filename": str, "type": str, '
        '"explanation": str}], "summary": str}\n\n'
        f"TARGET:\n{json.dumps(target, ensure_ascii=False)}\n\n"
        f"OTHER EVIDENCE IN CASE:\n{json.dumps(related, ensure_ascii=False)}"
    )

    # DeepSeek is OpenAI-compatible: the key goes in an Authorization
    # header (not the URL), and the request/response shape is the
    # standard chat-completions one, not Gemini's.
    body = json.dumps(
        {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        config.ATHAR_AI_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.ATHAR_AI_KEY}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Surface DeepSeek's own error message (e.g. invalid key, quota,
        # bad model id) instead of just the bare status code.
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            reason = detail.get("error", {}).get("message", str(exc))
        except Exception:
            reason = str(exc)
        return {
            "status": "FAILED",
            "message_en": f"AI analysis request failed: {reason}",
            "message_ar": f"فشل طلب تحليل الذكاء الاصطناعي: {reason}",
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {
            "status": "FAILED",
            "message_en": f"AI analysis request failed: {exc}",
            "message_ar": f"فشل طلب تحليل الذكاء الاصطناعي: {exc}",
        }

    try:
        raw_text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {
            "status": "FAILED",
            "message_en": "AI analysis returned an unexpected response shape.",
            "message_ar": "أعاد تحليل الذكاء الاصطناعي استجابة بشكل غير متوقع.",
        }

    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "status": "FAILED",
            "message_en": "AI analysis returned an unparsable response.",
            "message_ar": "أعاد تحليل الذكاء الاصطناعي استجابة غير قابلة للتحليل.",
        }

    return {
        "status": "SUCCESS",
        "is_automated_estimate": True,  # frontend MUST label this
        "correlations": parsed.get("correlations", []),
        "summary": parsed.get("summary", ""),
    }


def analyze_case_correlations(items: list[dict], lang: str = "en") -> dict:
    """
    Whole-case correlation pass used by the evidence map. Unlike a fixed
    numeric cutoff (e.g. "flag anything within N minutes"), this hands
    the model every item's metadata at once and asks it to judge what is
    genuinely investigatively meaningful given the full picture -- no
    threshold is applied here or anywhere upstream of this call.

    items: list of {id, filename, sha256, uploaded_at, capture_time,
    device} plus an optional content_excerpt (actual extracted text, for
    text files and PDFs -- see extract_text_excerpt) or visual_description
    (images), and -- for some images -- authenticity_check (a prior
    REAL/FAKE/UNSURE verdict from the authenticity-check feature, if one
    was run). capture_time is the real EXIF capture timestamp when
    available and is what the prompt is told to treat as the meaningful
    timing signal; uploaded_at is explicitly NOT (see the prompt).
    Returns {"status": "DISABLED"} with no key configured -- callers must
    fall back to deterministic facts only (identical hash / identical
    device) and must NOT invent a threshold-based edge in that case.
    """
    if not ai_enabled():
        return {
            "status": "DISABLED",
            "message_en": "AI analysis is disabled: no ATHAR_AI_KEY configured.",
            "message_ar": "تحليل الذكاء الاصطناعي معطّل: لم يتم ضبط ATHAR_AI_KEY.",
        }

    lang_instruction = (
        'Write every "explanation" value in Arabic. Keep JSON keys and '
        '"type" values in English.'
        if lang == "ar"
        else 'Write every "explanation" value in English.'
    )

    prompt = (
        "You are assisting a digital forensics investigator studying how a "
        "set of evidence items in one case relate to each other. You are "
        "given every item's numeric id, filename, sha256 hash, "
        "capture_time (the item's real EXIF capture timestamp, if "
        "available -- this is the ONLY timing information you have; "
        "there is no upload/system timestamp, and none should be "
        "assumed), detected device (from EXIF) if any, -- for text "
        "files, PDFs, and Word documents -- a content_excerpt with the "
        "item's actual extracted text content, and -- for images -- a "
        "visual_description of what is actually visible in the photo. "
        "TIMING RULE, IMPORTANT: when capture_time is missing for one or "
        "both items in a pair, treat timing as completely unknown for "
        "that pair -- do not reason about or mention timing at all in "
        "that case. "
        "TEXT AND VISUAL CONTENT ARE OFTEN THE STRONGEST SIGNAL: if a "
        "content_excerpt explicitly states or implies a connection to "
        "another item, a device, a person, or an event (e.g. a report "
        "saying a photo was taken on a specific person's phone, or naming "
        "a suspect also mentioned elsewhere), or if two visual_description "
        "values describe the same scene, object, or visible text, you "
        "MUST surface that as a correlation even if there is no metadata "
        "match at all -- do not require a hash, device, or timing match "
        "before reporting a content- or visual-based relationship. Beyond "
        "content, also identify meaningful device relationships and "
        "genuine capture_time-based patterns: do NOT apply any fixed "
        "numeric cutoff (e.g. do not assume 'within N minutes' is "
        "automatically significant, and do not assume a large gap is "
        "automatically insignificant) -- reason about whether the "
        "pattern is actually noteworthy for an investigator, given the "
        "full context of every item together. "
        "AUTHENTICITY RULE, IMPORTANT: some image items include an "
        "authenticity_check field -- a prior rough, low-confidence AI "
        "verdict (label REAL/FAKE/UNSURE + a short reason) on whether "
        "that specific image may be AI-generated or manipulated. If you "
        "report ANY edge where item_a or item_b has authenticity_check "
        "label FAKE or UNSURE, you MUST say so explicitly inside that "
        "edge's explanation (e.g. \"note: this image was flagged as "
        "possibly fake\") -- never present a link involving a "
        "flagged item as an equal-confidence match without that caveat, "
        "since treating unverified content as reliably connected to "
        "genuine evidence would be misleading. "
        "Do not report a relationship for every possible pair -- only "
        "ones with real investigative significance. Do not speculate "
        "beyond the given data, and do not invent identical-hash or "
        "identical-device relationships (those are computed separately "
        "and given to you only for context). BE CONCISE: each "
        '"explanation" must be ONE short sentence (max ~20 words) -- no '
        "multi-sentence paragraphs. " + lang_instruction + " Respond ONLY "
        'with a JSON object: {"edges": [{"item_a": int, "item_b": int, '
        '"type": str, "explanation": str}]}, where item_a/item_b are the '
        'numeric "id" values from the input and type is a short label '
        'such as "CONTENT_REFERENCE", "VISUAL_MATCH", "TIME_CLUSTER", or '
        '"SEQUENCE_PATTERN".\n\n'
        f"EVIDENCE ITEMS:\n{json.dumps(items, ensure_ascii=False)}"
    )

    body = json.dumps(
        {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        config.ATHAR_AI_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.ATHAR_AI_KEY}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            reason = detail.get("error", {}).get("message", str(exc))
        except Exception:
            reason = str(exc)
        return {
            "status": "FAILED",
            "message_en": f"AI analysis request failed: {reason}",
            "message_ar": f"فشل طلب تحليل الذكاء الاصطناعي: {reason}",
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {
            "status": "FAILED",
            "message_en": f"AI analysis request failed: {exc}",
            "message_ar": f"فشل طلب تحليل الذكاء الاصطناعي: {exc}",
        }

    try:
        raw_text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {
            "status": "FAILED",
            "message_en": "AI analysis returned an unexpected response shape.",
            "message_ar": "أعاد تحليل الذكاء الاصطناعي استجابة بشكل غير متوقع.",
        }

    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "status": "FAILED",
            "message_en": "AI analysis returned an unparsable response.",
            "message_ar": "أعاد تحليل الذكاء الاصطناعي استجابة غير قابلة للتحليل.",
        }

    valid_ids = {item["id"] for item in items}
    edges = []
    for e in parsed.get("edges", []):
        a, b = e.get("item_a"), e.get("item_b")
        if a in valid_ids and b in valid_ids and a != b:
            edges.append(
                {
                    "source": a,
                    "target": b,
                    "type": e.get("type") or "AI_CORRELATION",
                    "explanation": e.get("explanation", ""),
                    "ai_estimated": True,
                }
            )

    return {"status": "SUCCESS", "edges": edges}


def generate_case_summary(case_name: str, items: list[dict], lang: str = "en") -> dict:
    """
    Drafts a formal, evidence-grounded case summary for investigator
    review. This is NOT a legal conclusion and must never be presented
    as one: the prompt explicitly forbids asserting guilt, innocence, or
    anything not directly supported by the given evidence, and every
    fact must be attributed to the evidence it came from. Regardless of
    what the model outputs, the caller (and the frontend) must always
    render this as a labelled automated draft needing human review --
    that label is never optional here, given the "formal/court-style"
    framing the user asked for.

    items: evidence items as built by build_evidence_ai_items (id,
    filename, category, uploaded_at, device, content_excerpt?,
    visual_description?).

    Returns {"status": "DISABLED"} with no key configured -- no summary
    is ever fabricated in that case.
    """
    if not ai_enabled():
        return {
            "status": "DISABLED",
            "message_en": "AI analysis is disabled: no ATHAR_AI_KEY configured.",
            "message_ar": "تحليل الذكاء الاصطناعي معطّل: لم يتم ضبط ATHAR_AI_KEY.",
        }

    lang_instruction = (
        "Write the ENTIRE summary in formal, official Arabic (Modern Standard Arabic)."
        if lang == "ar"
        else "Write the ENTIRE summary in formal, official English."
    )

    prompt = (
        "You are drafting a SHORT, formal case-file summary for a digital "
        "forensics investigator. You are given every evidence item in "
        f'the case "{case_name}": filename, category, upload timestamp, '
        "detected device (from EXIF) if any, -- where available -- "
        "content_excerpt (actual extracted text from a document) or "
        "visual_description (what is actually visible in a photo), and "
        "-- for some images -- authenticity_check: a prior rough, "
        "low-confidence AI verdict (label REAL/FAKE/UNSURE + a short "
        "reason) on whether that specific image may be AI-generated or "
        "manipulated. "
        "AUTHENTICITY RULE, IMPORTANT: if any item has an "
        "authenticity_check with label FAKE or UNSURE, you MUST mention "
        "it explicitly in the facts section, by filename, framed as a "
        "flag needing verification (e.g. \"X was flagged by an automated, "
        "low-confidence check as possibly fake/manipulated and should be "
        "verified before relying on it\") -- never omit this, and never "
        "state or imply that a FAKE/UNSURE-flagged item is confirmed "
        "genuine evidence. "
        "Write exactly 4 short sections, using a plain line of text "
        "followed by a colon as each heading, nothing fancier: (1) case "
        "overview -- 1-2 sentences on what evidence exists; (2) facts -- "
        "each fact in ONE line, attributed to its filename, including "
        "any authenticity flags per the rule above; (3) timeline -- only "
        "if capture_time (not uploaded_at) makes an order meaningful, "
        "otherwise write \"لا يوجد جدول زمني موثوق\" / \"No reliable "
        "timeline\" and skip it; (4) gaps/notes -- ONLY things not "
        "already stated in section 2, as a short list, not a restatement. "
        "LENGTH LIMIT: the entire summary must be under 120 words total "
        "-- be terse, this is a working draft, not a report. Do not "
        "repeat the same fact in more than one section. "
        "FORMATTING: plain text only, no Markdown (no **bold**, no # "
        "headings, no backticks). STRICT RULES: only state what is "
        "directly supported by the given evidence -- never speculate, "
        "never invent names, dates, or facts not present, and NEVER "
        "assert guilt, innocence, or any legal conclusion; this is a "
        "factual summary of evidence, not a verdict, and it is a DRAFT "
        "for a human investigator to review, not a finished document. "
        + lang_instruction + "\n\n"
        f"EVIDENCE ITEMS:\n{json.dumps(items, ensure_ascii=False)}"
    )

    body = json.dumps(
        {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        config.ATHAR_AI_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.ATHAR_AI_KEY}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            reason = detail.get("error", {}).get("message", str(exc))
        except Exception:
            reason = str(exc)
        return {
            "status": "FAILED",
            "message_en": f"Summary generation failed: {reason}",
            "message_ar": f"فشل توليد الملخص: {reason}",
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {
            "status": "FAILED",
            "message_en": f"Summary generation failed: {exc}",
            "message_ar": f"فشل توليد الملخص: {exc}",
        }

    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return {
            "status": "FAILED",
            "message_en": "Summary generation returned an unexpected response shape.",
            "message_ar": "أعاد توليد الملخص استجابة بشكل غير متوقع.",
        }

    if not text:
        return {
            "status": "FAILED",
            "message_en": "Summary generation returned an empty response.",
            "message_ar": "أعاد توليد الملخص استجابة فارغة.",
        }

    return {"status": "SUCCESS", "summary_text": _strip_basic_markdown(text)}


def _strip_basic_markdown(text: str) -> str:
    """
    Defensive cleanup for the case summary: the prompt tells the model
    not to use Markdown, but models sometimes do anyway, and the
    frontend renders this text as plain text (no Markdown engine), so
    leftover '#'/'**' show up as literal characters. Strips heading '#'
    markers and bold/italic '**'/'__'/'*' markers and backticks while
    keeping the underlying text and line breaks intact.
    """
    lines = [re.sub(r"^\s{0,3}#{1,6}\s*", "", line) for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)
    text = text.replace("`", "")
    return text


# Software-field substrings for common editing/beautifying/AI tools. This
# is a small, fixed list, not a general classifier -- it only flags
# tools that happen to write their name into the EXIF Software field,
# and a tampered file can easily have this field blanked or forged, so
# ABSENCE of a match proves nothing. Presence is a genuine, deterministic
# fact (no AI, no guessing): the field literally contains that string.
SUSPICIOUS_EDITING_SOFTWARE = [
    "photoshop", "gimp", "lightroom", "snapseed", "facetune", "faceapp",
    "remini", "picsart", "canva", "affinity photo", "capcut", "pixlr",
    "luminar", "photopea", "meitu", "vsco",
]


def check_exif_authenticity_indicators(exif: dict) -> dict:
    """
    Deterministic (no AI) EXIF-based indicators -- purely factual
    observations about the metadata, not a verdict on authenticity:
    - editing_software_detected: the Software field names a known
      editing/beautifying tool.
    - missing_camera_metadata: no Make/Model at all, which is common
      for screenshots, re-saves, and downloads, and also for a file
      whose EXIF was deliberately stripped -- this field alone cannot
      distinguish those cases.
    """
    software = str(exif.get("Software") or "")
    software_lower = software.lower()
    detected = next((tool for tool in SUSPICIOUS_EDITING_SOFTWARE if tool in software_lower), None)
    has_camera_info = bool(exif.get("Make") or exif.get("Model"))
    return {
        "editing_software_detected": detected is not None,
        "software_field": software or None,
        "missing_camera_metadata": not has_camera_info,
    }


def assess_image_authenticity(file_path: str, lang: str = "en") -> dict:
    """
    A ROUGH, LOW-CONFIDENCE visual triage check for common AI-generation
    or manipulation artifacts, using the same vision model as
    describe_image.

    IMPORTANT LIMITATION, always true regardless of prompt wording:
    general-purpose vision-language models are NOT reliable deepfake
    detectors -- real forensic tools are purpose-trained on large
    labelled datasets specifically for this task. This function exists
    only as an approximate hint the user explicitly asked for with that
    understanding; the frontend MUST present it as low-confidence and
    never as a conclusive result.

    HIDDEN-REASONING NOTE: this model has "thinking" always on by
    default, billed against the same max_tokens budget as the visible
    answer -- harder-to-judge images (AI-generated ones especially,
    exactly the case this feature exists to catch) could consume the
    entire budget on reasoning and return empty content with
    finish_reason "length" no matter how high max_tokens was set, since
    no fixed ceiling is guaranteed to be enough for every image. Fixed
    by disabling thinking outright in _call_vision_model (see its
    docstring) rather than continuing to raise max_tokens.

    Returns {"status": "DISABLED"} if no AI key configured -- no
    assessment is ever fabricated in that case. Returns {"status":
    "NOT_APPLICABLE"} for a file that isn't an image at all.
    """
    if not ai_enabled():
        return {
            "status": "DISABLED",
            "message_en": "AI analysis is disabled: no ATHAR_AI_KEY configured.",
            "message_ar": "تحليل الذكاء الاصطناعي معطّل: لم يتم ضبط ATHAR_AI_KEY.",
        }

    encoded = _encode_image_for_vision(file_path)
    if not encoded:
        return {"status": "NOT_APPLICABLE"}
    mime, b64 = encoded

    lang_instruction = (
        "If you add a short reason, write it in Arabic." if lang == "ar" else "If you add a short reason, write it in English."
    )

    # Deliberately the simplest possible task: one verdict word, not a
    # structured JSON object with an explanation. This was changed from
    # an earlier JSON-based prompt after real-world testing showed the
    # vision model's hidden reasoning could exhaust the token budget on
    # harder (e.g. AI-generated) images before producing any JSON at
    # all -- a one-word answer needs far less generation, and parsing
    # doesn't depend on well-formed JSON, so it's much more robust
    # regardless of how much hidden reasoning the model does first.
    prompt = (
        "You are triaging a photo for a digital forensics investigator. "
        "This is a rough, low-confidence check only -- you are not a "
        "reliable deepfake detector. Reply with exactly ONE WORD first: "
        "REAL if the image looks like an authentic, unedited photo; FAKE "
        "if you notice signs of AI generation or digital manipulation "
        "(inconsistent lighting, warped features, unnatural texture, "
        "garbled text, mismatched reflections); UNSURE if you cannot "
        "tell. " + lang_instruction + " You may add one short reason "
        "after the word, but the word itself must come first and must "
        "be exactly REAL, FAKE, or UNSURE."
    )

    # Automatic retry ladder instead of one fixed guess: an easy (e.g.
    # ordinary real photo) image succeeds on the first, cheapest attempt;
    # a genuinely hard one (AI-generated images especially -- exactly the
    # case this feature exists to catch -- appear to need much more
    # hidden-reasoning headroom before this model produces any visible
    # output) automatically gets more room on each retry instead of
    # failing outright. Only reports failure after every rung is
    # exhausted.
    TOKEN_BUDGET_LADDER = [500, 1500, 3000, 6000]
    raw_text = ""
    finish_reason = None
    last_exc = None
    for budget in TOKEN_BUDGET_LADDER:
        try:
            raw_text, finish_reason = _call_vision_model(prompt, mime, b64, max_tokens=budget)
        except Exception as exc:
            last_exc = exc
            continue
        if raw_text:
            break  # got a real answer -- stop escalating

    if not raw_text and last_exc is not None and finish_reason is None:
        return {
            "status": "FAILED",
            "message_en": f"Authenticity check failed: {last_exc}",
            "message_ar": f"فشل فحص الأصالة: {last_exc}",
        }

    if not raw_text:
        # An EMPTY response (not even a refusal sentence) with
        # finish_reason "content_filter" is a strong, near-certain signal
        # that the provider's own safety system blocked generation
        # before any text was produced -- distinct from a genuine
        # parsing failure, so this is reported as its own case rather
        # than folded into the generic "unusable response" message.
        if finish_reason == "content_filter":
            return {
                "status": "FAILED",
                "message_en": "The AI provider's content filter blocked analysis of this image (empty response, finish_reason=content_filter) -- this is a decision made by the provider, not an error in this app.",
                "message_ar": "نظام تصفية المحتوى عند مزوّد الذكاء الاصطناعي منع تحليل هذي الصورة (رد فارغ، finish_reason=content_filter) — هذا قرار من المزوّد نفسه، مو خطأ بهذا التطبيق.",
            }
        if finish_reason == "length":
            return {
                "status": "FAILED",
                "message_en": f"The model used its entire token budget on every attempt, up to {TOKEN_BUDGET_LADDER[-1]} tokens, without producing any visible output for this specific image. This appears to be a genuine limit of this provider/model for this image, not something this app can work around further.",
                "message_ar": f"استهلك النموذج كل الميزانية بكل المحاولات، حتى {TOKEN_BUDGET_LADDER[-1]} توكن، بدون ما يطلع أي جواب لهذي الصورة تحديداً. يبدو إنه حد حقيقي بهذا المزوّد/الموديل لهذي الصورة، مو شي نقدر نتحايل عليه أكثر من جهة التطبيق.",
            }
        return {
            "status": "FAILED",
            "message_en": f"Authenticity check returned an empty response (finish_reason: {finish_reason or 'unknown'}).",
            "message_ar": f"أعاد فحص الأصالة استجابة فارغة (finish_reason: {finish_reason or 'غير معروف'}).",
        }

    # Lenient keyword parsing: find whichever of REAL/FAKE/UNSURE appears
    # FIRST in the response (case-insensitive), rather than requiring an
    # exact one-word match -- the model may still add punctuation or a
    # short lead-in despite the instruction. Anything after the keyword
    # is kept as an optional explanation.
    upper_text = raw_text.upper()
    positions = {
        kw: upper_text.find(kw) for kw in ("REAL", "FAKE", "UNSURE") if upper_text.find(kw) != -1
    }
    if not positions:
        snippet = raw_text.strip().replace("\n", " ")[:200]
        return {
            "status": "FAILED",
            "message_en": f"Authenticity check returned an unusable response (the model may have declined to analyze this image): {snippet}",
            "message_ar": f"أعاد فحص الأصالة استجابة غير قابلة للاستخدام (قد يكون النموذج رفض تحليل هذي الصورة): {snippet}",
        }
    label = min(positions, key=positions.get)
    explanation = raw_text[positions[label] + len(label) :].strip(" :.-،")

    return {
        "status": "SUCCESS",
        "label": label,
        "explanation": explanation,
    }