"""End-to-end bounded static audit orchestration for M2."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .applicability import ApplicabilityDecision, plan_applicability
from .boundary import (
    BoundaryLimits,
    BoundaryValidationError,
    RepositoryBoundary,
    effective_exclusions,
    normalize_exclusions,
    validate_limits,
    validate_repository,
)
from .catalog import CATALOG_BY_ID
from .checks import evaluate_dependency_checks, evaluate_runtime_and_setup_checks
from .config import ColdStartConfig, load_config
from .discovery import DetectionResult, InventoryResult, detect_projects, inventory_repository
from .findings import Applicability, AuditReport, Evidence, Finding
from .fingerprint import calculate_audit_fingerprint, canonical_json
from .policy import PolicyResult, evaluate_policy
from .version import CHECK_CATALOG_VERSION, REPORT_SCHEMA_VERSION, __version__


M1_LIMITATION = (
    "Project detection, ecosystem discovery, and P0 catalog checks were not implemented in M1."
)
M2_LIMITATION = (
    "M2 implements bounded inventory, project detection, and catalog applicability planning; "
    "those results do not prove that the repository builds or tests successfully."
)
M3_LIMITATION = (
    "M3 evaluates dependency declarations, applicable Python lock evidence, Python runtime declarations, "
    "and setup documentation statically; CS-DOCS-002 and the remaining P0 catalog rules remain outside this milestone."
)
M3_CHECK_IDS = frozenset(
    {
        "CS-DEPS-001",
        "CS-DEPS-002",
        "CS-RUNTIME-001",
        "CS-DOCS-001",
    }
)


@dataclass(frozen=True)
class AuditOptions:
    output_format: str = "terminal"
    strict: bool = False
    limits: BoundaryLimits = BoundaryLimits()
    excludes: tuple[str, ...] = ()
    config_path: str | None = None
    policy_name: str = "default"
    treat_not_verified_as: str = "review"
    fail_on: str = "info"
    required_checks: tuple[str, ...] = ()
    excluded_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.output_format not in {"terminal", "json"}:
            raise ValueError("output_format must be terminal or json")
        object.__setattr__(self, "limits", validate_limits(self.limits))
        object.__setattr__(self, "excludes", normalize_exclusions(self.excludes))
        if self.treat_not_verified_as not in {"allow", "review", "fail"}:
            raise ValueError("treat_not_verified_as must be allow, review, or fail")


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


def _generic_applicability(reason: str = "A bounded repository boundary is required for this discovery result.") -> Applicability:
    return Applicability(applicable=True, reason=reason, adapter="generic")


def _boundary_finding() -> Finding:
    return Finding(
        check_id="CS-BOUNDARY-001",
        severity="info",
        status="passed",
        title="Repository boundary and readability",
        message=(
            "The supplied repository boundary is an existing readable directory. "
            "M2 uses a bounded, read-only inventory and never executes repository code."
        ),
        evidence=(
            Evidence(
                kind="directory",
                path=".",
                detail=(
                    "The audit established a canonical readable root; no repository staging workspace was created."
                ),
            ),
        ),
        remediation=[],
        affected_path=None,
        category="project",
        applicability=_generic_applicability(),
        rule_version="2",
        evidence_strength="direct",
    )


def _inventory_finding(
    inventory: InventoryResult,
    detection: DetectionResult,
    *,
    excluded: bool = False,
) -> Finding:
    if excluded:
        return Finding(
            check_id="CS-PROJECT-001",
            severity="warning",
            status="skipped",
            title="Project metadata discovery",
            message="The configured policy excludes project metadata discovery; no discovery rule was evaluated.",
            evidence=(
                Evidence(
                    kind="policy",
                    path=None,
                    detail="The check is listed in excluded_checks in the active local policy.",
                ),
            ),
            remediation="Remove the exclusion when project metadata coverage is required.",
            affected_path=None,
            category="project",
            applicability=Applicability(
                applicable=False,
                reason="The active policy excludes this check.",
                adapter="policy",
            ),
            rule_version="2",
            evidence_strength="direct",
        )
    recognized = detection.recognized_paths
    if inventory.incomplete:
        status = "not_verified"
        severity = "warning"
        message = (
            "Bounded inventory coverage is incomplete; project metadata discovery cannot be reported as complete."
        )
        remediation: Sequence[str] | str | None = (
            "Review the inventory limit evidence and rerun with a permitted bound that covers the repository."
        )
        evidence = (
            Evidence(
                kind="error",
                path=None,
                detail=(
                    "Inventory coverage is partial: "
                    + ", ".join(inventory.omission_reasons or ("unreadable entry",))
                ),
            ),
        )
        strength = "unverified"
    elif recognized:
        status = "passed"
        severity = "info"
        message = "Bounded inventory found recognizable project metadata or source signals."
        remediation = []
        evidence_items = [
            Evidence(
                kind="metadata",
                path=path,
                detail="A deterministic inventory signal was discovered at this relative path.",
            )
            for path in recognized[:16]
        ]
        evidence_items.extend(
            Evidence(
                kind="metadata",
                path=item["path"],
                detail="An external symlink was recorded as evidence and was not followed.",
            )
            for item in inventory.external_symlinks[:8]
        )
        evidence = tuple(evidence_items)
        strength = "direct"
    else:
        status = "not_verified"
        severity = "warning"
        message = (
            "The readable repository has no recognized Python or Node project metadata signal; "
            "project metadata discovery remains not_verified."
        )
        remediation = (
            "Add a supported project metadata file or document the repository's intended build ecosystem."
        )
        evidence_items = [
            Evidence(
                kind="absence",
                path=None,
                detail=(
                    "The complete bounded inventory contained no supported metadata or source suffix signal; "
                    "this absence is not a build or test failure."
                ),
            ),
        ]
        evidence_items.extend(
            Evidence(
                kind="metadata",
                path=item["path"],
                detail="An external symlink was recorded as evidence and was not followed.",
            )
            for item in inventory.external_symlinks[:8]
        )
        evidence = tuple(evidence_items)
        strength = "absence"
    return Finding(
        check_id="CS-PROJECT-001",
        severity=severity,
        status=status,
        title="Project metadata discovery",
        message=message,
        evidence=evidence,
        remediation=remediation,
        affected_path=recognized[0] if recognized else None,
        category="project",
        applicability=_generic_applicability(
            "Bounded inventory is the precondition for project metadata discovery."
        ),
        rule_version="2",
        evidence_strength=strength,
    )


def _detection_finding(
    inventory: InventoryResult,
    detection: DetectionResult,
    *,
    excluded: bool = False,
) -> Finding:
    if excluded:
        return Finding(
            check_id="CS-PROJECT-002",
            severity="warning",
            status="skipped",
            title="Supported project type detection",
            message="The configured policy excludes project-type detection; no detection rule was evaluated.",
            evidence=(
                Evidence(
                    kind="policy",
                    path=None,
                    detail="The check is listed in excluded_checks in the active local policy.",
                ),
            ),
            remediation="Remove the exclusion when deterministic project detection is required.",
            affected_path=None,
            category="project",
            applicability=Applicability(
                applicable=False,
                reason="The active policy excludes this check.",
                adapter="policy",
            ),
            rule_version="2",
            evidence_strength="direct",
        )
    candidate = detection.candidates[0]
    if inventory.incomplete or detection.incomplete:
        status = "not_verified"
        severity = "warning"
        message = "Project-type detection is limited because bounded metadata coverage is incomplete."
        remediation: Sequence[str] | str | None = (
            "Resolve the bounded inventory or metadata parse limitation and rerun detection."
        )
        strength = "unverified"
    elif detection.primary == "mixed":
        status = "not_verified"
        severity = "warning"
        message = (
            "Both Python and Node signals were detected; ColdStart retained the mixed candidate instead of silently selecting one ecosystem."
        )
        remediation = (
            "Document the intended audit root or supported workflows for each ecosystem before relying on ecosystem-specific results."
        )
        strength = "derived"
    elif detection.primary == "unknown":
        status = "not_verified"
        severity = "warning"
        message = "No supported Python or Node candidate reached a meaningful detection threshold."
        remediation = (
            "Add recognizable project metadata or use a repository layout supported by a future adapter."
        )
        strength = "absence"
    elif candidate.confidence == "high":
        status = "passed"
        severity = "info"
        message = (
            f"A high-confidence {detection.primary} candidate was derived from bounded, non-executing signals."
        )
        remediation = []
        strength = "derived"
    else:
        status = "not_verified"
        severity = "warning"
        message = (
            f"A {candidate.confidence}-confidence {detection.primary} candidate was found, but the evidence is not sufficient for a high-confidence selection."
        )
        remediation = "Add unambiguous project metadata and rerun the audit."
        strength = "indicator"

    evidence = tuple(
        Evidence(
            kind="metadata" if candidate.evidence else "absence",
            path=path if path else None,
            detail=(
                f"Signal evidence for the {candidate.id} candidate; confidence is categorical, not probabilistic."
                if path
                else candidate.reason
            ),
        )
        for path in (candidate.evidence[:16] or (None,))
    )
    return Finding(
        check_id="CS-PROJECT-002",
        severity=severity,
        status=status,
        title="Supported project type detection",
        message=message,
        evidence=evidence,
        remediation=remediation,
        affected_path=candidate.evidence[0] if candidate.evidence else None,
        category="project",
        applicability=_generic_applicability(
            "Project candidates are planned from bounded inventory signals."
        ),
        rule_version="2",
        evidence_strength=strength,
    )


def _excluded_catalog_finding(decision: ApplicabilityDecision) -> Finding:
    """Keep configured catalog exclusions visible without evaluating a rule."""

    entry = CATALOG_BY_ID[decision.check_id]
    return Finding(
        check_id=entry.check_id,
        severity=entry.severity,
        status="skipped",
        title=entry.name,
        message=decision.reason,
        evidence=(
            Evidence(
                kind="policy",
                path=None,
                detail="The configured policy excludes this catalog check; no rule logic was run.",
            ),
        ),
        remediation="Remove this check from excluded_checks when its rule coverage is required.",
        affected_path=None,
        category=entry.category,
        applicability=Applicability(
            applicable=False,
            reason=decision.reason,
            adapter="policy",
        ),
        rule_version="2",
        evidence_strength="direct",
    )


def _scope_finding(inventory: InventoryResult) -> Finding:
    status = "not_verified" if not inventory.incomplete else "not_verified"
    return Finding(
        check_id="CS-SCOPE-001",
        severity="warning",
        status=status,
        title="Static catalog scope",
        message=(
            "M2 provides bounded discovery and applicability decisions, and M3 evaluates the first dependency, "
            "runtime, and setup-documentation checks; the remaining P0 catalog rule logic remains outside this milestone."
        ),
        evidence=(
            Evidence(
                kind="metadata",
                path=None,
                detail=(
                    "The report includes bounded M2 discovery plus M3 finding evidence; no remaining future check is represented as evaluated."
                ),
            ),
        ),
        remediation=(
            "Review the evaluated M3 findings, then use the remaining applicability evidence as input to later catalog-rule milestones; do not treat unimplemented scope as a build or test result."
        ),
        affected_path=None,
        category="project",
        applicability=_generic_applicability(
            "Every audit reports the implementation scope explicitly."
        ),
        rule_version="2",
        evidence_strength="unverified",
    )


def _merge_limits(
    configured: BoundaryLimits,
    values: BoundaryLimits | Mapping[str, object] | None,
    overrides: Mapping[str, object],
) -> BoundaryLimits:
    merged: dict[str, object] = configured.as_dict()
    if isinstance(values, BoundaryLimits):
        merged.update(values.as_dict())
    elif values is not None:
        if not isinstance(values, Mapping):
            raise BoundaryValidationError("limits must be a mapping")
        merged.update(values)
    merged.update({key: value for key, value in overrides.items() if value is not None})
    return validate_limits(merged)


def _fingerprint_inputs(
    inventory: InventoryResult,
    detection: DetectionResult,
    applicability: tuple[ApplicabilityDecision, ...],
    policy: Mapping[str, object],
    findings: Sequence[Finding],
) -> dict[str, object]:
    return {
        "paths": list(inventory.relative_paths),
        "file_metadata": [
            record.fingerprint_dict() for record in inventory.records
        ],
        "bounded_metadata": [dict(item) for item in detection.metadata_inputs],
        "inventory": inventory.stats_dict(),
        "detection": detection.to_dict(),
        "applicability": [item.to_dict() for item in applicability],
        "policy": dict(policy),
        "findings": [finding.to_dict() for finding in findings],
    }


def run_audit(
    repository_path: str,
    *,
    output_format: str | None = "terminal",
    strict: bool = False,
    limits: BoundaryLimits | Mapping[str, object] | None = None,
    config_path: str | None = None,
    excludes: Sequence[str] | None = None,
    max_files: int | None = None,
    max_bytes: int | None = None,
    max_depth: int | None = None,
    max_seconds: int | None = None,
) -> AuditResult:
    """Run bounded static discovery and return one normalized report model."""

    # Root validation happens before config parsing and before any recursive
    # operation.  It does not copy, stage, import, or execute repository data.
    initial_boundary = validate_repository(repository_path)
    config = load_config(initial_boundary.root, config_path)
    selected_limits = _merge_limits(
        config.limits,
        limits,
        {
            "max_files": max_files,
            "max_bytes": max_bytes,
            "max_depth": max_depth,
            "max_seconds": max_seconds,
        },
    )
    cli_exclusions = normalize_exclusions(excludes)
    selected_exclusions = effective_exclusions(tuple(config.excludes) + cli_exclusions)
    boundary = RepositoryBoundary(
        root=initial_boundary.root,
        label=initial_boundary.label,
        limits=selected_limits,
        exclusions=selected_exclusions,
    )

    selected_format = output_format or config.output_format
    effective_strict = bool(strict or config.strict)
    unknown_behavior = "fail" if effective_strict else config.treat_not_verified_as
    options = AuditOptions(
        output_format=selected_format,
        strict=effective_strict,
        limits=selected_limits,
        excludes=selected_exclusions,
        config_path=config.source_path,
        policy_name=config.name,
        treat_not_verified_as=unknown_behavior,
        fail_on=config.fail_on,
        required_checks=config.required_checks,
        excluded_checks=config.excluded_checks,
    )

    inventory = inventory_repository(
        boundary.root,
        limits=options.limits,
        excludes=boundary.exclusions,
    )
    detection = detect_projects(boundary.root, inventory)
    applicability = plan_applicability(
        detection,
        excluded_checks=options.excluded_checks,
    )
    m3_findings = evaluate_dependency_checks(
        boundary.root,
        inventory,
        detection,
        excluded_checks=options.excluded_checks,
    ) + evaluate_runtime_and_setup_checks(
        boundary.root,
        inventory,
        detection,
        excluded_checks=options.excluded_checks,
    )
    findings = (
        _boundary_finding(),
        _inventory_finding(
            inventory,
            detection,
            excluded="CS-PROJECT-001" in options.excluded_checks,
        ),
        _detection_finding(
            inventory,
            detection,
            excluded="CS-PROJECT-002" in options.excluded_checks,
        ),
        _scope_finding(inventory),
    ) + m3_findings + tuple(
        _excluded_catalog_finding(decision)
        for decision in applicability
        if decision.status == "skipped"
        and decision.check_id
        not in ({"CS-PROJECT-001", "CS-PROJECT-002"} | M3_CHECK_IDS)
    )
    policy_fingerprint_data = {
        "name": options.policy_name,
        "strict": options.strict,
        "treat_not_verified_as": options.treat_not_verified_as,
        "fail_on": options.fail_on,
        "required_checks": list(options.required_checks),
        "excluded_checks": list(options.excluded_checks),
        "configured": config.configured,
    }
    policy = evaluate_policy(
        findings,
        strict=options.strict,
        name=options.policy_name,
        treat_not_verified_as=options.treat_not_verified_as,
        fail_on=options.fail_on,
        incomplete=inventory.incomplete or detection.incomplete,
        required_checks=options.required_checks,
        excluded_checks=options.excluded_checks,
    )
    fingerprint_inputs = _fingerprint_inputs(
        inventory,
        detection,
        applicability,
        policy_fingerprint_data,
        findings,
    )
    fingerprint = calculate_audit_fingerprint(
        tool_version=__version__,
        catalog_version=CHECK_CATALOG_VERSION,
        policy=policy_fingerprint_data,
        limits=options.limits.as_dict(),
        relative_paths=inventory.relative_paths,
        metadata=fingerprint_inputs,
        detection={
            "candidates": [candidate.to_dict() for candidate in detection.candidates],
            "applicability": [item.to_dict() for item in applicability],
        },
    )
    scan_digest = hashlib.sha256(canonical_json(fingerprint_inputs).encode("utf-8")).hexdigest()
    detection_section = detection.to_dict()
    if inventory.incomplete:
        detection_section["status"] = "partial"
    elif detection.primary == "mixed":
        detection_section["status"] = "mixed"
    detection_section.update(
        {
            "applicability": [item.to_dict() for item in applicability],
            "inventory": inventory.stats_dict(),
            "file_inventory": [record.to_dict() for record in inventory.records],
            "scope": "M2 bounded discovery and M3 static catalog checks",
            "limitations": [M2_LIMITATION, M3_LIMITATION]
            + (["Inventory coverage is partial; rerun after reviewing limits."] if inventory.incomplete else []),
            "fingerprint_inputs": {
                "paths": list(inventory.relative_paths),
                "bounded_metadata": [dict(item) for item in detection.metadata_inputs],
                "applicability_count": len(applicability),
            },
        }
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
            "profile": options.policy_name if options.policy_name != "default" else None,
            "config_path": options.config_path,
            "limits": options.limits.as_dict(),
            "excludes": list(options.excludes),
        },
        repository={
            "label": boundary.label,
            "boundary": {
                **boundary.report_metadata(),
                "inspection": "bounded metadata inventory",
                "external_symlink_paths": [
                    item["path"] for item in inventory.external_symlinks
                ],
            },
            "audit_fingerprint": fingerprint,
            "scan_digest": scan_digest,
            "fingerprint_inputs": fingerprint_inputs,
        },
        detection=detection_section,
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
            "omitted_fields": [
                "absolute_host_paths",
                "environment_values",
                "unbounded_source_contents",
            ],
        },
        summary=policy.summary(),
    )
    return AuditResult(report=report, policy=policy, boundary=boundary)


# A concise alias for callers composing the CLI or future API layers.
audit = run_audit


__all__ = [
    "AuditOptions",
    "AuditResult",
    "BoundaryValidationError",
    "M1_LIMITATION",
    "M2_LIMITATION",
    "M3_CHECK_IDS",
    "M3_LIMITATION",
    "audit",
    "run_audit",
]
