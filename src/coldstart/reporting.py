"""Deterministic terminal and JSON renderers for normalized audit reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from .boundary import OutputValidationError, safe_text, validate_output_path
from .findings import AuditReport, SEVERITY_RANK, validate_report


def report_dict(report: AuditReport | Mapping[str, object]) -> dict[str, object]:
    if isinstance(report, AuditReport):
        value = report.to_dict()
    elif isinstance(report, Mapping):
        value = dict(report)
    else:
        raise TypeError("report must be an AuditReport or mapping")
    validate_report(value)
    return value


def render_json(report: AuditReport | Mapping[str, object]) -> str:
    """Render one newline-terminated deterministic JSON document."""

    return (
        json.dumps(
            report_dict(report),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _terminal_text(value: object, *, limit: int = 240) -> str:
    safe = safe_text(value, limit=limit)
    # Keep redirected output deterministic even when the host terminal uses a
    # legacy code page that cannot represent repository-provided Unicode.
    safe = safe.encode("ascii", "backslashreplace").decode("ascii")
    return safe.replace("\n", "\\n").replace("\r", "\\r")


def _finding_sort_key(finding: Mapping[str, object]) -> tuple[int, str, str]:
    severity = str(finding.get("severity", "info"))
    return (SEVERITY_RANK.get(severity, len(SEVERITY_RANK)), str(finding.get("category", "")), str(finding.get("check_id", "")))


def render_terminal(
    report: AuditReport | Mapping[str, object],
    *,
    exit_code: int | None = None,
) -> str:
    """Render a stable plain-text report without changing report semantics."""

    value = report_dict(report)
    tool = value["tool"]
    repository = value["repository"]
    detection = value["detection"]
    summary = value["summary"]
    counts = summary.get("counts", {})
    if exit_code is None:
        policy = value.get("policy", {})
        exit_code = int(policy.get("exit_code", 0)) if isinstance(policy, Mapping) else 0

    candidates = detection.get("candidates", [])
    primary = detection.get("primary")
    candidate_records = [item for item in candidates if isinstance(item, Mapping)] if isinstance(candidates, list) else []
    selected_candidate: Mapping[str, object] | None = None
    if isinstance(primary, str):
        selected_candidate = next(
            (item for item in candidate_records if item.get("id") == primary),
            None,
        )
    if selected_candidate is None and candidate_records:
        selected_candidate = candidate_records[0]
    if selected_candidate is not None:
        project_type = f"{_terminal_text(selected_candidate.get('id', 'unknown'))} ({_terminal_text(selected_candidate.get('confidence', 'unknown'))})"
    else:
        project_type = "unknown (not verified)"

    lines = [
        f"ColdStart {_terminal_text(tool.get('version', 'unknown'))} | schema {_terminal_text(value.get('schema_version', 'unknown'))} | catalog {_terminal_text(tool.get('catalog_version', 'unknown'))}",
        f"Repository: {_terminal_text(repository.get('label', 'repository'))} | Type: {project_type}",
        f"Result: {_terminal_text(summary.get('overall', 'error'))}",
        "Summary: "
        + " ".join(
            f"{name}={int(counts.get(name, 0))}"
            for name in ("passed", "failed", "not_applicable", "skipped", "not_verified", "error")
        ),
    ]

    inventory = detection.get("inventory", {})
    if isinstance(inventory, Mapping):
        lines.append(
            "Inventory: "
            f"files={int(inventory.get('file_count', 0))} "
            f"bytes={int(inventory.get('total_bytes', 0))} "
            f"depth={int(inventory.get('max_depth_observed', 0))} "
            f"coverage={_terminal_text(inventory.get('coverage', 'unknown'))} "
            f"external_symlinks={int(inventory.get('external_symlink_count', 0))} "
            f"staging={_terminal_text(inventory.get('staging', 'unknown'))}"
        )
    if candidate_records:
        candidate_labels = ", ".join(
            f"{_terminal_text(item.get('id', 'unknown'))}:{_terminal_text(item.get('confidence', 'unknown'))}"
            for item in candidate_records
        )
        lines.append(f"Candidates: {candidate_labels}")
    applicability = detection.get("applicability", [])
    if isinstance(applicability, list):
        applicable_count = sum(
            1
            for item in applicability
            if isinstance(item, Mapping) and item.get("applicable") is True
        )
        lines.append(
            f"Applicability: {applicable_count}/{len(applicability)} catalog decisions applicable"
        )
    fingerprint_inputs = detection.get("fingerprint_inputs", {})
    if isinstance(fingerprint_inputs, Mapping):
        paths = fingerprint_inputs.get("paths", [])
        metadata = fingerprint_inputs.get("bounded_metadata", [])
        lines.append(
            "Fingerprint inputs: "
            f"paths={len(paths) if isinstance(paths, list) else 0} "
            f"bounded_metadata={len(metadata) if isinstance(metadata, list) else 0}"
        )

    raw_findings = value.get("findings", [])
    findings = [item for item in raw_findings if isinstance(item, Mapping)]
    for finding in sorted(findings, key=_finding_sort_key):
        severity = _terminal_text(finding.get("severity", "info")).upper()
        lines.extend(
            [
                f"[{severity}] {_terminal_text(finding.get('check_id', 'UNKNOWN'))} -- {_terminal_text(finding.get('title', 'Untitled'))}",
                f"  Status: {_terminal_text(finding.get('status', 'error'))}",
                f"  Evidence strength: {_terminal_text(finding.get('evidence_strength', 'unverified'))}",
                f"  Message: {_terminal_text(finding.get('message', ''))}",
            ]
        )
        evidence = finding.get("evidence", [])
        if isinstance(evidence, list) and evidence:
            for item in evidence:
                if not isinstance(item, Mapping):
                    continue
                path = item.get("path") or "(boundary)"
                detail = _terminal_text(item.get("detail", ""))
                lines.append(
                    f"  Evidence: {_terminal_text(path)} ({_terminal_text(item.get('kind', 'metadata'))}) -- {detail}"
                )
        remediation = finding.get("remediation")
        if remediation is None or remediation == [] or remediation == "":
            lines.append("  Fix: none recorded")
        elif isinstance(remediation, list):
            for item in remediation:
                lines.append(f"  Fix: {_terminal_text(item)}")
        else:
            lines.append(f"  Fix: {_terminal_text(remediation)}")

    verification = value.get("verification", {})
    verification_status = (
        verification.get("status", "not requested")
        if isinstance(verification, Mapping)
        else "not requested"
    )
    limitations = detection.get("limitations", [])
    lines.append(
        f"Verification: {_terminal_text(verification_status).replace('_', ' ')}"
    )
    if isinstance(limitations, list) and limitations:
        for limitation in limitations:
            lines.append(f"Limitations: {_terminal_text(limitation)}")
    else:
        lines.append("Limitations: none recorded")
    if any(
        isinstance(item, Mapping)
        and item.get("status") == "not_verified"
        and item.get("check_id") in {"CS-PROJECT-001", "CS-PROJECT-002"}
        for item in findings
    ):
        next_step = "review the discovery limitations and clarify the repository type before relying on ecosystem-specific checks."
    else:
        next_step = "review applicability decisions; the P0 catalog rule logic is outside this M2 audit scope."
    lines.append(f"Next step: {next_step}")
    lines.append(f"Exit code: {exit_code}")
    return "\n".join(lines) + "\n"


def serialize_report(
    report: AuditReport | Mapping[str, object],
    output_format: str,
    *,
    exit_code: int | None = None,
) -> str:
    if output_format == "json":
        return render_json(report)
    if output_format == "terminal":
        return render_terminal(report, exit_code=exit_code)
    raise ValueError(f"unsupported report format: {output_format}")


def write_report(text: str, output_path: str | Path) -> None:
    """Write exact UTF-8 bytes to a prevalidated explicit destination."""

    destination = validate_output_path(output_path)
    if destination is None:
        raise OutputValidationError("output path is required")
    try:
        destination.write_bytes(text.encode("utf-8"))
    except OSError as error:
        raise OutputValidationError(
            f"could not write report: {safe_text(destination.name)}"
        ) from error


# Descriptive aliases for callers that prefer serializer terminology.
serialize_json = render_json
serialize_terminal = render_terminal
