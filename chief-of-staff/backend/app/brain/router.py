import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brain.intent import IntentType
from app.knowledge.classifier import classify_memory
from app.models.memory import MemoryEntry
from app.missions.models import Mission
from app.missions.service import create_mission, list_missions


def route_intent(
    *,
    intent: IntentType,
    message: str,
    db: Session,
    context: dict,
) -> dict:
    """Delegate Builder intent to the correct Polaris capability."""

    if intent == IntentType.REMEMBER:
        return _remember(message=message, db=db)

    if intent == IntentType.RECALL:
        return _recall(message=message, db=db)

    if intent == IntentType.START_Q2_MISSION:
        return _start_q2(db=db)

    if intent == IntentType.LIST_MISSIONS:
        return _list_missions(db=db)

    if intent == IntentType.SUMMARIZE:
        return _summarize(context=context)

    if intent == IntentType.HELP:
        return {
            "reply": (
                "You can ask me to remember information, recall memories, "
                "start the Q2 Compliance mission, list your missions, "
                "or summarize recent activity."
            ),
            "action": "HELP_SHOWN",
        }

    return {
        "reply": (
            "I am not fully certain what you want me to do. "
            "Try: 'Remember that...', 'What do you remember about...', "
            "'Let's complete Q2', or 'Show me my missions'."
        ),
        "action": "NO_ACTION",
    }


def _remember(*, message: str, db: Session) -> dict:
    details = _clean_memory_message(message)
    title = _make_title(details)
    classification = classify_memory(details)

    entry = MemoryEntry(
        category=classification.category,
        title=title,
        details=details,
        importance=classification.importance,
        source="Conversation",
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    entity_names = [
        entity.name
        for entity in classification.entities
    ]

    return {
        "reply": (
            f"I've saved this to Polaris Memory: {details}"
            + (
                f" Recognized: {', '.join(entity_names)}."
                if entity_names
                else ""
            )
        ),
        "action": "MEMORY_CREATED",
        "entity_id": entry.id,
    }


def _recall(*, message: str, db: Session) -> dict:
    query = _extract_recall_query(message)
    memories_query = db.query(MemoryEntry)

    if query:
        pattern = f"%{query}%"
        memories_query = memories_query.filter(
            or_(
                MemoryEntry.title.ilike(pattern),
                MemoryEntry.details.ilike(pattern),
                MemoryEntry.category.ilike(pattern),
                MemoryEntry.source.ilike(pattern),
            )
        )

    memories = (
        memories_query
        .order_by(MemoryEntry.created_at.desc())
        .limit(5)
        .all()
    )

    if not memories:
        subject = f" about {query}" if query else ""
        return {
            "reply": f"I couldn't find any Polaris memories{subject}.",
            "action": "MEMORY_SEARCHED",
            "items": [],
        }

    lines = [
        f"• {memory.title}: {memory.details}"
        for memory in memories
    ]

    return {
        "reply": "Here is what I remember:\n" + "\n".join(lines),
        "action": "MEMORY_SEARCHED",
        "items": [memory.id for memory in memories],
    }


def _start_q2(*, db: Session) -> dict:
    existing = (
        db.query(Mission)
        .filter(
            Mission.title == "Complete Q2 Compliance",
            Mission.status != "Complete",
        )
        .order_by(Mission.created_at.desc())
        .first()
    )

    if existing is not None:
        next_task = _first_incomplete_task(existing)
        next_text = (
            f" Your next task is: {next_task.title}."
            if next_task is not None
            else ""
        )

        return {
            "reply": (
                f"Your Q2 Compliance mission is already active at "
                f"{existing.progress}% progress.{next_text}"
            ),
            "action": "MISSION_FOUND",
            "entity_id": existing.id,
        }

    mission = create_mission(
        db,
        template_key="q2_compliance",
        owner="Surinder Pahil",
        company="MOR Logistics Manitoba Limited",
        due_at=None,
    )

    task_count = sum(
        len(workflow.tasks)
        for workflow in mission.workflows
    )

    first_task = _first_incomplete_task(mission)
    next_text = (
        f" Your first task is: {first_task.title}."
        if first_task is not None
        else ""
    )

    return {
        "reply": (
            f"I've started the Q2 Compliance mission with "
            f"{len(mission.workflows)} workflows and {task_count} tasks."
            f"{next_text}"
        ),
        "action": "MISSION_CREATED",
        "entity_id": mission.id,
    }


def _list_missions(*, db: Session) -> dict:
    missions = list_missions(db)[:10]

    if not missions:
        return {
            "reply": "You do not have any missions yet.",
            "action": "MISSIONS_LISTED",
            "items": [],
        }

    lines = [
        f"• {mission.title} — {mission.status}, {mission.progress}%"
        for mission in missions
    ]

    return {
        "reply": "Your missions:\n" + "\n".join(lines),
        "action": "MISSIONS_LISTED",
        "items": [mission.id for mission in missions],
    }


def _summarize(*, context: dict) -> dict:
    memories = context.get("recent_memories", [])
    missions = context.get("active_missions", [])

    mission_text = (
        ", ".join(
            f"{mission.title} ({mission.progress}%)"
            for mission in missions
        )
        if missions
        else "no active missions"
    )

    memory_text = (
        ", ".join(memory.title for memory in memories)
        if memories
        else "no recent memories"
    )

    return {
        "reply": (
            f"Current summary: {mission_text}. "
            f"Recent memories: {memory_text}."
        ),
        "action": "SUMMARY_CREATED",
    }


def _clean_memory_message(message: str) -> str:
    cleaned = re.sub(
        (
            r"^\s*("
            r"remember(?:\s+that)?|"
            r"save this|"
            r"note that|"
            r"record that|"
            r"don't forget|"
            r"do not forget"
            r")\s*[:,-]?\s*"
        ),
        "",
        message,
        flags=re.IGNORECASE,
    ).strip()

    return cleaned or message.strip()


def _make_title(details: str) -> str:
    sentence = details.rstrip(".!?")
    words = sentence.split()
    short = " ".join(words[:8])

    return short[:80] or "Conversation Memory"


def _extract_recall_query(message: str) -> str:
    normalized = message.strip()

    patterns = (
        r"what do you remember about\s+(.+)",
        r"do you remember\s+(.+)",
        r"search memory for\s+(.+)",
        r"find memory(?: about| for)?\s+(.+)",
        r"recall\s+(.+)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(1).strip(" ?.!")

    return ""


def _first_incomplete_task(mission: Mission):
    for workflow in mission.workflows:
        for task in workflow.tasks:
            if task.status != "Complete":
                return task

    return None
