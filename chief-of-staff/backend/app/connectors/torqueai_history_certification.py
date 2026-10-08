"""Preview certification: isolated engine permits control-ledger DML only.

No scheduler, ingestion, approval, image application, or rollback writer enters
this module. Snapshot hashes stay aggregate; source records never leave it.
"""
from contextlib import contextmanager
import hashlib
import json
import os
import re

from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from app.connectors.torqueai import TorqueAIConnectorError, _validated_configuration
from app.connectors.torqueai_backfill_control import BackfillControl, CONTROL_TABLES, ControlError, fingerprint
from app.database.database import engine as application_engine
from app.models.torqueai import (TorqueAIDispatch, TorqueAIDispatchOperational,
                                TorqueAIDispatchStop, TorqueAIDispatchSyncRun,
                                TorqueAIDispatchSyncState)
from app.models.torqueai_backfill import MANIFEST, WINDOW, ATTEMPT, IDENTITY
from app.organizations.models import Organization

OPERATOR = "github-actions/historical-preview-certification"
NORMAL = (TorqueAIDispatch.__table__, TorqueAIDispatchOperational.__table__,
          TorqueAIDispatchStop.__table__, TorqueAIDispatchSyncState.__table__,
          TorqueAIDispatchSyncRun.__table__)
LEDGER = (MANIFEST, WINDOW, ATTEMPT, IDENTITY)
FLAGS = ("database_writes", "provider_writes", "checkpoint_modified", "claims_modified",
         "raw_provider_payload_returned", "operational_rows_modified", "secrets_exposed")


@contextmanager
def _isolated_engine():
    # Separate pool/listener: cannot restrict or participate in scheduled sessions.
    engine = create_engine(application_engine.url, pool_pre_ping=True)
    def restrict(conn, cursor, statement, parameters, context, executemany):
        compiled = context.compiled.statement if context.compiled else None
        if isinstance(compiled, Select):
            return
        if statement == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY":
            return
        # SQLAlchemy's PostgreSQL dialect performs these fixed read-only probes
        # before its first application statement. Arbitrary textual SQL is denied.
        if statement.strip().lower() in {"select pg_catalog.version()", "select current_schema()",
                                        "show transaction isolation level", "show standard_conforming_strings"}:
            return
        if isinstance(compiled, (Insert, Update)) and compiled.table.name in CONTROL_TABLES:
            return
        raise ControlError("Certification permits control-ledger writes only")
    event.listen(engine, "before_cursor_execute", restrict)
    try:
        yield engine
    finally:
        event.remove(engine, "before_cursor_execute", restrict)
        engine.dispose()


def _snapshot(engine, organization_id):
    output = {"normal": {}, "control_counts": {}}
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        for table in NORMAL:
            digest, count = hashlib.sha256(), 0
            for row in connection.execution_options(stream_results=True).execute(
                select(table).where(table.c.organization_id == organization_id).order_by(table.c.id)
            ).mappings():
                digest.update(json.dumps(dict(row), sort_keys=True, default=str,
                                         separators=(",", ":")).encode())
                digest.update(b"\n")
                count += 1
            output["normal"][table.name] = {"rows": count, "fingerprint": digest.hexdigest()}
        for table in LEDGER:
            output["control_counts"][table.name] = connection.execute(select(func.count()).select_from(table).where(
                table.c.organization_id == organization_id)).scalar_one()
        runs = TorqueAIDispatchSyncRun.__table__
        output["latest_normal_run"] = connection.execute(select(runs.c.run_id, runs.c.status,
            runs.c.trigger_mode, runs.c.started_at, runs.c.completed_at).where(
                runs.c.organization_id == organization_id).order_by(runs.c.id.desc()).limit(1)).mappings().first()
        output["latest_normal_run"] = ({k: str(v) if v is not None else None
                                        for k, v in output["latest_normal_run"].items()}
                                       if output["latest_normal_run"] else None)
        connection.rollback()
    return output


