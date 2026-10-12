"""Minimized dispatch update review, never an executor or rollback writer."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re

from app.connectors.torqueai_ingestion import _canonical_value, _persisted_values

FIELDS = (
    "provider_load_number", "provider_order_number", "status", "order_date_text",
    "ship_date_text", "delivery_date_text", "customer_name", "dispatcher_name",
    "driver_name", "carrier_name", "truck_number", "trailer_number", "loaded_miles",
)


class EvidenceError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def image(values):
    return {key: _canonical_value(values[key]) for key in FIELDS}


def validate_image(value, load, order):
    if (not isinstance(value, dict) or set(value) != set(FIELDS)
            or any(v is not None and not isinstance(v, str) for v in value.values())
            or (value["provider_load_number"], value["provider_order_number"]) != (load, order)):
        raise EvidenceError("Invalid minimized dispatch image")
    if value["loaded_miles"] is not None:
        try:
            miles = Decimal(value["loaded_miles"])
            if not miles.is_finite() or miles < 0 or _canonical_value(miles) != value["loaded_miles"]:
                raise EvidenceError("Invalid normalized miles")
        except ArithmeticError as exc:
            raise EvidenceError("Invalid normalized miles") from exc


def build_review(current, proposed, operational_fingerprint):
    before, after = image(current), image(_persisted_values(proposed))
    review = {
        "dispatch_id": current["id"], "organization_id": current["organization_id"],
        "provider_load_number": proposed.provider_load_number,
        "provider_order_number": proposed.provider_order_number,
        "before_image": before, "proposed_image": after,
        "before_hash": digest(before), "proposed_hash": digest(after),
        "current_source_fingerprint": current["source_fingerprint"],
        "proposed_source_fingerprint": proposed.source_fingerprint,
        "current_operational_fingerprint": current["operational_fingerprint"],
        "proposed_operational_fingerprint": operational_fingerprint,
        "changed_fields": sorted(k for k in FIELDS if before[k] != after[k]),
    }
    validate_review(review)
    return review


REVIEW_KEYS = frozenset(("dispatch_id", "organization_id", "provider_load_number", "provider_order_number",
    "before_image", "proposed_image", "before_hash", "proposed_hash", "current_source_fingerprint",
    "proposed_source_fingerprint", "current_operational_fingerprint", "proposed_operational_fingerprint",
    "changed_fields"))


def validate_review(review):
    if not isinstance(review, dict) or set(review) != REVIEW_KEYS:
        raise EvidenceError("Unexpected update review fields")
    if type(review["dispatch_id"]) is not int or review["dispatch_id"] <= 0 or not review["organization_id"]:
        raise EvidenceError("Invalid durable reference")
    for key in ("current_source_fingerprint", "proposed_source_fingerprint", "before_hash", "proposed_hash",
                "current_operational_fingerprint", "proposed_operational_fingerprint"):
        value = review[key]
        if value is None and key == "current_operational_fingerprint":
            continue
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise EvidenceError("Invalid review fingerprint")
    for key, hash_key in (("before_image", "before_hash"), ("proposed_image", "proposed_hash")):
        validate_image(review[key], review["provider_load_number"], review["provider_order_number"])
        if digest(review[key]) != review[hash_key]:
            raise EvidenceError("Review image integrity failure")
    if review["changed_fields"] != sorted(k for k in FIELDS if review["before_image"][k] != review["proposed_image"][k]):
        raise EvidenceError("Review diff integrity failure")
    proposed_digest = hashlib.sha256(json.dumps({k: review["proposed_image"][k] for k in FIELDS},
        ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode()).hexdigest()
    if proposed_digest != review["proposed_source_fingerprint"]:
        raise EvidenceError("Proposed normalized fingerprint mismatch")


def envelope(review, *, manifest_id, window_id, attempt_id, identity_evidence_id, code_sha, created_at):
    validate_review(review)
    return {"schema_version": 1, "classification": "would_update", "quarantined": False,
            "manifest_id": manifest_id, "window_id": window_id, "attempt_id": attempt_id,
            "identity_evidence_id": identity_evidence_id, "code_sha": code_sha,
            "created_at": created_at.isoformat(), "review": review}


def validate_record(row):
    """Reject tampered images, diffs, hashes and tenant/attempt/row linkage."""
    payload = row["evidence"]
    expected = {"schema_version", "classification", "quarantined", "manifest_id", "window_id",
                "attempt_id", "identity_evidence_id", "code_sha", "created_at", "review"}
    if set(payload) != expected or payload["schema_version"] != 1 or payload["classification"] != "would_update" or payload["quarantined"] is not False:
        raise EvidenceError("Invalid update envelope")
    validate_review(payload["review"])
    if digest(payload) != row["evidence_fingerprint"]:
        raise EvidenceError("Update evidence integrity failure")
    for key in ("organization_id", "dispatch_id", "provider_load_number", "provider_order_number"):
        if payload["review"][key] != row[key]:
            raise EvidenceError("Update identity linkage failure")
    for key in ("manifest_id", "window_id", "attempt_id", "identity_evidence_id"):
        if payload[key] != row[key]:
            raise EvidenceError("Update attempt linkage failure")
    timestamp = datetime.fromisoformat(payload["created_at"])
    stored = row["created_at"]
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    if timestamp != stored:
        raise EvidenceError("Update timestamp linkage failure")


def current_matches_before(row, current):
    """Read-only row decision. Also require valid attempt summary before use.

    Future writes must verify the attempt-bound evidence and lock/recheck atomically.
    """
    try:
        validate_record(row)
        review = row["evidence"]["review"]
        return (all(current[k] == review[k] for k in ("organization_id", "provider_load_number", "provider_order_number"))
                and current["id"] == review["dispatch_id"] and digest(image(current)) == review["before_hash"]
                and current["source_fingerprint"] == review["current_source_fingerprint"]
                and current["operational_fingerprint"] == review["current_operational_fingerprint"])
    except (EvidenceError, KeyError, TypeError, ValueError):
        return False
