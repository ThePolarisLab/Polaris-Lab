from datetime import datetime, timedelta, timezone
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from app.ace.feed_runner import ace_feed_health
from app.ace.service import summary as ace_operational_summary
from app.dashboard.models import DailyBrief, DashboardItem, DashboardPriority, ExecutiveDashboard
from app.models.ace import AceInBondMovement
from app.models.team_note import TeamNote
from app.models.truck import Truck
from app.missions.models import Mission
from app.motive.vehicle_utilization_operational_status import vehicle_utilization_operational_status
from app.reasoning.service import analyze_q2_compliance_risk


def build_executive_dashboard(db: Session, *, organization_id: str, user_name: str = "Surinder") -> ExecutiveDashboard:
    now = datetime.now(timezone.utc)
    open_notes = (
        db.query(TeamNote)
        .filter(TeamNote.organization_id == organization_id, TeamNote.status != "RESOLVED")
        .order_by(TeamNote.due_at.asc(), TeamNote.created_at.asc())
        .all()
    )
    active_missions = (
        db.query(Mission)
        .filter(Mission.organization_id == organization_id, Mission.status != "Complete")
        .order_by(Mission.created_at.asc())
        .all()
    )
    total_trucks = db.query(Truck).filter(Truck.organization_id == organization_id).count()
    q2 = analyze_q2_compliance_risk(db, organization_id)
    ace_attention = _ace_attention(db, organization_id)
    needs = (_attention(open_notes, q2) + ace_attention)[:8]
    carry = _carry(open_notes, active_missions, now)
    waiting = _waiting_on(open_notes, now)
    plan = _plan(needs, carry)
    upcoming = _upcoming(open_notes, now)
    watch = (_watch(open_notes, q2) + _ace_watch(db, organization_id))[:6]
    health_items = _system_health(db, organization_id)
    daily_brief = DailyBrief(
        todays_priority=tuple(_daily_priority(needs, carry, waiting)),
        needs_attention=tuple(needs),
        ace_summary=tuple(_ace_summary(db, organization_id)),
        carry_forward=tuple(_without_duplicate_titles(carry, needs)),
        waiting_on=tuple(waiting),
        system_health=tuple(health_items),
    )
    recommendation = q2.recommendation if plan and "Q2" in plan[0].title else (f"Start with '{plan[0].title}'. Reason: {plan[0].reason}" if plan else "Review current operations and confirm today's priorities.")
    critical = sum(1 for x in needs if x.severity == "CRITICAL")
    status = "ATTENTION REQUIRED" if critical >= 2 else ("WATCH" if critical == 1 or needs else "RUNNING NORMALLY")
    review = max(2, min(12, len(needs)+len(carry)+len(upcoming)))
    return ExecutiveDashboard(f"Good morning, {user_name}.", status, review, tuple(needs), tuple(carry), tuple(plan), tuple(upcoming), tuple(watch), len(open_notes), len(active_missions), total_trucks, recommendation, daily_brief)


def _attention(notes, q2):
    items=[]
    for n in notes:
        if n.note_type in {"BLOCKER","ACTION"}:
            items.append(DashboardItem(n.title,n.details,"CRITICAL" if n.note_type=="BLOCKER" else "HIGH",f"Team Note — {n.author}",n.target_entity))
    if q2.risk.value in {"MEDIUM","HIGH"}:
        items.append(DashboardItem("Complete Q2 Compliance",f"Risk {q2.risk.value}; {q2.evidence_count} connected evidence item(s).","CRITICAL" if q2.risk.value=="HIGH" else "HIGH","Polaris Reasoning",q2.mission_id))
    return items[:8]


def _ace_table_available(db: Session) -> bool:
    """Allow mixed-schema test/rollout environments to render the dashboard safely."""
    try:
        return "ace_inbond_movements" in inspect(db.get_bind()).get_table_names()
    except Exception:
        return False


