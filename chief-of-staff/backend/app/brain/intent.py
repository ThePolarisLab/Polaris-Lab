from enum import Enum


class IntentType(str, Enum):
    REMEMBER = "REMEMBER"
    RECALL = "RECALL"
    SUMMARIZE = "SUMMARIZE"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"


def detect_intent(message: str) -> IntentType:
    """
    Detect the Builder's intent using simple, predictable rules.

    This is intentionally rule-based for Version 1.
    We can replace or enhance it with an AI model later.
    """

    normalized = message.strip().lower()

    if not normalized:
        return IntentType.UNKNOWN

    remember_phrases = (
        "remember ",
        "remember that",
        "save this",
        "note that",
        "record that",
        "don't forget",
        "do not forget",
    )

    recall_phrases = (
        "what do you remember",
        "do you remember",
        "show me what you remember",
        "recall",
        "search memory",
        "find memory",
    )

    summarize_phrases = (
        "summarize",
        "summary",
        "what happened",
        "give me a recap",
        "recap",
    )

    help_phrases = (
        "help",
        "what can you do",
        "how do i use polaris",
        "how can you help",
    )

    if any(phrase in normalized for phrase in remember_phrases):
        return IntentType.REMEMBER

    if any(phrase in normalized for phrase in recall_phrases):
        return IntentType.RECALL

    if any(phrase in normalized for phrase in summarize_phrases):
        return IntentType.SUMMARIZE

    if any(phrase in normalized for phrase in help_phrases):
        return IntentType.HELP

    return IntentType.UNKNOWN