"""Privacy-safe JSON schema observation helpers for TorqueAI certification.

The schema observer reports key paths and JSON types only. The narrow stop-job
observer returns only bounded categorical ``stops[].job`` values and never the
provider records they came from.
"""

from __future__ import annotations

import re
from typing import Any


_SAFE_JOB_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _/-]{0,31}$")


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def schema_paths(value: Any, *, prefix: str = "", max_depth: int = 6) -> dict[str, str]:
    """Return deterministic JSON key paths/types without retaining values.

    Arrays are represented with ``[]``. All observed array items are walked so
    optional keys present in later stop records can be certified as well.
    """
    observed: dict[str, str] = {}

    def walk(node: Any, path: str, depth: int) -> None:
        if depth > max_depth:
            return
        if path:
            observed[path] = json_type_name(node)
        if isinstance(node, dict):
            for key in sorted(node):
                child_path = f"{path}.{key}" if path else str(key)
                walk(node[key], child_path, depth + 1)
        elif isinstance(node, list):
            item_path = f"{path}[]" if path else "[]"
            for item in node:
                item_type = json_type_name(item)
                prior = observed.get(item_path)
                if prior is None:
                    observed[item_path] = item_type
                elif prior != item_type:
                    observed[item_path] = "mixed"
                walk(item, item_path, depth + 1)

    walk(value, prefix, 0)
    return dict(sorted(observed.items()))


def dispatch_schema_paths(records: tuple[dict[str, Any], ...]) -> dict[str, str]:
    """Union key paths/types across a certified response page without values."""
    merged: dict[str, str] = {}
    for record in records:
        for path, type_name in schema_paths(record).items():
            previous = merged.get(path)
            if previous is None:
                merged[path] = type_name
            elif previous != type_name:
                merged[path] = "mixed"
    return dict(sorted(merged.items()))


def dispatch_stop_job_values(
    records: tuple[dict[str, Any], ...],
    *,
    max_distinct_values: int = 20,
) -> tuple[str, ...]:
    """Return only safe, distinct categorical ``stops[].job`` strings.

    This deliberately does not return stop sequence, location, load identity,
    customer, appointment, notes, or any surrounding record context. Values
    that look like free text rather than a short category token fail closed.
    """
    if not isinstance(max_distinct_values, int) or isinstance(max_distinct_values, bool) or max_distinct_values < 1:
        raise ValueError("invalid stop job certification bound")

    observed: set[str] = set()
    for record in records:
        stops = record.get("stops")
        if not isinstance(stops, list):
            continue
        for stop in stops:
            if not isinstance(stop, dict):
                continue
            raw_job = stop.get("job")
            if raw_job is None:
                continue
            if not isinstance(raw_job, str):
                raise ValueError("stop job value is not a string")
            job = raw_job.strip()
            if not job:
                continue
            if not _SAFE_JOB_VALUE_RE.fullmatch(job):
                raise ValueError("stop job value is not a safe categorical token")
            observed.add(job)
            if len(observed) > max_distinct_values:
                raise ValueError("too many distinct stop job values")

    return tuple(sorted(observed, key=lambda value: (value.casefold(), value)))