def _ace_attention(db, organization_id):
    if not _ace_table_available(db):
        return []
    counts = _ace_attention_counts(db, organization_id)
    items = []
    total = counts["critical"] + counts["review"]
    if total:
        detail_parts = []
        for label, key in (
            ("Unauthorized", "unauthorized"),
            ("Penalty", "penalty"),
            ("Overdue", "overdue_for_export"),
            ("Late", "late_in_transit"),
            ("Carrier review", "carrier_mismatch"),
            ("QP filer review", "qp_filer_review"),
        ):
            if counts[key]:
                detail_parts.append(f"{counts[key]} {label}")
        detail = "; ".join(detail_parts) or f"{total} unresolved review item(s)"
        items.append(DashboardItem(
            "ACE / Bond Control requires attention",
            detail,
            "CRITICAL" if counts["critical"] else "HIGH",
            "ACE Bond Control",
            "#executive/ace?counter_filter=exceptions",
        ))
    feed_item = _ace_feed_attention(db, organization_id)
    if feed_item:
        items.append(feed_item)
    return items[:3]


def _ace_attention_counts(db, organization_id):
    rows = (
        db.query(AceInBondMovement)
        .filter(
            AceInBondMovement.organization_id == organization_id,
            AceInBondMovement.resolved_at.is_(None),
            AceInBondMovement.review_status.in_(["review", "critical"]),
        )
        .all()
    )
    counts = {
        "critical": 0,
        "review": 0,
        "unauthorized": 0,
        "penalty": 0,
        "overdue_for_export": 0,
        "late_in_transit": 0,
        "carrier_mismatch": 0,
        "qp_filer_review": 0,
    }
    for movement in rows:
        if movement.review_status == "critical":
            counts["critical"] += 1
        else:
            counts["review"] += 1
        for reason in _ace_reason_tokens(movement.review_reason):
            if reason in counts:
                counts[reason] += 1
    return counts


def _ace_reason_tokens(reason: str | None) -> set[str]:
    if not reason:
        return set()
    return {token.strip() for token in reason.split(",") if token.strip()}


def _ace_feed_attention(db, organization_id):
    try:
        health = ace_feed_health(db, organization_id)
    except Exception:
        return None
    status = health.get("status")
    if status == "error":
        return DashboardItem(
            "ACE daily feed failed",
            f"Latest feed check ended in {health.get('latest_check_status') or 'failure'}. Review ACE feed health before relying on today's report.",
            "CRITICAL",
            "ACE Daily Feed",
            "#executive/ace",
        )
    if status == "warning":
        return DashboardItem(
            "ACE daily feed needs review",
            f"No successful ACE import inside the configured {health.get('freshness_threshold_hours') or 36}-hour freshness window.",
            "HIGH",
            "ACE Daily Feed",
            "#executive/ace",
        )
    return None


def _ace_watch(db, organization_id):
    return []


def _ace_summary(db, organization_id):
    if not _ace_table_available(db):
        return []
    try:
        counts = ace_operational_summary(db, organization_id)
        health = ace_feed_health(db, organization_id)
    except Exception:
        return []
    if not counts.get("total") and health.get("status") == "unknown":
        return []
    detail = (
        f"Feed {health.get('status') or 'unknown'}; "
        f"{counts.get('active', 0)} Active; {counts.get('open', 0)} Open; "
        f"{counts.get('exceptions', 0)} Exceptions; {counts.get('overdue', 0)} Overdue; "
        f"{counts.get('late', 0)} Late; {counts.get('unauthorized', 0)} Unauthorized"
    )
    severity = "HIGH" if counts.get("exceptions") or counts.get("overdue") or health.get("status") in {"error", "warning"} else "LOW"
    return [DashboardItem("ACE / Bond Control", detail, severity, "ACE Bond Control", "#executive/ace")]


def _carry(notes, missions, now):
    items=[]; today=now.date()
    for n in notes:
        created=_aware(n.created_at); due=_aware(n.due_at)
        if created.date()<today or (due and due<now):
            items.append(DashboardItem(n.title,n.status.replace('_',' ').title() + (f" — assigned to {n.assigned_to}" if n.assigned_to else ""),"HIGH" if due and due<now else "MEDIUM",f"Team Note — {n.author}",n.target_entity))
    for m in missions:
        p=int(getattr(m,'progress',0) or 0)
        if p<100: items.append(DashboardItem(m.title,f"{p}% complete","MEDIUM","Mission",f"mission.{m.id}"))
    return items[:8]


