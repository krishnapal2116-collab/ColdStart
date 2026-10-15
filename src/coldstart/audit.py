"""M1 end-to-end static audit orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .boundary import (
    BoundaryLimits,
    BoundaryValidationError,
    RepositoryBoundary,
    validate_limits,
    validate_repository,
)
from .findings import Applicability, AuditReport, Evidence, Finding
from .fingerprint import calculate_audit_fingerprint
from .policy import PolicyResult, evaluate_policy
from .version import CHECK_CATALOG_VERSION, REPORT_SCHEMA_VERSION, __version__


M1_LIMITATION = (
    "Project detection, ecosystem discovery, and P0 catalog checks are not implemented in M1."
)


@dataclass(frozen=True)
class AuditOptions:
    output_format: str = "terminal"
    strict: bool = False
    limits: BoundaryLimits = BoundaryLimits()

    def __post_init__(self) -> None:
        if self.output_format not in {"terminal", "json"}:
            raise ValueError("output_format must be terminal or json")
        object.__setattr__(self, "limits", validate_limits(self.limits))


@dataclass(frozen=True)
class AuditResult:
    report: AuditReport
    policy: PolicyResult
    boundary: RepositoryBoundary

    @property
    def exit_code(self) -> int:
        return self.policy.exit_code

    def to_dict(self) -> dict[str, object]:
        return self.report.to_dict()


def _boundary_finding() -> Finding:
    return Finding(
        check_id="CS-BOUNDARY-001",
        severity="info",
        status="passed",
        title="Repository boundary and readability",
        message=(
            "The supplied repository boundary is an existing readable directory; "
            "no project files were read or executed."
        ),
        evidence=(
            Evidence(
                kind="directory",
                path=".",
                detail="The audit opened the repository directory for bounded metadata validation.",
            ),
        ),
        remediation=[],
        affected_path=None,
        category="project",
        applicability=Applicability(
            applicable=True,
            reason="A readable repository boundary is required for every audit.",
            adapter="generic",
        ),
        rule_version="1",
        evidence_strength="direct",
    )


def run_audit(
    repository_path: str,
    *,
    output_format: str = "terminal",
    strict: bool = False,
    limits: BoundaryLimits | Mapping[str, object] | None = None,
) -> AuditResult:
    """Run the safe M1 audit and return one normalized report model.

    The only repository operation is root-boundary validation.  No project file
    is imported, parsed, spawned, modified, or copied.
    """

    options = AuditOptions(
        output_format=output_format,
        strict=strict,
        limits=validate_limits(limits),
    )
    boundary = validate_repository(repository_path, limits=options.limits)
    findings = (_boundary_finding(),)
    policy = evaluate_policy(findings, strict=options.strict)

    policy_fingerprint_data = {
        "name": policy.name,
        "strict": options.strict,
        "treat_not_verified_as": policy.treat_not_verified_as,
    }
    detection = {
        "candidates": [],
        "applicability": [],
        "status": "not_implemented",
        "scope": "M1 boundary/readability only",
        "limitations": [M1_LIMITATION],
    }
    fingerprint = calculate_audit_fingerprint(
        tool_version=__version__,
        catalog_version=CHECK_CATALOG_VERSION,
        policy=policy_fingerprint_data,
        limits=options.limits.as_dict(),
        relative_paths=(".",),
        metadata={
            "external_symlinks": boundary.external_symlinks,
            "readable": boundary.readable,
            "root_kind": "directory",
        },
        detection={"candidates": [], "applicability": []},
    )

    report = AuditReport(
        schema_version=REPORT_SCHEMA_VERSION,
        tool={
            "name": "coldstart",
            "version": __version__,
            "catalog_version": CHECK_CATALOG_VERSION,
        },
        invocation={
            "command": "audit",
            "format": options.output_format,
            "strict": options.strict,
            "profile": None,
            "config_path": None,
            "limits": options.limits.as_dict(),
        },
        repository={
            "label": boundary.label,
            "boundary": boundary.report_metadata(),
            "audit_fingerprint": fingerprint,
            "scan_digest": None,
        },
        detection=detection,
        findings=findings,
        policy=policy.to_dict(),
        verification={
            "requested": [],
            "authorized": [],
            "executions": [],
            "status": "not_requested",
        },
        redaction={
            "mode": "default",
            "redacted_count": 0,
            "omitted_fields": ["absolute_host_paths", "environment_values"],
        },
        summary=policy.summary(),
    )
    return AuditResult(report=report, policy=policy, boundary=boundary)


# A concise alias for callers composing the CLI or a future API.
audit = run_audit


__all__ = [
    "AuditOptions",
    "AuditResult",
    "BoundaryValidationError",
    "M1_LIMITATION",
    "audit",
    "run_audit",
]
