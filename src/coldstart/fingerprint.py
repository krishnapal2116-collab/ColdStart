"""Deterministic audit fingerprint calculation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import PurePath
from typing import Any

from .findings import normalize_relative_path


def canonical_json(value: object) -> str:
    """Serialize normalized fingerprint inputs without platform variation."""

    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_value(value: Any) -> Any:
    if isinstance(value, PurePath):
        return str(value).replace("\\", "/")
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, set):
        normalized = [_normalize_value(item) for item in value]
        return sorted(normalized, key=canonical_json)
    return value


def calculate_audit_fingerprint(
    *,
    tool_version: str,
    catalog_version: str,
    policy: Mapping[str, object],
    limits: Mapping[str, object],
    relative_paths: Iterable[str] = (),
    metadata: Mapping[str, object] | None = None,
    detection: Mapping[str, object] | None = None,
) -> str:
    """Hash the bounded, normalized evidence inputs defined by the contract.

    Absolute roots, timestamps, report IDs, and terminal formatting are never
    accepted as fingerprint inputs.  M1 supplies only ``."`` and root metadata;
    later discovery can add normalized relative paths and bounded digests.
    """

    normalized_paths = sorted(
        path
        for path in (normalize_relative_path(path) for path in relative_paths)
        if path is not None
    )
    payload = {
        "catalog_version": str(catalog_version),
        "detection": _normalize_value(detection or {}),
        "limits": _normalize_value(dict(limits)),
        "metadata": _normalize_value(metadata or {}),
        "paths": normalized_paths,
        "policy": _normalize_value(dict(policy)),
        "tool_version": str(tool_version),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# Short aliases keep the module convenient for callers while retaining the
# explicit name used by the report contract.
audit_fingerprint = calculate_audit_fingerprint
fingerprint_audit = calculate_audit_fingerprint
