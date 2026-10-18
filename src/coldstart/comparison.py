"""Deterministic, offline comparison of two ColdStart audit reports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .boundary import safe_text
from .findings import (
    CATEGORY_VALUES,
    EVIDENCE_KIND_VALUES,
    EVIDENCE_STRENGTH_VALUES,
    SEVERITY_RANK,
    SEVERITY_VALUES,
    STATUS_VALUES,
    normalize_relative_path,
)
from .version import CHECK_CATALOG_VERSION, COMPARISON_SCHEMA_VERSION, __version__


MAX_COMPARISON_BYTES = 10_000_000
MAX_CHECK_ID_LENGTH = 240
_FINGERPRINT_RE = re.compile(r"^[a-f0-9]{64}$")
_FINDING_FIELDS = (
    "check_id",
    "severity",
    "status",
    "title",
    "message",
    "evidence",
    "remediation",
    "affected_path",
    "category",
    "applicability",
    "rule_version",
    "evidence_strength",
)
_STATUS_RANK = {
    "passed": 0,
    "not_applicable": 0,
    "skipped": 1,
    "not_verified": 2,
    "failed": 3,
    "error": 4,
}


class ComparisonValidationError(ValueError):
    """Raised when a comparison input is not a compatible audit report."""


def _mapping(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ComparisonValidationError(f"{description} must be an object")
    return value


def _required(mapping: Mapping[str, object], field: str, description: str) -> object:
    if field not in mapping:
        raise ComparisonValidationError(f"{description} is missing {field}")
    return mapping[field]


def _string(value: object, description: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise ComparisonValidationError(f"{description} must be a non-empty string")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ComparisonValidationError("report contains a duplicate JSON key")
        result[key] = value
    return result


def _load_json(path: str | Path, label: str) -> Mapping[str, object]:
    candidate = Path(path)
    try:
        raw = candidate.read_bytes()
    except OSError as error:
        raise ComparisonValidationError(f"could not read {label} report") from error
    if len(raw) > MAX_COMPARISON_BYTES:
        raise ComparisonValidationError(
            f"{label} report exceeds the safe limit of {MAX_COMPARISON_BYTES} bytes"
        )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ComparisonValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparisonValidationError(f"{label} report is not valid UTF-8 JSON") from error
    return _mapping(value, f"{label} report")


def _validate_evidence(item: object, label: str) -> dict[str, object]:
    evidence = _mapping(item, f"{label} evidence item")
    for field in ("kind", "path", "detail"):
        _required(evidence, field, f"{label} evidence item")
    kind = _string(evidence["kind"], f"{label} evidence kind")
    if kind not in EVIDENCE_KIND_VALUES:
        raise ComparisonValidationError(f"{label} evidence kind is unsupported")
    path_value = evidence["path"]
    if path_value is not None and not isinstance(path_value, str):
        raise ComparisonValidationError(f"{label} evidence path must be a string or null")
    try:
        normalized_path = normalize_relative_path(path_value)
    except ValueError as error:
        raise ComparisonValidationError(f"{label} evidence path is invalid") from error
    detail = _string(evidence["detail"], f"{label} evidence detail", nonempty=False)
    normalized: dict[str, object] = {
        "kind": kind,
        "path": normalized_path,
        "line_start": None,
        "line_end": None,
        "detail": detail,
        "digest": None,
    }
    for field in ("line_start", "line_end"):
        value = evidence.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ComparisonValidationError(f"{label} {field} must be null or positive")
        normalized[field] = value
    digest = evidence.get("digest")
    if digest is not None and not isinstance(digest, str):
        raise ComparisonValidationError(f"{label} evidence digest must be a string or null")
    normalized["digest"] = digest
    if (
        normalized["line_start"] is not None
        and normalized["line_end"] is not None
        and normalized["line_end"] < normalized["line_start"]
    ):
        raise ComparisonValidationError(f"{label} evidence line range is invalid")
    return normalized


def _validate_finding(item: object, label: str) -> dict[str, object]:
    finding = _mapping(item, f"{label} finding")
    missing = [field for field in _FINDING_FIELDS if field not in finding]
    if missing:
        raise ComparisonValidationError(
            f"{label} finding is missing {', '.join(missing)}"
        )
    check_id = _string(finding["check_id"], f"{label} check_id")
    if len(check_id) > MAX_CHECK_ID_LENGTH:
        raise ComparisonValidationError(f"{label} check_id exceeds the safe length")
    severity = _string(finding["severity"], f"{label} severity")
    status = _string(finding["status"], f"{label} status")
    category = _string(finding["category"], f"{label} category")
    evidence_strength = _string(
        finding["evidence_strength"], f"{label} evidence_strength"
    )
    if severity not in SEVERITY_VALUES:
        raise ComparisonValidationError(f"{label} severity is unsupported")
    if status not in STATUS_VALUES:
        raise ComparisonValidationError(f"{label} status is unsupported")
    if category not in CATEGORY_VALUES:
        raise ComparisonValidationError(f"{label} category is unsupported")
    if evidence_strength not in EVIDENCE_STRENGTH_VALUES:
        raise ComparisonValidationError(f"{label} evidence_strength is unsupported")
    title = _string(finding["title"], f"{label} title", nonempty=False)
    message = _string(finding["message"], f"{label} message", nonempty=False)
    evidence = finding["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ComparisonValidationError(f"{label} evidence must be a non-empty array")
    normalized_evidence = [_validate_evidence(item, label) for item in evidence]
    normalized_evidence.sort(
        key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))
    )
    remediation = finding["remediation"]
    if remediation is not None and not isinstance(remediation, (str, list)):
        raise ComparisonValidationError(f"{label} remediation has an invalid type")
    if isinstance(remediation, list) and any(not isinstance(item, str) for item in remediation):
        raise ComparisonValidationError(f"{label} remediation must contain strings")
    affected_path = finding["affected_path"]
    if affected_path is not None and not isinstance(affected_path, str):
        raise ComparisonValidationError(f"{label} affected_path must be a string or null")
    try:
        normalized_affected_path = normalize_relative_path(affected_path)
    except ValueError as error:
        raise ComparisonValidationError(f"{label} affected_path is invalid") from error
    applicability = _mapping(finding["applicability"], f"{label} applicability")
    for field in ("applicable", "reason", "adapter"):
        _required(applicability, field, f"{label} applicability")
    if not isinstance(applicability["applicable"], bool):
        raise ComparisonValidationError(f"{label} applicability flag is invalid")
    applicability_reason = _string(
        applicability["reason"], f"{label} applicability reason", nonempty=False
    )
    applicability_adapter = _string(
        applicability["adapter"], f"{label} applicability adapter"
    )
    rule_version = _string(finding["rule_version"], f"{label} rule_version")
    return {
        "check_id": check_id,
        "severity": severity,
        "status": status,
        "title": title,
        "message": message,
        "evidence": normalized_evidence,
        "remediation": remediation,
        "affected_path": normalized_affected_path,
        "category": category,
        "applicability": {
            "applicable": applicability["applicable"],
            "reason": applicability_reason,
            "adapter": applicability_adapter,
        },
        "rule_version": rule_version,
        "evidence_strength": evidence_strength,
    }


def _validate_report(
    report: Mapping[str, object], label: str
) -> tuple[str, dict[str, dict[str, object]]]:
    required = (
        "schema_version",
        "tool",
        "invocation",
        "repository",
        "detection",
        "findings",
        "policy",
        "verification",
        "redaction",
        "summary",
    )
    missing = [field for field in required if field not in report]
    if missing:
        raise ComparisonValidationError(
            f"{label} report is missing {', '.join(missing)}"
        )
    if report["schema_version"] != "1.0":
        raise ComparisonValidationError(f"{label} report schema version is incompatible")
    tool = _mapping(report["tool"], f"{label} tool")
    if tool.get("name") != "coldstart":
        raise ComparisonValidationError(f"{label} report tool is incompatible")
    _string(_required(tool, "version", f"{label} tool"), f"{label} tool version")
    if tool.get("catalog_version") != CHECK_CATALOG_VERSION:
        raise ComparisonValidationError(f"{label} report catalog version is incompatible")
    repository = _mapping(report["repository"], f"{label} repository")
    fingerprint = _string(
        _required(repository, "audit_fingerprint", f"{label} repository"),
        f"{label} audit fingerprint",
    )
    if _FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise ComparisonValidationError(f"{label} audit fingerprint is invalid")
    findings = report["findings"]
    if not isinstance(findings, list):
        raise ComparisonValidationError(f"{label} report findings must be an array")
    normalized: dict[str, dict[str, object]] = {}
    for index, item in enumerate(findings):
        finding = _validate_finding(item, f"{label} finding {index + 1}")
        check_id = str(finding["check_id"])
        if check_id in normalized:
            raise ComparisonValidationError(f"{label} report contains duplicate check ID")
        normalized[check_id] = finding
    return fingerprint, normalized


def _direction(
    baseline: Mapping[str, object], current: Mapping[str, object]
) -> str:
    """Classify a changed finding without changing the canonical category."""

    baseline_severity = SEVERITY_RANK[str(baseline["severity"])]
    current_severity = SEVERITY_RANK[str(current["severity"])]
    baseline_status = _STATUS_RANK[str(baseline["status"])]
    current_status = _STATUS_RANK[str(current["status"])]
    severity_delta = current_severity - baseline_severity
    status_delta = current_status - baseline_status
    if severity_delta >= 0 and status_delta >= 0 and (severity_delta or status_delta):
        return "worsened"
    if severity_delta <= 0 and status_delta <= 0 and (severity_delta or status_delta):
        return "improved"
    return "changed"


def _changed_fields(
    baseline: Mapping[str, object], current: Mapping[str, object]
) -> list[str]:
    return [field for field in _FINDING_FIELDS if baseline[field] != current[field]]


def _safe_finding_summary(finding: Mapping[str, object]) -> dict[str, object]:
    """Expose only bounded, non-evidence metadata from an input finding."""

    return {
        "check_id": safe_text(finding["check_id"], limit=MAX_CHECK_ID_LENGTH),
        "severity": str(finding["severity"]),
        "status": str(finding["status"]),
        "title": safe_text(finding["title"], limit=240),
        "category": str(finding["category"]),
        "affected_path": (
            None
            if finding["affected_path"] is None
            else safe_text(finding["affected_path"], limit=240)
        ),
        "evidence_strength": str(finding["evidence_strength"]),
        "rule_version": safe_text(finding["rule_version"], limit=240),
    }


@dataclass(frozen=True)
class ComparisonResult:
    """Normalized result of comparing current findings with a baseline."""

    current_fingerprint: str
    baseline_fingerprint: str
    added: tuple[dict[str, object], ...]
    resolved: tuple[dict[str, object], ...]
    unchanged: tuple[dict[str, object], ...]
    changed: tuple[dict[str, object], ...]

    @property
    def fingerprint_status(self) -> str:
        return (
            "unchanged"
            if self.current_fingerprint == self.baseline_fingerprint
            else "changed"
        )

    @property
    def summary(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "resolved": len(self.resolved),
            "unchanged": len(self.unchanged),
            "changed": len(self.changed),
        }

    def to_dict(self, *, output_format: str = "json") -> dict[str, object]:
        """Return the versioned, JSON-safe comparison document."""

        return {
            "comparison_schema_version": COMPARISON_SCHEMA_VERSION,
            "tool": {
                "name": "coldstart",
                "version": __version__,
                "catalog_version": CHECK_CATALOG_VERSION,
            },
            "invocation": {
                "command": "compare",
                "format": output_format,
            },
            "current": {
                "label": "current",
                "audit_fingerprint": self.current_fingerprint,
            },
            "baseline": {
                "label": "baseline",
                "audit_fingerprint": self.baseline_fingerprint,
            },
            "fingerprint": {
                "comparison": self.fingerprint_status,
                "current": self.current_fingerprint,
                "baseline": self.baseline_fingerprint,
            },
            "summary": self.summary,
            "changes": {
                "added": list(self.added),
                "resolved": list(self.resolved),
                "unchanged": list(self.unchanged),
                "changed": list(self.changed),
            },
            "exit_code": 0,
        }


def compare_reports(
    current_path: str | Path,
    baseline_path: str | Path,
) -> ComparisonResult:
    """Compare two compatible reports without auditing or executing anything."""

    current_report = _load_json(current_path, "current")
    baseline_report = _load_json(baseline_path, "baseline")
    current_fingerprint, current_findings = _validate_report(current_report, "current")
    baseline_fingerprint, baseline_findings = _validate_report(
        baseline_report,
        "baseline",
    )

    added: list[dict[str, object]] = []
    resolved: list[dict[str, object]] = []
    unchanged: list[dict[str, object]] = []
    changed: list[dict[str, object]] = []
    for check_id in sorted(set(current_findings) | set(baseline_findings)):
        current = current_findings.get(check_id)
        baseline = baseline_findings.get(check_id)
        if baseline is None:
            assert current is not None
            added.append(
                {
                    "check_id": safe_text(check_id, limit=MAX_CHECK_ID_LENGTH),
                    "finding": _safe_finding_summary(current),
                }
            )
            continue
        if current is None:
            resolved.append(
                {
                    "check_id": safe_text(check_id, limit=MAX_CHECK_ID_LENGTH),
                    "finding": _safe_finding_summary(baseline),
                }
            )
            continue
        fields = _changed_fields(baseline, current)
        if not fields:
            unchanged.append(
                {
                    "check_id": safe_text(check_id, limit=MAX_CHECK_ID_LENGTH),
                    "severity": current["severity"],
                    "status": current["status"],
                }
            )
            continue
        changed.append(
            {
                "check_id": safe_text(check_id, limit=MAX_CHECK_ID_LENGTH),
                "direction": _direction(baseline, current),
                "changed_fields": fields,
                "baseline": _safe_finding_summary(baseline),
                "current": _safe_finding_summary(current),
            }
        )
    return ComparisonResult(
        current_fingerprint=current_fingerprint,
        baseline_fingerprint=baseline_fingerprint,
        added=tuple(added),
        resolved=tuple(resolved),
        unchanged=tuple(unchanged),
        changed=tuple(changed),
    )


__all__ = [
    "ComparisonResult",
    "ComparisonValidationError",
    "MAX_COMPARISON_BYTES",
    "MAX_CHECK_ID_LENGTH",
    "compare_reports",
]
