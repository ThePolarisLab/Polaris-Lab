"""Privacy-safe JSON schema observation helpers for TorqueAI certification.

The observer reports key paths and JSON types only. It never returns provider values.
"""

from __future__ import annotations

from typing import Any


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
