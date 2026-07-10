from app.brain.intent import detect_intent
from app.brain.responder import build_response


def process_message(message: str) -> dict:
    """
    Coordinate the first Polaris Brain flow.

    Builder message
        -> Intent detection
        -> Response generation
    """

    intent = detect_intent(message)
    reply = build_response(intent, message)

    return {
        "intent": intent.value,
        "message": message,
        "reply": reply,
    }