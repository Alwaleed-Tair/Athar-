"""
Server-side i18n for audit log messages.

audit_log NEVER stores a pre-built sentence -- only an action code (e.g.
EVIDENCE_REGISTERED) and its JSON params. The human-readable sentence is
built HERE, at read time, from the request's `lang` query parameter. This
means a single stored row can be rendered in either language without any
migration or duplicated storage, and a new language only needs a new
entry in TEMPLATES.
"""
from typing import Optional

from . import config

TEMPLATES = {
    "USER_LOGIN": {
        "en": "{username} logged in",
        "ar": "قام {username} بتسجيل الدخول",
    },
    "USER_LOGIN_FAILED": {
        "en": "Failed login attempt for {username}",
        "ar": "محاولة تسجيل دخول فاشلة لـ {username}",
    },
    "USER_CREATED": {
        "en": "Admin {actor_username} created user {new_username} ({role})",
        "ar": "أنشأ المسؤول {actor_username} المستخدم {new_username} ({role})",
    },
    "USER_REGISTERED": {
        "en": "{full_name} ({username}) created an investigator account",
        "ar": "أنشأ {full_name} ({username}) حساب محقق",
    },
    "PASSWORD_RESET": {
        "en": "Admin {actor_username} reset the password for {target_username}",
        "ar": "أعاد المسؤول {actor_username} تعيين كلمة مرور {target_username}",
    },
    "CASE_CREATED": {
        "en": "{username} created case \"{case_name}\"",
        "ar": "أنشأ {username} القضية \"{case_name}\"",
    },
    "CASE_OPENED": {
        "en": "{username} opened case \"{case_name}\"",
        "ar": "فتح {username} القضية \"{case_name}\"",
    },
    "CASE_DELETED": {
        "en": "{username} archived (deleted) case \"{case_name}\"",
        "ar": "أرشف (حذف) {username} القضية \"{case_name}\"",
    },
    "CASE_SUMMARY_GENERATED": {
        "en": "{username} generated the AI case summary for \"{case_name}\"",
        "ar": "ولّد {username} ملخص القضية بالذكاء الاصطناعي لـ \"{case_name}\"",
    },
    "RESTRICTED_LINK_DETECTED": {
        "en": "Evidence \"{filename}\" matches evidence in a case {username} has no access to ({reasons}); details withheld",
        "ar": "الدليل \"{filename}\" يطابق دليلاً في قضية لا يملك {username} صلاحيتها ({reasons})، والتفاصيل محجوبة",
    },
    "ACCESS_REQUESTED": {
        "en": "{username} asked the owner of the matching case for access (from \"{filename}\", {reasons})",
        "ar": "طلب {username} الوصول من مالك القضية المطابقة (انطلاقاً من \"{filename}\"، {reasons})",
    },
    "ACCESS_REQUEST_RECEIVED": {
        "en": "{requester_username} asked for access to this case: their evidence matches \"{filename}\" ({reasons})",
        "ar": "طلب {requester_username} الوصول إلى هذه القضية: دليله يطابق \"{filename}\" ({reasons})",
    },
    "ACCESS_REQUEST_APPROVED": {
        "en": "{actor_username} approved the access request of {requester_username}",
        "ar": "قبل {actor_username} طلب وصول {requester_username}",
    },
    "ACCESS_REQUEST_DECLINED": {
        "en": "{actor_username} declined the access request of {requester_username}",
        "ar": "رفض {actor_username} طلب وصول {requester_username}",
    },
    "MEMBER_ADDED": {
        "en": "{actor_username} granted {member_username} access to this case",
        "ar": "منح {actor_username} المستخدم {member_username} صلاحية الوصول لهذه القضية",
    },
    "EVIDENCE_UPLOADED": {
        "en": "{username} uploaded evidence \"{filename}\" (sha256 {sha256_short}…)",
        "ar": "رفع {username} الدليل \"{filename}\" (بصمة {sha256_short}…)",
    },
    "EVIDENCE_CATEGORY_CHANGED": {
        "en": "{username} set the category of \"{filename}\" to {category}",
        "ar": "غيّر {username} تصنيف \"{filename}\" إلى {category}",
    },
    "EVIDENCE_OPENED": {
        "en": "{username} inspected evidence \"{filename}\"",
        "ar": "فتح {username} الدليل \"{filename}\" للمعاينة",
    },
    "EVIDENCE_DOWNLOADED": {
        "en": "{username} downloaded evidence \"{filename}\"",
        "ar": "نزّل {username} الدليل \"{filename}\"",
    },
    "EVIDENCE_ANALYZED": {
        "en": "{username} ran AI analysis on evidence \"{filename}\"",
        "ar": "شغّل {username} تحليل الذكاء الاصطناعي على الدليل \"{filename}\"",
    },
    "EVIDENCE_AUTHENTICITY_CHECKED": {
        "en": "{username} ran an authenticity check on evidence \"{filename}\"",
        "ar": "شغّل {username} فحص الأصالة على الدليل \"{filename}\"",
    },
    "EMAIL_VERIFIED": {
        "en": "{username} verified their e-mail address",
        "ar": "وثّق {username} بريده الإلكتروني",
    },
    "EMAIL_VERIFIED_BY_ADMIN": {
        "en": "Admin {actor_username} manually activated the account of {target_username}",
        "ar": "فعّل المسؤول {actor_username} حساب {target_username} يدوياً",
    },
    "ACCOUNT_APPROVED": {
        "en": "Admin {actor_username} approved the account of {target_username}",
        "ar": "وافق المسؤول {actor_username} على حساب {target_username}",
    },
    "ACCOUNT_REJECTED": {
        "en": "Admin {actor_username} rejected the registration request of {target_username}",
        "ar": "رفض المسؤول {actor_username} طلب تسجيل {target_username}",
    },
    "PROFILE_UPDATED": {
        "en": "{username} updated their profile (name \"{full_name}\")",
        "ar": "حدّث {username} ملفه الشخصي (الاسم \"{full_name}\")",
    },
    "PASSWORD_CHANGED": {
        "en": "{username} changed their password",
        "ar": "غيّر {username} كلمة المرور",
    },
    "PASSWORD_RESET_BY_EMAIL": {
        "en": "{username} reset their password using an e-mailed link",
        "ar": "أعاد {username} تعيين كلمة المرور عبر رابط أُرسل إلى بريده",
    },
    "ACCOUNT_DELETED": {
        "en": "{username} deleted their account (cases: {case_action})",
        "ar": "حذف {username} حسابه (القضايا: {case_action})",
    },
    "EVIDENCE_OCR_RUN": {
        "en": "{username} ran text extraction (OCR, {method}) on \"{filename}\"",
        "ar": "شغّل {username} استخراج النص (OCR، {method}) على \"{filename}\"",
    },
    "EVIDENCE_UPDATED": {
        "en": "{username} edited the details of \"{filename}\" ({fields})",
        "ar": "عدّل {username} بيانات الدليل \"{filename}\" ({fields})",
    },
    "EVIDENCE_DELETED": {
        "en": "{username} deleted evidence \"{filename}\" (sha256 {sha256_short}…); the file is retained until {purge_after}",
        "ar": "حذف {username} الدليل \"{filename}\" (بصمة {sha256_short}…)؛ يُحتفظ بالملف حتى {purge_after}",
    },
    "EVIDENCE_PURGED": {
        "en": "Retention period ended: stored file of deleted evidence \"{filename}\" (sha256 {sha256_short}…) was permanently removed",
        "ar": "انتهت مدة الاحتفاظ: أُزيل نهائياً الملف المخزّن للدليل المحذوف \"{filename}\" (بصمة {sha256_short}…)",
    },
    "EVIDENCE_INTEGRITY_CHECKED": {
        "en": "{username} verified the file integrity of \"{filename}\": {result}",
        "ar": "تحقق {username} من سلامة ملف الدليل \"{filename}\": {result}",
    },
    "EVIDENCE_CONVERSATION_PARSED": {
        "en": "Conversation content of \"{filename}\" was extracted (messages: {count}; format: {format})",
        "ar": "استُخرج محتوى المحادثة من \"{filename}\" (عدد الرسائل: {count}؛ الصيغة: {format})",
    },
    "CONVERSATION_SUMMARY_GENERATED": {
        "en": "{username} generated a conversation summary for \"{filename}\"",
        "ar": "ولّد {username} ملخص المحادثة للدليل \"{filename}\"",
    },
    "REPORT_GENERATED": {
        "en": "{username} exported the PDF report for case \"{case_name}\" (evidence items: {evidence_count}; chain: {intact})",
        "ar": "صدّر {username} التقرير القانوني (PDF) للقضية \"{case_name}\" (عدد الأدلة: {evidence_count}؛ حالة السلسلة: {intact})",
    },
    "CASE_SEARCHED": {
        "en": "{username} searched case \"{case_name}\"",
        "ar": "بحث {username} في القضية \"{case_name}\"",
    },
    "MEMBER_REMOVED": {
        "en": "{actor_username} removed {member_username} from this case",
        "ar": "أزال {actor_username} المستخدم {member_username} من هذه القضية",
    },
    "CHAIN_VERIFIED": {
        "en": "{username} ran a chain-of-custody verification: {intact}",
        "ar": "شغّل {username} تحققاً من سلسلة العهدة: {intact}",
    },
}

