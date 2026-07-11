from sqlalchemy.orm import Session
from app.brain.context import load_context
from app.brain.intent import detect_intent
from app.brain.responder import build_response
from app.brain.router import route_intent

def process_message(message: str, db: Session) -> dict:
    context = load_context(db)
    intent = detect_intent(message)
    result = route_intent(intent=intent, message=message, db=db, context=context)
    response = {"intent": intent.value, "message": message, "reply": build_response(result), "action": result.get("action")}
    if result.get("entity_id") is not None: response["entity_id"] = result["entity_id"]
    if result.get("items") is not None: response["items"] = result["items"]
    return response
