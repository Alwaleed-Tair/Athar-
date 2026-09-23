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
    "CHAIN_VERIFIED": {
        "en": "{username} ran a chain-of-custody verification (intact: {intact})",
        "ar": "شغّل {username} تحققاً من سلسلة العهدة (سليمة: {intact})",
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


def build_message(action: str, params: dict, lang: Optional[str]) -> str:
    lang = lang if lang in config.SUPPORTED_LANGS else config.DEFAULT_LANG
    entry = TEMPLATES.get(action)
    if entry is None:
        return action
    template = entry.get(lang, entry.get(config.DEFAULT_LANG, action))
    if "category" in params and params["category"] in CATEGORY_LABELS:
        params = {**params, "category": CATEGORY_LABELS[params["category"]].get(lang, params["category"])}
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        # Missing param for an older row shape -- fall back to the action
        # code rather than crashing the whole audit view.
        return action