"""Shared location confidence thresholds used by operational intelligence."""
from datetime import datetime, timezone

HIGH_CONFIDENCE_LOCATION_MAX_AGE_MINUTES = 30.0
STALE_LOCATION_MAX_AGE_MINUTES = 120.0


def utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def age_minutes(value, now):
    """Future observations are invalid, not zero-age fresh evidence."""
    if value is None:
        return None
    age = (utc(now) - utc(value)).total_seconds() / 60
    return age if age >= 0 else None


def location_confidence(age):
    if age is None:
        return "unknown"
    if age <= HIGH_CONFIDENCE_LOCATION_MAX_AGE_MINUTES:
        return "high"
    if age <= STALE_LOCATION_MAX_AGE_MINUTES:
        return "medium"
    return "low"


def fresh(value, now):
    age = age_minutes(value, now)
    return age is not None and age <= STALE_LOCATION_MAX_AGE_MINUTES