# Display names for the fixed evidence-category codes (see
# config.EVIDENCE_CATEGORIES) -- used to localize the category name
# inside audit messages, since audit_log stores the raw code (e.g.
# OFFICIAL_DOCUMENT), not a sentence.
CATEGORY_LABELS = {
    "PHYSICAL_EVIDENCE": {"en": "Physical Evidence", "ar": "دليل مادي"},
    "TESTIMONY": {"en": "Testimony", "ar": "شهادة"},
    "TECHNICAL_REPORT": {"en": "Technical Report", "ar": "تقرير فني"},
    "CORRESPONDENCE": {"en": "Correspondence", "ar": "مراسلات"},
    "OFFICIAL_DOCUMENT": {"en": "Official Document", "ar": "وثيقة رسمية"},
    "OTHER": {"en": "Other", "ar": "أخرى"},
}


INTACT_LABELS = {
    True: {"en": "intact", "ar": "سليمة"},
    False: {"en": "TAMPERING DETECTED", "ar": "رُصد تلاعب"},
}
FORMAT_LABELS = {
    "TEXT_TIMESTAMPED": {"en": "timestamped text export", "ar": "تصدير نصي بالأوقات"},
    "TEXT_SPEAKERS": {"en": "speaker transcript", "ar": "نص محادثة (المتحدث: الرسالة)"},
    "JSON": {"en": "JSON export", "ar": "تصدير JSON"},
    "CSV": {"en": "CSV", "ar": "CSV"},
    "PDF_TEXT": {"en": "PDF text", "ar": "نص PDF"},
    "DOCX_TEXT": {"en": "Word text", "ar": "نص Word"},
    "OCR_TEXT": {"en": "text read from an image (OCR)", "ar": "نص مقروء من صورة (OCR)"},
}
CASE_ACTION_LABELS = {
    "TRANSFERRED": {"en": "ownership transferred to another member", "ar": "نُقلت الملكية إلى عضو آخر"},
    "ARCHIVED": {"en": "archived", "ar": "أُرشفت"},
    "NONE": {"en": "none", "ar": "لا يوجد"},
}
OCR_METHOD_LABELS = {
    "TESSERACT": {"en": "Tesseract", "ar": "Tesseract"},
    "AI_VISION": {"en": "AI vision", "ar": "رؤية الذكاء الاصطناعي"},
    "NONE": {"en": "none", "ar": "لا يوجد"},
}
_MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "ar": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
}