def _certify(engine, *, organization_id, date_from, date_to, code_sha):
    service = BackfillControl(engine, organization_id=organization_id)
    with engine.connect() as connection:
        if connection.execute(select(WINDOW.c.id).where(WINDOW.c.organization_id == organization_id,
            WINDOW.c.date_from <= date_to, WINDOW.c.date_to >= date_from).limit(1)).first():
            raise HTTPException(409, "historical preview interval already reserved")
    before = _snapshot(engine, organization_id)
    # Stable per-interval keys stop signed replay or concurrent duplicate fetches.
    key = f"certification:{date_from.isoformat()}:{date_to.isoformat()}"
    manifest_id = service.plan(request_key=key, operator=OPERATOR, code_sha=code_sha,
                               windows=[(date_from, date_to)])
    window = service.windows(manifest_id)[0]
    report = service.preview(window["id"], request_key=key, operator=OPERATOR, code_sha=code_sha)
    after = _snapshot(engine, organization_id)
    with engine.connect() as connection:
        final_window = connection.execute(select(WINDOW).where(WINDOW.c.organization_id == organization_id,
            WINDOW.c.id == window["id"])).mappings().one()
        attempt = connection.execute(select(ATTEMPT).where(ATTEMPT.c.organization_id == organization_id,
            ATTEMPT.c.window_id == window["id"])).mappings().one()
        quarantined = connection.execute(select(func.count()).select_from(IDENTITY).where(
            IDENTITY.c.organization_id == organization_id, IDENTITY.c.attempt_id == attempt["id"],
            IDENTITY.c.quarantined == 1)).scalar_one()
    normal_changed = before["normal"] != after["normal"]
    runs = TorqueAIDispatchSyncRun.__tablename__
    normal_sync_activity = before["normal"][runs] != after["normal"][runs]
    expected = {MANIFEST.name: 1, WINDOW.name: 1, ATTEMPT.name: 1,
                IDENTITY.name: len(report["identities"])}
    deltas = {t: after["control_counts"][t] - before["control_counts"][t]
              for t in before["control_counts"]}
    evidence_valid = (attempt["evidence_fingerprint"] == fingerprint(attempt["evidence"])
                      and attempt["status"] == final_window["status"]
                      and final_window["active_attempt_id"] is None and final_window["lease_until"] is None
                      and final_window["approved_at"] is None
                      and quarantined == report["identity_conflicts"])
    safety = (all(report[k] is False for k in FLAGS[:5]) and not normal_changed
              and deltas == expected and evidence_valid)
    payload = {"status": final_window["status"] if safety else "inconclusive",
        "provider": "torqueai", "operation": "historical_preview_certification",
        "request": report["request"], "window_semantics": "dispatch_order_date",
        "manifest_created": deltas[MANIFEST.name] == 1, "manifest_id": manifest_id, "window_id": window["id"],
        "attempt_id": attempt["id"], "code_sha": code_sha,
        "window_status": final_window["status"], "attempt_status": attempt["status"],
        "quarantined": quarantined, "page_size": report["pagination"]["page_size"],
        "pages_fetched": report["pagination"]["pages_fetched"],
        "provider_total_count": report["pagination"]["provider_total_count"],
        "returned_ship_dates": report["returned_ship_dates"], "before": before, "after": after,
        "control_row_deltas": deltas, "observed_normal_state_change": normal_changed,
        "normal_sync_activity_observed": normal_sync_activity, "safety_verified": safety,
        **{k: False for k in FLAGS}}
    for key in ("provider_records_received", "validated_records", "would_insert", "would_update",
                "unchanged", "identity_conflicts", "missing_usable_lane_stops"):
        payload[key] = report[key]
    # False flags refer to this structurally isolated preview, not unrelated writers.
    # Any concurrent normal change remains inconclusive; never guess attribution.
    if not safety or report["status"] != "success":
        raise HTTPException(409 if not safety else 502, payload)
    return payload


def certify_history(*, date_from, date_to):
    code_sha = os.getenv("RENDER_GIT_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", code_sha) is None:
        raise HTTPException(503, "deployed code identity unavailable")
    try:
        _validated_configuration("mor-logistics")  # No HTTP or database work.
        with _isolated_engine() as engine:
            with engine.connect() as connection:
                organization_id = connection.execute(select(Organization.id).where(
                    Organization.slug == "mor-logistics", Organization.status == "active")).scalar_one_or_none()
            if organization_id is None:
                raise HTTPException(503, "active MOR tenant unavailable")
            return _certify(engine, organization_id=organization_id, date_from=date_from,
                            date_to=date_to, code_sha=code_sha)
    except TorqueAIConnectorError:
        raise HTTPException(503, "TorqueAI configuration unavailable") from None
    except (ControlError, SQLAlchemyError):
        # Retain any partial ledger/lease as evidence; no cleanup, retry or rollback.
        raise HTTPException(409, "preview unavailable; inspect control ledger before retry") from None
