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
    fail_on: str = "info"
    incomplete: bool = False
    required_checks: tuple[str, ...] = ()
    excluded_checks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "decision": self.decision,
            "treat_not_verified_as": self.treat_not_verified_as,
            "fail_on": self.fail_on,
            "required_checks": list(self.required_checks),
            "excluded_checks": list(self.excluded_checks),
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


def evaluate_policy(
    findings: Sequence[Finding],
    *,
    strict: bool = False,
    name: str | None = None,
    treat_not_verified_as: str | None = None,
    fail_on: str = "info",
    incomplete: bool = False,
    required_checks: Sequence[str] = (),
    excluded_checks: Sequence[str] = (),
) -> PolicyResult:
    """Evaluate normalized statuses without changing any finding semantics.

    ``strict`` is retained as the small M1 API and is equivalent to
    ``treat_not_verified_as='fail'``.  M2 configuration can select an explicit
    unknown behavior and a severity threshold without reclassifying findings.
    """

    if fail_on not in {"info", "warning", "error", "blocking"}:
        raise ValueError("fail_on must be info, warning, error, or blocking")
    unknown_behavior = "fail" if strict else (treat_not_verified_as or "review")
    if unknown_behavior not in {"allow", "review", "fail"}:
        raise ValueError("treat_not_verified_as must be allow, review, or fail")
    severity_threshold = {
        "info": 0,
        "warning": 1,
        "error": 2,
        "blocking": 3,
    }[fail_on]

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
            severity_value = {
                "info": 0,
                "warning": 1,
                "error": 2,
                "blocking": 3,
            }[finding.severity]
            if severity_value >= severity_threshold:
                has_findings = True
                violations.append(finding.check_id)
        elif finding.status == "not_verified":
            if unknown_behavior == "fail":
                has_findings = True
                violations.append(finding.check_id)

    unique_violations = tuple(sorted(set(violations)))
    if has_error:
        decision = "error"
        exit_code = EXIT_INTERNAL
    elif has_findings:
        decision = "needs_attention"
        exit_code = EXIT_FINDINGS
    elif incomplete:
        decision = "incomplete"
        exit_code = EXIT_INCOMPLETE
    else:
        decision = "pass"
        exit_code = EXIT_OK

    # Keep the status vocabulary centralized even when a caller passes a custom
    # Finding-like object in a test harness.
    for status in counts:
        if status not in STATUS_VALUES:
            raise ValueError(f"unsupported finding status: {status}")

    return PolicyResult(
        name=name or ("strict" if strict else "default"),
        decision=decision,
        treat_not_verified_as=unknown_behavior,
        violations=unique_violations,
        exit_code=exit_code,
        counts=counts,
        severity_counts=_severity_counts(normalized),
        fail_on=fail_on,
        incomplete=incomplete,
        required_checks=tuple(sorted(set(required_checks))),
        excluded_checks=tuple(sorted(set(excluded_checks))),
    )


def calculate_exit_code(findings: Sequence[Finding], *, strict: bool = False) -> int:
    """Return only the process decision for callers that do not need metadata."""

    return evaluate_policy(findings, strict=strict).exit_code