def _pretty_date(value: str, lang: str) -> str:
    """'2026-12-01' -> '1 Dec 2026' / '1 ديسمبر 2026' (anything else is returned as is)."""
    try:
        y, m, d = (int(x) for x in str(value)[:10].split("-"))
        return f"{d} {_MONTHS[lang][m - 1]} {y}"
    except (ValueError, IndexError):
        return str(value)


RESULT_LABELS = {
    "MATCH": {"en": "hash matches the value recorded at upload", "ar": "البصمة مطابقة للقيمة المسجلة عند الرفع"},
    "MISMATCH": {"en": "HASH MISMATCH - file differs from the recorded original", "ar": "عدم تطابق - الملف يختلف عن الأصل المسجل"},
    "MISSING": {"en": "stored file is missing", "ar": "الملف المخزّن مفقود"},
}


REASON_LABELS = {
    "IDENTICAL_FILE": {"en": "identical file", "ar": "ملف مطابق"},
    "SHARED_PHONE": {"en": "same phone number", "ar": "رقم هاتف مشترك"},
    "SHARED_EMAIL": {"en": "same e-mail", "ar": "بريد إلكتروني مشترك"},
    "SHARED_IBAN": {"en": "same IBAN", "ar": "آيبان مشترك"},
}


def _fallback(action: str, lang: str) -> str:
    if lang == "ar":
        return f"سجل من نوع «{action}» (تفاصيله غير متاحة أو تالفة)"
    return f'Record of type "{action}" (details unavailable or corrupted)'


def build_message(action: str, params: dict, lang: Optional[str]) -> str:
    lang = lang if lang in config.SUPPORTED_LANGS else config.DEFAULT_LANG
    entry = TEMPLATES.get(action)
    if entry is None:
        return _fallback(action, lang)
    template = entry.get(lang, entry.get(config.DEFAULT_LANG, action))
    if "category" in params and params["category"] in CATEGORY_LABELS:
        params = {**params, "category": CATEGORY_LABELS[params["category"]].get(lang, params["category"])}
    params = dict(params)
    if "intact" in params:
        params["intact"] = INTACT_LABELS[bool(params["intact"])][lang]
    if params.get("format") in FORMAT_LABELS:
        params["format"] = FORMAT_LABELS[params["format"]][lang]
    if params.get("case_action") in CASE_ACTION_LABELS:
        params["case_action"] = CASE_ACTION_LABELS[params["case_action"]][lang]
    if params.get("method") in OCR_METHOD_LABELS:
        params["method"] = OCR_METHOD_LABELS[params["method"]][lang]
    if "reason_codes" in params:
        codes = params.get("reason_codes") or []
        sep = "، " if lang == "ar" else ", "
        params["reasons"] = sep.join(REASON_LABELS.get(c, {}).get(lang, str(c)) for c in codes) or "-"
    if "purge_after" in params:
        params["purge_after"] = _pretty_date(params["purge_after"], lang)
    if "result" in params and params["result"] in RESULT_LABELS:
        params = {**params, "result": RESULT_LABELS[params["result"]].get(lang, params["result"])}
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        # Missing/corrupted params (e.g. a tampered row): say so in the user's
        # language instead of showing a raw action code.
        return _fallback(action, lang)
