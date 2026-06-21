"""Lead qualification logic — scores user intent from conversation signals."""

import re

# Keywords that raise lead score
HIGH_INTENT_SIGNALS = [
    # Arabic
    "سعر", "تسجيل", "اشتراك", "كيف أسجل", "رسوم", "دفع", "شهادة",
    "دبلومة", "دبلوما", "مدة", "متى يبدأ", "تواصل", "اتصال", "واتساب",
    "هل يمكنني", "أريد الالتحاق", "أريد التسجيل",
    # English
    "price", "cost", "enroll", "register", "how to join", "payment",
    "certificate", "diploma", "how long", "duration", "contact", "whatsapp",
    "sign up", "i want to join", "i want to register",
]

MEDIUM_INTENT_SIGNALS = [
    # Arabic
    "مسار", "مناسب", "مقارنة", "أفضل", "يناسبني", "خيارات", "ماذا أختار",
    # English
    "track", "suitable", "compare", "best", "which is better", "options",
    "what should i choose",
]

BROWSING_SIGNALS = [
    "ما هي", "اشرح", "معلومات", "ما هو", "كيف يعمل",
    "what is", "tell me about", "explain", "information",
]


def compute_lead_score(messages: list[dict]) -> float:
    """
    Score the lead from 0.0 to 1.0 based on conversation signals.
    messages: list of {"role": "user"/"assistant", "content": str}
    """
    user_text = " ".join(
        m["content"].lower()
        for m in messages
        if m["role"] == "user"
    )

    score = 0.0

    # High intent signals (+0.15 each, max 0.75)
    for signal in HIGH_INTENT_SIGNALS:
        if signal in user_text:
            score += 0.15

    # Medium intent signals (+0.08 each)
    for signal in MEDIUM_INTENT_SIGNALS:
        if signal in user_text:
            score += 0.08

    # Conversation length bonus (more engaged = higher score)
    user_turns = sum(1 for m in messages if m["role"] == "user")
    score += min(user_turns * 0.03, 0.15)

    return min(round(score, 2), 1.0)


def is_qualified(score: float, threshold: float = 0.45) -> bool:
    return score >= threshold


def detect_intent_stage(messages: list[dict]) -> str:
    """Return one of: browsing | exploring | comparing | price_sensitive | objecting | ready"""
    user_text = " ".join(
        m["content"].lower()
        for m in messages[-4:]   # last 4 turns only
        if m["role"] == "user"
    )

    enrollment_kw = ["سجل", "اشترك", "كيف أسجل", "enroll", "register", "sign up", "join now"]
    price_kw = ["سعر", "تكلفة", "رسوم", "غالي", "price", "cost", "expensive", "afford"]
    objection_kw = ["مش متأكد", "وقت", "مشغول", "ما عندي وقت", "not sure", "no time", "busy"]
    compare_kw = ["مقارنة", "أفضل", "الفرق", "compare", "difference", "better", "versus", "vs"]
    explore_kw = ["مسار", "دبلومة", "track", "diploma", "roadmap", "diploma"]

    if any(k in user_text for k in enrollment_kw):
        return "ready"
    if any(k in user_text for k in price_kw):
        return "price_sensitive"
    if any(k in user_text for k in objection_kw):
        return "objecting"
    if any(k in user_text for k in compare_kw):
        return "comparing"
    if any(k in user_text for k in explore_kw):
        return "exploring"
    return "browsing"


def extract_language(text: str) -> str:
    """Detect 'arabic' or 'english' from user text."""
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    return "arabic" if arabic_chars > len(text) * 0.2 else "english"
