"""Query normalization + alias expansion.

Users name Kayfa's programs in many ways — English abbreviations ("AI"),
Arabic transliterations ("فل ستاك"), or full names ("الذكاء الاصطناعي"). The KB
documents use one canonical wording, so a raw query can miss the right file.

`expand_query` detects these aliases and appends the canonical names (in both
Arabic and English) to the query before retrieval/routing, so e.g.

    "عايز اشتغل AI"      -> matches "الذكاء الاصطناعي / Artificial Intelligence"
    "كورس فل ستاك"       -> matches "Full Stack / تطوير الويب المتكامل"
"""

import re

# ── Arabic normalization ─────────────────────────────────────────────────────────
_DIACRITICS = re.compile(r"[ؗ-ًؚ-ْـ]")  # harakat + tatweel


def normalize_ar(text: str) -> str:
    """Lowercase + fold Arabic letter variants so alias triggers match loosely."""
    t = text.lower()
    t = _DIACRITICS.sub("", t)
    t = re.sub(r"[إأآا]", "ا", t)
    t = t.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي").replace("ة", "ه")
    t = re.sub(r"\s+", " ", t)
    return t


# ── Alias groups: (trigger phrases, canonical expansion) ──────────────────────────
# Triggers are matched against the normalized query; expansions are appended raw.
_ALIAS_GROUPS: list[tuple[list[str], str]] = [
    (["ai", "a i", "ذكاء اصطناعي", "الذكاء الاصطناعي", "اي اي", "ايه اي"],
     "الذكاء الاصطناعي Artificial Intelligence AI"),
    (["full stack", "fullstack", "full-stack", "فل ستاك", "فول ستاك", "فلوستاك", "flostack"],
     "Full Stack فل ستاك تطوير الويب المتكامل Web Development"),
    (["data science", "datascience", "data-science", "علم البيانات", "داتا ساينس", "داتا", "تحليل البيانات"],
     "Data Science علم البيانات تحليل البيانات"),
    (["cyber", "cybersecurity", "cyber security", "الامن السيبراني", "امن سيبراني", "سيبراني", "سايبر"],
     "Cyber Security الأمن السيبراني"),
    (["soc", "security operations", "مركز العمليات"],
     "SOC Security Operations Center مركز العمليات الأمنية"),
    (["pentest", "pen test", "penetration", "اختبار الاختراق", "بن تست", "بنتست", "هكر اخلاقي"],
     "Penetration Testing اختبار الاختراق PenTest"),
    (["frontend", "front end", "front-end", "واجهات", "الواجهه الاماميه"],
     "Front-end تطوير الواجهات الأمامية"),
    (["backend", "back end", "back-end", "الخلفيه", "الواجهه الخلفيه"],
     "Back-end تطوير الواجهات الخلفية"),
    (["web", "website", "تطوير الويب", "مواقع", "ويب"],
     "Web Development تطوير الويب"),
    (["diploma", "دبلوم", "دبلومه", "دبلومات"],
     "دبلومة Diploma"),
    (["roadmap", "track", "مسار", "مسارات", "تراك"],
     "مسار تعليمي Roadmap Track"),
    (["price", "prices", "cost", "fee", "fees", "how much",
      "سعر", "أسعار", "اسعار", "تكلفة", "تكلفه", "بكام", "كام", "رسوم", "قديش", "مجاني", "مجانا", "free"],
     "السعر الأسعار التكلفة الرسوم Price USD Cost Fees"),
]

# Pre-normalize triggers once at import.
_NORM_GROUPS = [([normalize_ar(t) for t in triggers], exp) for triggers, exp in _ALIAS_GROUPS]


def expand_query(query: str) -> str:
    """Append canonical course/track names for any aliases found in the query."""
    norm = normalize_ar(query)
    extras: list[str] = []
    for triggers, expansion in _NORM_GROUPS:
        if any(t in norm for t in triggers):
            extras.append(expansion)
    if not extras:
        return query
    return f"{query} | {' '.join(extras)}"
