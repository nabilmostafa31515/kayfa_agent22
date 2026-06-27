"""
Lightweight, dependency-free country validation for the lead-capture form.

The location field is free-text "City / Country" (bilingual), so we don't try
to validate cities — we just require that a *recognized country* appears
somewhere in the input. That rejects gibberish like "Maghr" while accepting
"Cairo, Egypt", "القاهرة، مصر", "Saudi Arabia", or "الرياض السعودية".

Matching is done over word n-grams (1–5 words) so multi-word countries
("United Arab Emirates", "المملكة العربية السعودية") match, while avoiding
substring false-positives (e.g. "Oman" inside "Romania").
"""

from __future__ import annotations

import re

# ── Country names: English (+ common aliases) and Arabic ──────────────────────
# Not exhaustive on purpose, but covers every sovereign state in English plus
# the Arab world and major countries in Arabic, with the aliases users actually
# type (usa, uk, uae, ksa, …).
_COUNTRY_NAMES: list[str] = [
    # — Arab world (English + Arabic) —
    "egypt", "مصر", "saudi arabia", "ksa", "السعودية", "المملكة العربية السعودية",
    "united arab emirates", "uae", "الامارات", "الإمارات", "الامارات العربية المتحدة",
    "qatar", "قطر", "kuwait", "الكويت", "bahrain", "البحرين", "oman", "عمان", "سلطنة عمان",
    "yemen", "اليمن", "iraq", "العراق", "syria", "سوريا", "سورية", "jordan", "الاردن", "الأردن",
    "lebanon", "لبنان", "palestine", "فلسطين", "libya", "ليبيا", "tunisia", "تونس",
    "algeria", "الجزائر", "morocco", "المغرب", "mauritania", "موريتانيا", "sudan", "السودان",
    "somalia", "الصومال", "djibouti", "جيبوتي", "comoros", "جزر القمر",
    # — Major / common —
    "united states", "usa", "us", "united states of america", "امريكا", "أمريكا", "الولايات المتحدة",
    "united kingdom", "uk", "britain", "great britain", "england", "بريطانيا", "المملكة المتحدة", "انجلترا",
    "canada", "كندا", "france", "فرنسا", "germany", "المانيا", "ألمانيا", "italy", "ايطاليا", "إيطاليا",
    "spain", "اسبانيا", "إسبانيا", "portugal", "البرتغال", "netherlands", "هولندا", "belgium", "بلجيكا",
    "switzerland", "سويسرا", "sweden", "السويد", "norway", "النرويج", "denmark", "الدنمارك",
    "finland", "فنلندا", "ireland", "ايرلندا", "austria", "النمسا", "greece", "اليونان",
    "turkey", "turkiye", "تركيا", "russia", "روسيا", "ukraine", "اوكرانيا", "أوكرانيا",
    "poland", "بولندا", "romania", "رومانيا", "china", "الصين", "japan", "اليابان",
    "south korea", "korea", "كوريا", "كوريا الجنوبية", "india", "الهند", "pakistan", "باكستان",
    "bangladesh", "بنغلاديش", "indonesia", "اندونيسيا", "إندونيسيا", "malaysia", "ماليزيا",
    "singapore", "سنغافورة", "philippines", "الفلبين", "thailand", "تايلاند", "vietnam", "فيتنام",
    "iran", "ايران", "إيران", "afghanistan", "افغانستان", "أفغانستان",
    "australia", "استراليا", "أستراليا", "new zealand", "نيوزيلندا",
    "brazil", "البرازيل", "argentina", "الارجنتين", "الأرجنتين", "mexico", "المكسيك",
    "chile", "تشيلي", "colombia", "كولومبيا", "peru", "بيرو",
    "nigeria", "نيجيريا", "kenya", "كينيا", "ethiopia", "اثيوبيا", "إثيوبيا",
    "south africa", "جنوب افريقيا", "جنوب أفريقيا", "ghana", "غانا", "tanzania", "تنزانيا",
    # — Remaining sovereign states (English) —
    "afghanistan", "albania", "andorra", "angola", "antigua and barbuda", "armenia",
    "azerbaijan", "bahamas", "barbados", "belarus", "belize", "benin", "bhutan",
    "bolivia", "bosnia and herzegovina", "botswana", "brunei", "bulgaria", "burkina faso",
    "burundi", "cabo verde", "cambodia", "cameroon", "central african republic", "chad",
    "congo", "democratic republic of the congo", "costa rica", "croatia", "cuba",
    "cyprus", "czechia", "czech republic", "dominica", "dominican republic", "ecuador",
    "el salvador", "equatorial guinea", "eritrea", "estonia", "eswatini", "fiji",
    "gabon", "gambia", "georgia", "grenada", "guatemala", "guinea", "guinea-bissau",
    "guyana", "haiti", "honduras", "hungary", "iceland", "jamaica", "kazakhstan",
    "kiribati", "kosovo", "kyrgyzstan", "laos", "latvia", "lesotho", "liberia",
    "liechtenstein", "lithuania", "luxembourg", "madagascar", "malawi", "maldives",
    "mali", "malta", "marshall islands", "mauritius", "micronesia", "moldova", "monaco",
    "mongolia", "montenegro", "mozambique", "myanmar", "namibia", "nauru", "nepal",
    "nicaragua", "niger", "north korea", "north macedonia", "palau", "panama",
    "papua new guinea", "paraguay", "rwanda", "saint kitts and nevis", "saint lucia",
    "saint vincent and the grenadines", "samoa", "san marino", "sao tome and principe",
    "senegal", "serbia", "seychelles", "sierra leone", "slovakia", "slovenia",
    "solomon islands", "south sudan", "sri lanka", "suriname", "tajikistan",
    "timor-leste", "togo", "tonga", "trinidad and tobago", "turkmenistan", "tuvalu",
    "uganda", "uruguay", "uzbekistan", "vanuatu", "venezuela", "zambia", "zimbabwe",
]

_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_AR_NORMALIZE = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def _normalize(text: str) -> str:
    """Lowercase, strip Arabic diacritics, and unify common Arabic letter forms
    so 'الإمارات' and 'الامارات' compare equal."""
    text = _AR_DIACRITICS.sub("", text.strip().lower())
    return text.translate(_AR_NORMALIZE)


_COUNTRIES_NORM: set[str] = {_normalize(c) for c in _COUNTRY_NAMES}
_MAX_WORDS = max(len(c.split()) for c in _COUNTRIES_NORM)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)  # letter runs (incl. Arabic), no digits


def is_recognized_country(text: str) -> bool:
    """True when a recognized country name appears as a whole word/phrase in
    ``text``. Empty input is treated as recognized (the field is optional —
    callers decide whether to require it)."""
    if not text or not text.strip():
        return True
    words = _WORD_RE.findall(_normalize(text))
    for n in range(min(_MAX_WORDS, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            if " ".join(words[i:i + n]) in _COUNTRIES_NORM:
                return True
    return False
