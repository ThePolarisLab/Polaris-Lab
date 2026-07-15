from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.dashboard.models import DashboardItem, DashboardPriority, ExecutiveDashboard
from app.models.team_note import TeamNote
from app.models.truck import Truck
from app.missions.models import Mission
from app.reasoning.service import analyze_q2_compliance_risk


def build_executive_dashboard(db: Session, *, user_name: str = "Surinder") -> ExecutiveDashboard:
    now = datetime.now(timezone.utc)
    open_notes = (db.query(TeamNote).filter(TeamNote.status != "RESOLVED").order_by(TeamNote.due_at.asc(), TeamNote.created_at.asc()).all())
    active_missions = (db.query(Mission).filter(Mission.status != "Complete").order_by(Mission.created_at.asc()).all())
    total_trucks = db.query(Truck).count()
    q2 = analyze_q2_compliance_risk(db)
    needs = _attention(open_notes, q2)
    carry = _carry(open_notes, active_missions, now)
    plan = _plan(needs, carry)
    upcoming = _upcoming(open_notes, now)
    watch = _watch(open_notes, q2)
    recommendation = q2.recommendation if plan and "Q2" in plan[0].title else (f"Start with '{plan[0].title}'. Reason: {plan[0].reason}" if plan else "Review current operations and confirm today's priorities.")
    critical = sum(1 for x in needs if x.severity == "CRITICAL")
    status = "ATTENTION REQUIRED" if critical >= 2 else ("WATCH" if critical == 1 or needs else "RUNNING NORMALLY")
    review = max(2, min(12, len(needs)+len(carry)+len(upcoming)))
    return ExecutiveDashboard(f"Good morning, {user_name}.", status, review, tuple(needs), tuple(carry), tuple(plan), tuple(upcoming), tuple(watch), len(open_notes), len(active_missions), total_trucks, recommendation)


def _attention(notes, q2):
    items=[]
    for n in notes:
        if n.note_type in {"BLOCKER","ACTION"}:
            items.append(DashboardItem(n.title,n.details,"CRITICAL" if n.note_type=="BLOCKER" else "HIGH",f"Team Note — {n.author}",n.target_entity))
    if q2.risk.value in {"MEDIUM","HIGH"}:
        items.append(DashboardItem("Complete Q2 Compliance",f"Risk {q2.risk.value}; {q2.evidence_count} connected evidence item(s).","CRITICAL" if q2.risk.value=="HIGH" else "HIGH","Polaris Reasoning",q2.mission_id))
    return items[:8]


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


def _aware(value):
    if value is None: return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
