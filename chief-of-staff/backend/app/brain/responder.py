from app.brain.intent import IntentType


def build_response(intent: IntentType, message: str) -> str:
    """
    Build a simple Builder-facing response.

    Version 1 returns deterministic responses.
    Later, this will use context, reasoning, and memory results.
    """

    if intent == IntentType.REMEMBER:
        return "I understand. I will prepare this to be saved in Polaris Memory."

    if intent == IntentType.RECALL:
        return "I understand. I will search Polaris Memory for relevant information."

    if intent == IntentType.SUMMARIZE:
        return "I understand. I will prepare a summary from the available context."

    if intent == IntentType.HELP:
        return (
            "You can ask me to remember information, recall past events, "
            "summarize work, or explain what Polaris knows."
        )

    return (
        "I am not fully certain what you want me to do. "
        "Please tell me whether you want me to remember, recall, summarize, or help."
    )