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


def lead_temperature(score: float) -> str:
    """Map a numeric lead score to a hot / warm / cold label.

    Thresholds mirror the chat status-bar badges (\u22650.6 high, \u22650.35 mid)."""
    if score >= 0.6:
        return "hot"
    if score >= 0.35:
        return "warm"
    return "cold"


# \u2500\u2500 Lightweight signal extraction (rule-based; the LLM refines these) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

# Dialect hints \u2014 only meaningful for Arabic speakers. Best-effort: surfaces a
# guess the rep can correct, not a hard classification.
_DIALECT_HINTS = {
    "\u062E\u0644\u064A\u062C\u064A": ["\u0648\u0634", "\u0634\u0644\u0648\u0646", "\u0643\u064A\u0641\u0643", "\u0627\u0628\u063A\u0649", "\u0623\u0628\u063A\u0649", "\u0648\u0627\u064A\u062F", "\u0632\u064A\u0646", "\u0643\u0630\u0627"],
    "\u0645\u0635\u0631\u064A": ["\u0639\u0627\u064A\u0632", "\u0639\u0627\u0648\u0632", "\u0627\u0632\u0627\u064A", "\u0625\u0632\u0627\u064A", "\u0627\u064A\u0647", "\u0625\u064A\u0647", "\u0643\u062F\u0647", "\u0645\u0634", "\u0639\u0644\u0634\u0627\u0646", "\u0639\u0634\u0627\u0646"],
    "\u0634\u0627\u0645\u064A": ["\u0634\u0648", "\u0647\u0644\u0642", "\u0643\u062A\u064A\u0631", "\u0647\u064A\u0643", "\u0628\u062F\u064A", "\u0644\u064A\u0634", "\u0645\u0646\u064A\u062D"],
    "\u0645\u063A\u0627\u0631\u0628\u064A": ["\u0628\u0632\u0627\u0641", "\u0648\u0627\u062E\u0627", "\u062F\u0627\u0628\u0627", "\u0643\u064A\u0641\u0627\u0634", "\u0628\u063A\u064A\u062A"],
}

_BUDGET_SENSITIVE = [
    "\u063A\u0627\u0644\u064A", "\u063A\u0627\u0644\u064A\u0629", "\u0645\u0643\u0644\u0641", "\u062A\u062E\u0641\u064A\u0636", "\u062E\u0635\u0645", "\u0623\u0642\u0633\u0627\u0637", "\u062A\u0642\u0633\u064A\u0637", "\u0645\u064A\u0632\u0627\u0646\u064A\u0629", "\u0645\u0627 \u0639\u0646\u062F\u064A \u0641\u0644\u0648\u0633",
    "expensive", "discount", "installment", "budget", "afford", "cheaper", "too much",
]

_LEVEL_BEGINNER = ["\u0645\u0628\u062A\u062F\u0626", "\u0645\u0628\u062A\u062F\u0623", "\u0645\u0646 \u0627\u0644\u0635\u0641\u0631", "\u0644\u0627 \u0623\u0639\u0631\u0641", "\u062C\u062F\u064A\u062F", "beginner", "from scratch", "new to", "no experience"]
_LEVEL_INTERMEDIATE = ["\u0645\u062A\u0648\u0633\u0637", "\u0639\u0646\u062F\u064A \u062E\u0628\u0631\u0629", "\u0623\u0639\u0631\u0641 \u0623\u0633\u0627\u0633\u064A\u0627\u062A", "intermediate", "some experience", "basics"]
_LEVEL_ADVANCED = ["\u0645\u062A\u0642\u062F\u0645", "\u0645\u062D\u062A\u0631\u0641", "\u062E\u0628\u064A\u0631", "advanced", "professional", "expert", "senior"]


def detect_dialect(text: str) -> str:
    """Best-effort Arabic dialect guess. Returns '' when nothing matches."""
    lowered = text.lower()
    best, best_hits = "", 0
    for dialect, hints in _DIALECT_HINTS.items():
        hits = sum(1 for h in hints if h in lowered)
        if hits > best_hits:
            best, best_hits = dialect, hits
    return best


def detect_current_level(text: str) -> str:
    """Guess the user's current level: beginner | intermediate | advanced | ''."""
    lowered = text.lower()
    if any(k in lowered for k in _LEVEL_ADVANCED):
        return "advanced"
    if any(k in lowered for k in _LEVEL_INTERMEDIATE):
        return "intermediate"
    if any(k in lowered for k in _LEVEL_BEGINNER):
        return "beginner"
    return ""


def detect_budget_sensitivity(text: str) -> str:
    """Return 'high' if price/discount concerns appear, else ''."""
    lowered = text.lower()
    return "high" if any(k in lowered for k in _BUDGET_SENSITIVE) else ""

# cache-bust: force Streamlit Cloud bytecode refresh (2026-06-21)
