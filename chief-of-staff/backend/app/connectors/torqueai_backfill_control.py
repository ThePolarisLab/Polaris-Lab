"""Internal control-plane library. No CLI, HTTP route, scheduler or dispatch writer.

Transactions may mutate only the four backfill ledger tables. Caller transactions
and scheduled claims/checkpoints never enter this service. Preview execution uses
the existing isolated read-only provider/database boundary.
"""
from contextlib import contextmanager
from datetime import date, timedelta, timezone
import hashlib
import json
import re
from uuid import uuid4

from sqlalchemy import event, insert, select, update
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from app.connectors.torqueai_history_preview import preview_torqueai_history
from app.connectors.torqueai_ingestion import TorqueAIDispatchIngestionError, _validate_window
from app.models.torqueai_backfill import ATTEMPT, CLAIM_NAMESPACE, IDENTITY, MANIFEST, SEMANTICS, WINDOW, utcnow
from app.organizations.models import Organization

CONTROL_TABLES = frozenset(t.name for t in (MANIFEST, WINDOW, ATTEMPT, IDENTITY))


class ControlError(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _label(value, maximum=120):
    if (not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ControlError("Invalid operator/request label")
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ControlError("Exact lowercase code SHA required")
    return value


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@contextmanager
def _ledger_connection(engine):
    with engine.begin() as connection:
        def restrict(conn, cursor, statement, parameters, context, executemany):
            compiled = context.compiled.statement if context.compiled else None
            if isinstance(compiled, Select):
                return
            if not isinstance(compiled, (Insert, Update)) or compiled.table.name not in CONTROL_TABLES:
                raise ControlError("Control plane permits ledger writes only")
        event.listen(connection, "before_cursor_execute", restrict)
        try:
            yield connection
        finally:
            event.remove(connection, "before_cursor_execute", restrict)


class BackfillControl:
    def __init__(self, engine, *, organization_id):
        self.engine = engine
        self.organization_id = organization_id

    def _tenant(self, connection):
        tenant = connection.execute(select(Organization.id).where(
            Organization.id == self.organization_id, Organization.slug == "mor-logistics",
            Organization.status == "active")).scalar_one_or_none()
        if tenant is None:
            raise ControlError("Active MOR tenant required")

    def _window(self, connection, window_id):
        self._tenant(connection)
        row = connection.execute(select(WINDOW).where(
            WINDOW.c.organization_id == self.organization_id, WINDOW.c.id == window_id
        ).with_for_update()).mappings().one_or_none()
        if row is None:
            raise ControlError("Unknown tenant window")
        return row

    def plan(self, *, request_key, operator, code_sha, windows):
        """Idempotent immutable plan, no overlap within a manifest; adjacent is valid."""
        _label(request_key); _label(operator); _sha(code_sha)
        intervals = sorted(windows)
        if not intervals:
            raise ControlError("At least one window required")
        for start, end in intervals:
            if type(start) is not date or type(end) is not date:
                raise ControlError("Explicit date objects required")
            try:
                _validate_window(start, end)
            except TorqueAIDispatchIngestionError as exc:
                raise ControlError(str(exc)) from exc
        if any(intervals[i][0] <= intervals[i - 1][1] for i in range(1, len(intervals))):
            raise ControlError("Duplicate/overlapping provider intervals forbidden")
        with _ledger_connection(self.engine) as connection:
            self._tenant(connection)
            # Serialize plan creation for this tenant, including concurrent retries.
            connection.execute(select(Organization.id).where(
                Organization.id == self.organization_id).with_for_update()).one()
            previous = connection.execute(select(MANIFEST).where(
                MANIFEST.c.organization_id == self.organization_id, MANIFEST.c.request_key == request_key
            )).mappings().one_or_none()
            if previous:
                stored = connection.execute(select(WINDOW.c.date_from, WINDOW.c.date_to).where(
                    WINDOW.c.organization_id == self.organization_id, WINDOW.c.manifest_id == previous["id"]
                ).order_by(WINDOW.c.date_from)).all()
                if list(map(tuple, stored)) != intervals or previous["code_sha"] != code_sha or previous["operator"] != operator:
                    raise ControlError("Request key reused with different plan")
                return previous["id"]
            manifest_id = str(uuid4())
            now = utcnow()
            connection.execute(insert(MANIFEST).values(id=manifest_id, organization_id=self.organization_id,
                request_key=request_key, operator=operator, code_sha=code_sha, created_at=now,
                window_semantics=SEMANTICS, execution_mode="preview_only"))
            for start, end in intervals:
                connection.execute(insert(WINDOW).values(id=str(uuid4()), organization_id=self.organization_id,
                    manifest_id=manifest_id, date_from=start, date_to=end, status="planned", created_at=now))
            return manifest_id

    def windows(self, manifest_id):
        with _ledger_connection(self.engine) as connection:
            self._tenant(connection)
            return [dict(row) for row in connection.execute(select(WINDOW).where(
                WINDOW.c.organization_id == self.organization_id, WINDOW.c.manifest_id == manifest_id
            ).order_by(WINDOW.c.date_from)).mappings()]

    def begin_preview(self, window_id, *, request_key, operator, code_sha):
        """Separate preview claim; a retry key returns its original attempt.

        Expired attempts are retained as failed. A new key is required to retry.
        There is no automatic retry or operational-write capability.
        """
        return self._begin_preview(window_id, request_key=request_key, operator=operator, code_sha=code_sha)[0]

    def _begin_preview(self, window_id, *, request_key, operator, code_sha):
        _label(request_key); _label(operator); _sha(code_sha)
        with _ledger_connection(self.engine) as connection:
            window = self._window(connection, window_id)
            previous = connection.execute(select(ATTEMPT).where(
                ATTEMPT.c.organization_id == self.organization_id, ATTEMPT.c.window_id == window_id,
                ATTEMPT.c.request_key == request_key)).mappings().one_or_none()
            if previous:
                if previous["operator"] != operator or previous["code_sha"] != code_sha:
                    raise ControlError("Retry key metadata changed")
                return previous["id"], False
            if window["status"] in {"approved", "running", "completed"}:
                raise ControlError("Approved/executing window cannot be re-previewed")
            now = utcnow()
            if window["active_attempt_id"]:
                if _aware(window["lease_until"]) > now:
                    raise ControlError("Preview claim already active")
                connection.execute(update(ATTEMPT).where(ATTEMPT.c.id == window["active_attempt_id"],
                    ATTEMPT.c.organization_id == self.organization_id).values(status="failed", completed_at=now))
            attempt_id = str(uuid4())
            connection.execute(insert(ATTEMPT).values(id=attempt_id, organization_id=self.organization_id,
                window_id=window_id, request_key=request_key, operator=operator, code_sha=code_sha,
                claim_namespace=CLAIM_NAMESPACE, started_at=now, status="previewing"))
            connection.execute(update(WINDOW).where(WINDOW.c.id == window_id,
                WINDOW.c.organization_id == self.organization_id).values(active_attempt_id=attempt_id,
                lease_until=now + timedelta(minutes=30), started_at=now, completed_at=None, status="planned"))
            return attempt_id, True

    def finish_preview(self, window_id, attempt_id, report):
        """Store bounded evidence from the existing validator; never raw payloads."""
        with _ledger_connection(self.engine) as connection:
            window = self._window(connection, window_id)
            attempt = connection.execute(select(ATTEMPT).where(ATTEMPT.c.id == attempt_id,
                ATTEMPT.c.organization_id == self.organization_id, ATTEMPT.c.window_id == window_id
            )).mappings().one_or_none()
            if not attempt:
                raise ControlError("Unknown tenant attempt")
            evidence, identities = _preview_evidence(report, window)
            digest = fingerprint(evidence)
            if attempt["completed_at"]:
                if attempt["evidence_fingerprint"] != digest:
                    raise ControlError("Completed evidence is immutable")
                return attempt["status"]
            if window["active_attempt_id"] != attempt_id or _aware(window["lease_until"]) <= utcnow():
                raise ControlError("Preview lease lost/expired")
            historical_conflict = connection.execute(select(IDENTITY.c.id).join(ATTEMPT,
                (ATTEMPT.c.id == IDENTITY.c.attempt_id) & (ATTEMPT.c.organization_id == IDENTITY.c.organization_id)
            ).where(IDENTITY.c.organization_id == self.organization_id, ATTEMPT.c.window_id == window_id,
                    IDENTITY.c.quarantined == 1).limit(1)).first() is not None
            status = ("failed" if report["status"] != "success" else "blocked"
                      if evidence["identity_conflicts"] or historical_conflict else "previewed")
            now = utcnow()
            for item in identities:
                connection.execute(insert(IDENTITY).values(id=str(uuid4()), organization_id=self.organization_id,
                    attempt_id=attempt_id, provider_load_number=item["provider_load_number"],
                    provider_order_number=item["provider_order_number"], classification=item["classification"],
                    quarantined=int(item["classification"] == "identity_conflict"),
                    conflicting_order_numbers=item["conflicting_order_numbers"]))
            connection.execute(update(ATTEMPT).where(ATTEMPT.c.id == attempt_id,
                ATTEMPT.c.organization_id == self.organization_id).values(status=status, completed_at=now,
                evidence=evidence, evidence_fingerprint=digest))
            connection.execute(update(WINDOW).where(WINDOW.c.id == window_id,
                WINDOW.c.organization_id == self.organization_id).values(status=status, completed_at=now,
                active_attempt_id=None, lease_until=None))
            return status

    def preview(self, window_id, *, request_key, operator, code_sha, connector=None):
        """Internal library operation; writes ledger only, reads provider/dispatches."""
        attempt_id, created = self._begin_preview(window_id, request_key=request_key, operator=operator, code_sha=code_sha)
        with _ledger_connection(self.engine) as connection:
            window = self._window(connection, window_id)
            previous = connection.execute(select(ATTEMPT).where(ATTEMPT.c.id == attempt_id,
                ATTEMPT.c.organization_id == self.organization_id)).mappings().one()
            if previous["completed_at"]:
                if previous["evidence"] is None:
                    raise ControlError("Expired attempt has no evidence; use a new retry key")
                return previous["evidence"]
            if not created:
                raise ControlError("Preview request already in progress; do not refetch")
        report = preview_torqueai_history(self.engine, date_from=window["date_from"],
                                         date_to=window["date_to"], connector=connector)
        self.finish_preview(window_id, attempt_id, report)
        return report

    def approve(self, window_id, *, operator):
        """Approval records review only; cannot enable execution."""
        _label(operator)
        with _ledger_connection(self.engine) as connection:
            window = self._window(connection, window_id)
            if window["status"] == "approved" and window["approved_by"] == operator:
                return
            if window["status"] != "previewed":
                raise ControlError("Only conflict-free successful previews may be approved")
            connection.execute(update(WINDOW).where(WINDOW.c.id == window_id,
                WINDOW.c.organization_id == self.organization_id).values(
                    status="approved", approved_by=operator, approved_at=utcnow()))

    def record_images(self, evidence_id, *, before_image, after_image):
        """Immutable future rollback evidence; does not apply either image."""
        with _ledger_connection(self.engine) as connection:
            self._tenant(connection)
            row = connection.execute(select(IDENTITY).where(IDENTITY.c.id == evidence_id,
                IDENTITY.c.organization_id == self.organization_id).with_for_update()).mappings().one_or_none()
            if not row or row["quarantined"] or row["classification"] not in {"would_insert", "would_update"}:
                raise ControlError("Nonconflicting insert/update evidence required")
            if (before_image is None) != (row["classification"] == "would_insert"):
                raise ControlError("Update requires before-image; insert requires absence")
            validate_image(after_image, row)
            if before_image is not None:
                validate_image(before_image, row)
            before_digest = fingerprint(before_image) if before_image is not None else None
            after_digest = fingerprint(after_image)
            if row["after_fingerprint"]:
                if (row["before_fingerprint"], row["after_fingerprint"]) != (before_digest, after_digest):
                    raise ControlError("Images are immutable")
                return
            connection.execute(update(IDENTITY).where(IDENTITY.c.id == evidence_id,
                IDENTITY.c.organization_id == self.organization_id).values(before_image=before_image,
                    before_fingerprint=before_digest, after_image=after_image, after_fingerprint=after_digest))


def _preview_evidence(report, window):
    if report.get("request") != {"from": window["date_from"].isoformat(), "to": window["date_to"].isoformat()}:
        raise ControlError("Preview source interval mismatch")
    if report.get("mode") != "historical_preview" or report.get("provider") != "torqueai":
        raise ControlError("Existing TorqueAI preview evidence required")
    if any(report.get(key) is not False for key in (
        "database_writes", "provider_writes", "checkpoint_modified", "claims_modified", "raw_provider_payload_returned")):
        raise ControlError("Read-only preview evidence required")
    evidence = {"request": report["request"], "window_semantics": SEMANTICS,
                "status": report["status"], "inserted": 0, "updated": 0}
    for key in ("mode", "database_writes", "provider_writes", "checkpoint_modified",
                "claims_modified", "raw_provider_payload_returned"):
        evidence[key] = report[key]
    for key in ("provider_records_received", "validated_records", "would_insert", "would_update",
                "unchanged", "identity_conflicts", "missing_usable_lane_stops"):
        value = report[key]
        if type(value) is not int or not 0 <= value <= 1000:
            raise ControlError("Invalid bounded preview count")
        evidence[key] = value
    pagination = report["pagination"]
    if (pagination["page_size"] != 100 or not 0 <= pagination["pages_fetched"] <= 10
            or len(pagination["pages"]) != pagination["pages_fetched"]):
        raise ControlError("Invalid preview pagination")
    evidence["pagination"] = {key: pagination[key] for key in ("page_size", "pages_fetched", "provider_total_count")}
    evidence["pagination"]["pages"] = [{key: page[key] for key in (
        "page", "records", "total_count", "items_per_page")} for page in pagination["pages"]]
    evidence["returned_ship_dates"] = {key: report["returned_ship_dates"][key] for key in (
        "minimum", "maximum", "outside_requested_window", "missing_or_invalid")}
    evidence["validation_failures"] = [{"code": _label(item["code"])} for item in report["validation_failures"]]
    identities = []
    seen = set()
    counts = {key: 0 for key in ("would_insert", "would_update", "unchanged", "identity_conflict")}
    for item in report["identities"]:
        # Preserve tabs/internal separators in source order identities exactly.
        load, order = item["provider_load_number"], item["provider_order_number"]
        if not isinstance(load, str) or not isinstance(order, str) or not load or not order or len(load) > 120 or len(order) > 255:
            raise ControlError("Invalid exact provider identity")
        if (load, order) in seen or item["classification"] not in counts:
            raise ControlError("Duplicate identity/invalid classification")
        seen.add((load, order)); counts[item["classification"]] += 1
        conflicts = item["conflicting_order_numbers"]
        if (not isinstance(conflicts, list) or any(not isinstance(v, str) or not v or len(v) > 255 for v in conflicts)
                or (item["classification"] == "identity_conflict" and (len(set(conflicts)) < 2 or order not in conflicts))
                or (item["classification"] != "identity_conflict" and conflicts)):
            raise ControlError("Invalid conflict quarantine evidence")
        identities.append({"provider_load_number": load, "provider_order_number": order,
            "classification": item["classification"], "conflicting_order_numbers": conflicts})
    if report["status"] == "success":
        if (len(identities) != evidence["validated_records"] or pagination["provider_total_count"] != len(identities)
                or any(counts[key] != evidence["identity_conflicts" if key == "identity_conflict" else key] for key in counts)):
            raise ControlError("Preview identity/count mismatch")
    elif report["status"] != "failed" or identities or not evidence["validation_failures"]:
        raise ControlError("Invalid failure evidence")
    evidence["identities"] = identities
    return evidence, identities


def validate_image(image, identity):
    """Full whitelisted durable bundle, not provider payload; values JSON scalars.

    Future executor must read/revalidate this bundle atomically before any update.
    No source payload, customer alias, credential, arbitrary table or SQL accepted.
    """
    from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop
    if not isinstance(image, dict) or set(image) != {"dispatch", "operational", "stops"}:
        raise ControlError("Complete durable image bundle required")
    if not isinstance(image["stops"], list):
        raise ControlError("Ordered stop image list required")
    for model, rows in ((TorqueAIDispatch, [image["dispatch"]]),
                        (TorqueAIDispatchOperational, [] if image["operational"] is None else [image["operational"]]),
                        (TorqueAIDispatchStop, image["stops"])):
        for row in rows:
            if (not isinstance(row, dict) or set(row) != set(model.__table__.columns.keys())
                    or row["organization_id"] != identity["organization_id"]
                    or any(row[column.name] is None for column in model.__table__.columns if not column.nullable)
                    or any(type(v) not in (str, int, float, bool, type(None)) for v in row.values())):
                raise ControlError("Incomplete/unsafe/cross-tenant durable image")
            if (type(row["id"]) is not int or row["id"] <= 0
                    or not isinstance(row["source_fingerprint"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", row["source_fingerprint"])):
                raise ControlError("Invalid durable row/source fingerprint")
            if model is not TorqueAIDispatch and row["dispatch_id"] != image["dispatch"]["id"]:
                raise ControlError("Image dispatch linkage mismatch")
    dispatch = image["dispatch"]
    if (dispatch["provider_load_number"], dispatch["provider_order_number"]) != (
            identity["provider_load_number"], identity["provider_order_number"]):
        raise ControlError("Image exact identity mismatch")
    indices = [row["stop_index"] for row in image["stops"]]
    if any(type(index) is not int or index < 0 for index in indices) or indices != sorted(set(indices)):
        raise ControlError("Stop indices must be unique and ordered")
    fingerprint(image)  # Reject NaN/infinite numbers and non-JSON values.


def rollback_eligible(evidence, current_image):
    """Decision only. No restore/delete writer exists in this PR.

    Full current bundle must still equal recorded after-image, not merely its
    source fingerprint. Future execution must lock and recheck atomically.
    """
    try:
        if evidence["quarantined"] or evidence["classification"] not in {"would_insert", "would_update"}:
            return False
        before, after = evidence["before_image"], evidence["after_image"]
        validate_image(after, evidence)
        if fingerprint(after) != evidence["after_fingerprint"]:
            return False
        if before is not None:
            validate_image(before, evidence)
            if fingerprint(before) != evidence["before_fingerprint"]:
                return False
        elif evidence["classification"] != "would_insert" or evidence["before_fingerprint"] is not None:
            return False
        validate_image(current_image, evidence)
        return fingerprint(current_image) == evidence["after_fingerprint"]
    except (ControlError, ValueError, TypeError, KeyError):
        return False
