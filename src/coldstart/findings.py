"""Normalized finding and report data objects for ColdStart."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


STATUS_VALUES = (
    "passed",
    "failed",
    "not_applicable",
    "skipped",
    "not_verified",
    "error",
)
SEVERITY_VALUES = ("info", "warning", "error", "blocking")
EVIDENCE_STRENGTH_VALUES = (
    "direct",
    "derived",
    "indicator",
    "absence",
    "unverified",
)
EVIDENCE_KIND_VALUES = (
    "file",
    "directory",
    "metadata",
    "command",
    "absence",
    "execution",
    "policy",
    "error",
)
CATEGORY_VALUES = (
    "project",
    "dependencies",
    "runtime",
    "documentation",
    "configuration",
    "portability",
    "security",
    "build",
    "execution",
)
SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITY_VALUES)}


def normalize_relative_path(path: str | None) -> str | None:
    """Normalize a project-relative report path and reject escapes."""

    if path is None:
        return None
    value = str(path).replace("\\", "/")
    if not value:
        return "."
    if value.startswith("/") or (
        len(value) >= 2 and value[1] == ":" and value[0].isalpha()
    ):
        raise ValueError("evidence paths must be relative")
    parts: list[str] = []
    for part in value.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("evidence path escapes the repository boundary")
        parts.append(part)
    return "/".join(parts) if parts else "."


@dataclass(frozen=True)
class Evidence:
    kind: str
    path: str | None
    detail: str
    line_start: int | None = None
    line_end: int | None = None
    digest: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in EVIDENCE_KIND_VALUES:
            raise ValueError(f"unsupported evidence kind: {self.kind}")
        object.__setattr__(self, "path", normalize_relative_path(self.path))
        if self.line_start is not None and (
            isinstance(self.line_start, bool)
            or not isinstance(self.line_start, int)
            or self.line_start < 1
        ):
            raise ValueError("line_start must be null or positive")
        if self.line_end is not None and (
            isinstance(self.line_end, bool)
            or not isinstance(self.line_end, int)
            or self.line_end < 1
        ):
            raise ValueError("line_end must be null or positive")
        if self.line_start is not None and self.line_end is not None:
            if self.line_end < self.line_start:
                raise ValueError("line_end cannot precede line_start")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "detail": str(self.detail),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class Applicability:
    applicable: bool
    reason: str
    adapter: str

    def to_dict(self) -> dict[str, object]:
        return {
            "applicable": self.applicable,
            "reason": self.reason,
            "adapter": self.adapter,
        }


@dataclass(frozen=True)
class Finding:
    check_id: str
    severity: str
    status: str
    title: str
    message: str
    evidence: tuple[Evidence, ...] | Sequence[Evidence]
    remediation: tuple[str, ...] | Sequence[str] | str | None = None
    affected_path: str | None = None
    category: str = "project"
    applicability: Applicability = field(
        default_factory=lambda: Applicability(
            applicable=True,
            reason="The finding applies to the inspected boundary.",
            adapter="generic",
        )
    )
    rule_version: str = "1"
    evidence_strength: str = "unverified"

    def __post_init__(self) -> None:
        if not self.check_id:
            raise ValueError("check_id is required")
        if self.severity not in SEVERITY_VALUES:
            raise ValueError(f"unsupported severity: {self.severity}")
        if self.status not in STATUS_VALUES:
            raise ValueError(f"unsupported status: {self.status}")
        if self.category not in CATEGORY_VALUES:
            raise ValueError(f"unsupported category: {self.category}")
        if self.evidence_strength not in EVIDENCE_STRENGTH_VALUES:
            raise ValueError(f"unsupported evidence strength: {self.evidence_strength}")
        normalized_evidence = tuple(self.evidence)
        if not normalized_evidence:
            raise ValueError("a finding requires at least one evidence item")
        if any(not isinstance(item, Evidence) for item in normalized_evidence):
            raise ValueError("finding evidence must contain Evidence objects")
        object.__setattr__(self, "evidence", normalized_evidence)
        if self.remediation is None:
            normalized_remediation: tuple[str, ...] | str | None = None
        elif isinstance(self.remediation, str):
            normalized_remediation = self.remediation
        else:
            normalized_remediation = tuple(str(item) for item in self.remediation)
        object.__setattr__(self, "remediation", normalized_remediation)
        object.__setattr__(self, "affected_path", normalize_relative_path(self.affected_path))

    def to_dict(self) -> dict[str, object]:
        evidence = sorted(
            (item.to_dict() for item in self.evidence),
            key=lambda item: (
                str(item["path"] or ""),
                str(item["kind"]),
                str(item["detail"]),
            ),
        )
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "status": self.status,
            "title": str(self.title),
            "message": str(self.message),
            "evidence": evidence,
            "remediation": (
                list(self.remediation)
                if isinstance(self.remediation, tuple)
                else self.remediation
            ),
            "affected_path": self.affected_path,
            "category": self.category,
            "applicability": self.applicability.to_dict(),
            "rule_version": self.rule_version,
            "evidence_strength": self.evidence_strength,
        }


def normalize_findings(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    """Sort findings using the contract's stable severity/category/check order."""

    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                SEVERITY_RANK[finding.severity],
                finding.category,
                finding.check_id,
            ),
        )
    )


def summary_counts(findings: Sequence[Finding]) -> dict[str, int]:
    counts = {status: 0 for status in STATUS_VALUES}
    for finding in findings:
        counts[finding.status] += 1
    return counts


@dataclass(frozen=True)
class AuditReport:
    """The normalized report model consumed by both serializers."""

    schema_version: str
    tool: Mapping[str, object]
    invocation: Mapping[str, object]
    repository: Mapping[str, object]
    detection: Mapping[str, object]
    findings: tuple[Finding, ...] | Sequence[Finding]
    policy: Mapping[str, object]
    verification: Mapping[str, object]
    redaction: Mapping[str, object]
    summary: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", normalize_findings(tuple(self.findings)))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool": dict(self.tool),
            "invocation": dict(self.invocation),
            "repository": dict(self.repository),
            "detection": dict(self.detection),
            "findings": [finding.to_dict() for finding in self.findings],
            "policy": dict(self.policy),
            "verification": dict(self.verification),
            "redaction": dict(self.redaction),
            "summary": dict(self.summary),
        }


def validate_report(report: Mapping[str, object]) -> None:
    """Validate the required M1 report shape before serialization."""

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
    missing = [name for name in required if name not in report]
    if missing:
        raise ValueError(f"report is missing required fields: {', '.join(missing)}")
    if report["schema_version"] != "1.0":
        raise ValueError("report schema_version must be 1.0")
    if not isinstance(report["findings"], list):
        raise ValueError("report findings must be an array")