def _waiting_on(notes, now):
    items = []
    for n in notes:
        if not n.assigned_to:
            continue
        due = _aware(n.due_at)
        detail = f"Waiting on {n.assigned_to}"
        if due:
            detail += f"; due {due.strftime('%a, %b %d at %I:%M %p')}"
        items.append(DashboardItem(n.title, detail, "HIGH" if due and due < now else "MEDIUM", f"Team Note — {n.author}", n.target_entity))
    return items[:6]


def _plan(needs, carry):
    rank={'CRITICAL':4,'HIGH':3,'MEDIUM':2,'LOW':1}; combined=list(needs)+list(carry); combined.sort(key=lambda x:rank.get(x.severity,1), reverse=True)
    seen=set(); out=[]
    for x in combined:
        k=x.title.casefold()
        if k in seen: continue
        seen.add(k); out.append(DashboardPriority(len(out)+1,x.title,x.detail,x.source))
        if len(out)==5: break
    return out or [DashboardPriority(1,"Review today's operations","No urgent carry-forward items were found.","Polaris")]


def _upcoming(notes, now):
    horizon=now+timedelta(days=7); out=[]
    for n in notes:
        due=_aware(n.due_at)
        if due and now<=due<=horizon:
            out.append(DashboardItem(n.title,f"Due {due.strftime('%a, %b %d at %I:%M %p')}","MEDIUM",f"Team Note — {n.author}",n.target_entity))
    return out[:6]


def _watch(notes, q2):
    out=[]
    for n in notes:
        if n.note_type in {"INFORMATION","DECISION"}: out.append(DashboardItem(n.title,n.details,"LOW",f"Team Note — {n.author}",n.target_entity))
    if q2.risk.value=="LOW" and q2.evidence_count: out.append(DashboardItem("Q2 Compliance","Connected evidence exists, but current calculated risk is low.","LOW","Polaris Reasoning",q2.mission_id))
    return out[:6]


def _motive_utilization_health(db, organization_id):
    try:
        status = vehicle_utilization_operational_status(db, organization_id)
    except Exception:
        return DashboardItem(
            "Motive utilization health could not be read",
            "Motive vehicle-utilization operational health is unavailable; review Motive operational status.",
            "HIGH",
            "Motive Vehicle Utilization",
        )

    operational_status = status.get("operational_status")
    if operational_status == "healthy":
        return None

    if operational_status == "not_started":
        configuration = status.get("configuration")
        configuration = configuration if isinstance(configuration, dict) else {}
        if not (
            configuration.get("production_ingestion_enabled")
            or configuration.get("production_scheduler_enabled")
        ):
            return None
        return DashboardItem(
            "Motive vehicle utilization has no production history",
            "Production vehicle-utilization capability is enabled, but no production history is available.",
            "MEDIUM",
            "Motive Vehicle Utilization",
        )

    production = status.get("production")
    production = production if isinstance(production, dict) else {}
    checkpoint = status.get("checkpoint")
    checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
    if production.get("status") != "success":
        detail = "Latest production vehicle-utilization run did not complete successfully; review Motive operational status."
    elif checkpoint.get("status") != "success":
        detail = "Production vehicle-utilization checkpoint is not successful; review Motive operational status."
    else:
        detail = "Production utilization history and checkpoint are inconsistent; review Motive operational status."
    return DashboardItem(
        "Motive vehicle utilization needs review",
        detail,
        "HIGH",
        "Motive Vehicle Utilization",
    )


def _system_health(db, organization_id):
    items = []
    ace_item = _ace_feed_attention(db, organization_id)
    if ace_item:
        items.append(ace_item)
    motive_item = _motive_utilization_health(db, organization_id)
    if motive_item:
        items.append(motive_item)
    return items


def _daily_priority(needs, carry, waiting):
    rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    combined = list(needs) + list(carry) + list(waiting)
    combined.sort(key=lambda item: rank.get(item.severity, 1), reverse=True)
    seen = set()
    out = []
    for item in combined:
        key = (item.title.casefold(), item.source.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(DashboardPriority(len(out) + 1, item.title, item.detail, item.source))
        if len(out) == 3:
            break
    return out


def _without_duplicate_titles(items, already_shown):
    seen = {item.title.casefold() for item in already_shown}
    return [item for item in items if item.title.casefold() not in seen]


def _aware(value):
    if value is None: return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
