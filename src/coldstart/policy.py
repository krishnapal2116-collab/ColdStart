"""Policy evaluation and documented process exit-code calculation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .findings import Finding, STATUS_VALUES, summary_counts


EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_INCOMPLETE = 3
EXIT_INTERNAL = 4


@dataclass(frozen=True)
class PolicyResult:
    name: str
    decision: str
    treat_not_verified_as: str
    violations: tuple[str, ...]
    exit_code: int
    counts: dict[str, int]
    severity_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "decision": self.decision,
            "treat_not_verified_as": self.treat_not_verified_as,
            "violations": list(self.violations),
            "exit_code": self.exit_code,
        }

    def summary(self) -> dict[str, object]:
        return {
            "overall": self.decision,
            "counts": dict(self.counts),
            "severity_counts": dict(self.severity_counts),
        }


def _severity_counts(findings: Sequence[Finding]) -> dict[str, int]:
    counts = {severity: 0 for severity in ("info", "warning", "error", "blocking")}
    for finding in findings:
        counts[finding.severity] += 1
    return counts


def evaluate_policy(findings: Sequence[Finding], *, strict: bool = False) -> PolicyResult:
    """Evaluate normalized statuses without changing any finding semantics."""

    normalized = tuple(findings)
    counts = summary_counts(normalized)
    violations: list[str] = []
    has_error = False
    has_findings = False

    for finding in normalized:
        if finding.status == "error":
            has_error = True
            violations.append(finding.check_id)
        elif finding.status == "failed":
            has_findings = True
            violations.append(finding.check_id)
        elif finding.status == "not_verified":
            if strict:
                has_findings = True
                violations.append(finding.check_id)

    unique_violations = tuple(sorted(set(violations)))
    if has_error:
        decision = "error"
        exit_code = EXIT_INTERNAL
    elif has_findings:
        decision = "needs_attention"
        exit_code = EXIT_FINDINGS
    else:
        decision = "pass"
        exit_code = EXIT_OK

    # Keep the status vocabulary centralized even when a caller passes a custom
    # Finding-like object in a test harness.
    for status in counts:
        if status not in STATUS_VALUES:
            raise ValueError(f"unsupported finding status: {status}")

    return PolicyResult(
        name="strict" if strict else "default",
        decision=decision,
        treat_not_verified_as="fail" if strict else "review",
        violations=unique_violations,
        exit_code=exit_code,
        counts=counts,
        severity_counts=_severity_counts(normalized),
    )


def calculate_exit_code(findings: Sequence[Finding], *, strict: bool = False) -> int:
    """Return only the process decision for callers that do not need metadata."""

    return evaluate_policy(findings, strict=strict).exit_code
