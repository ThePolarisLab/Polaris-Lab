from enum import Enum

class IntentType(str, Enum):
    REMEMBER = "REMEMBER"
    RECALL = "RECALL"
    LIST_MISSIONS = "LIST_MISSIONS"
    START_Q2_MISSION = "START_Q2_MISSION"
    SUMMARIZE = "SUMMARIZE"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"

def detect_intent(message: str) -> IntentType:
    normalized = " ".join(message.strip().lower().split())
    if not normalized:
        return IntentType.UNKNOWN
    if any(p in normalized for p in ("let's complete q2","lets complete q2","complete q2","finish q2","start q2","q2 compliance")):
        return IntentType.START_Q2_MISSION
    if any(p in normalized for p in ("show me my missions","show my missions","list missions","active missions","what missions")):
        return IntentType.LIST_MISSIONS
    if any(p in normalized for p in ("what do you remember","do you remember","show me what you remember","recall","search memory","find memory")):
        return IntentType.RECALL
    if any(p in normalized for p in ("remember ","remember that","save this","note that","record that","don't forget","do not forget")):
        return IntentType.REMEMBER
    if any(p in normalized for p in ("summarize","summary","what happened","give me a recap","recap")):
        return IntentType.SUMMARIZE
    if any(p in normalized for p in ("help","what can you do","how do i use polaris","how can you help")):
        return IntentType.HELP
    return IntentType.UNKNOWN
