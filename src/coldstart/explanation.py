"""Offline explanations for the reviewed P0 check catalog.

The explanation command is deliberately separate from auditing.  Its content
is bundled metadata derived from the reviewed catalog; it never needs a
repository path, reads no project files, and does not execute a check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .catalog import CATALOG, CATALOG_BY_ID, CATALOG_CHECK_IDS, CatalogEntry


class UnknownCheckError(ValueError):
    """Raised when an explanation is requested for an unregistered check."""


@dataclass(frozen=True)
class CheckExplanation:
    """Complete, deterministic explanation metadata for one catalog check."""

    check_id: str
    name: str
    severity: str
    category: str
    adapters: tuple[str, ...]
    purpose: str
    applicability: str
    algorithm: str
    evidence: str
    limitations: str
    remediation: str
    test_references: tuple[str, ...]


@dataclass(frozen=True)
class _ExplanationDetails:
    """The explanatory fields that are not already owned by CatalogEntry."""

    purpose: str
    applicability: str
    algorithm: str
    evidence: str
    limitations: str
    remediation: str
    test_references: tuple[str, ...]


def _details(
    *,
    purpose: str,
    applicability: str,
    algorithm: str,
    evidence: str,
    limitations: str,
    remediation: str,
    test_references: tuple[str, ...],
) -> _ExplanationDetails:
    """Create one immutable metadata record with a readable call site."""

    return _ExplanationDetails(
        purpose=purpose,
        applicability=applicability,
        algorithm=algorithm,
        evidence=evidence,
        limitations=limitations,
        remediation=remediation,
        test_references=test_references,
    )


_DETAILS: Mapping[str, _ExplanationDetails] = {
    "CS-PROJECT-001": _details(
        purpose=(
            "Establish whether the bounded repository contains recognizable "
            "project or source metadata before ecosystem-specific checks run."
        ),
        applicability=(
            "Generic; considered for every readable repository with a bounded "
            "inventory."
        ),
        algorithm=(
            "Collect a sorted, bounded metadata inventory and correlate supported "
            "project marker paths with the detected candidates. Incomplete or "
            "unreadable inventory evidence remains explicitly incomplete."
        ),
        evidence=(
            "Relative metadata paths, inventory coverage state, candidate signals, "
            "and an evidence-strength classification; no source command is run."
        ),
        limitations=(
            "Custom build systems and unusual layouts may not be recognized, and "
            "metadata presence does not prove that the project is complete."
        ),
        remediation=(
            "Add supported project metadata and a concise setup README, then rerun "
            "the bounded audit."
        ),
        test_references=(
            "tests/test_phase3_m2_discovery.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-001)",
        ),
    ),
    "CS-PROJECT-002": _details(
        purpose=(
            "Identify Python, Node, unknown, or mixed project candidates without "
            "silently selecting one ecosystem."
        ),
        applicability=(
            "Generic; candidate detection runs for every bounded repository and "
            "preserves ambiguity."
        ),
        algorithm=(
            "Score supported metadata names and source suffixes deterministically, "
            "classify confidence as low, medium, or high, and retain all material "
            "candidates in stable order."
        ),
        evidence=(
            "Candidate IDs, categorical confidence, relative signal paths, and "
            "bounded reasons explaining the selection or ambiguity."
        ),
        limitations=(
            "Confidence is a category rather than proof; custom ecosystems and "
            "ambiguous monorepos can remain unknown or mixed."
        ),
        remediation=(
            "Add unambiguous ecosystem metadata and document the intended project "
            "entry point when the repository contains multiple candidates."
        ),
        test_references=(
            "tests/test_phase3_m2_discovery.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-002)",
        ),
    ),
    "CS-DEPS-001": _details(
        purpose=(
            "Detect high-confidence Python third-party imports that are not "
            "declared by the supported dependency metadata."
        ),
        applicability=(
            "Python candidates only; non-Python repositories receive an explicit "
            "not-applicable result."
        ),
        algorithm=(
            "Parse bounded dependency metadata and Python AST imports, normalize "
            "distribution names, exclude standard-library and local modules, and "
            "apply the reviewed import-to-distribution aliases."
        ),
        evidence=(
            "Relative declaration/import paths, import locations, normalized "
            "package names, parser limitations, and bounded coverage details."
        ),
        limitations=(
            "Dynamic or generated imports, vendored code, namespace packages, and "
            "unmapped distributions can remain uncertain; no dependency is installed."
        ),
        remediation=(
            "Declare every required runtime and development dependency in the "
            "supported metadata and keep the declaration aligned with imports."
        ),
        test_references=(
            "tests/test_phase3_m3_dependencies.py",
            "tests/test_phase3_m3_integration.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-003)",
        ),
    ),
    "CS-DEPS-002": _details(
        purpose=(
            "Require lock evidence when a Python project declares or imports "
            "dependencies, while leaving dependency-free projects not applicable."
        ),
        applicability=(
            "Python candidates with dependency evidence; dependency-free projects "
            "and unrelated ecosystem lockfiles are not applicable."
        ),
        algorithm=(
            "Recognize supported Python lockfile names and fully pinned requirements "
            "only when bounded documentation identifies the pinned file as the "
            "reproducibility source."
        ),
        evidence=(
            "Accepted lockfile or pinned-requirements path, documentation reference, "
            "or explicit bounded absence; freshness is not inferred."
        ),
        limitations=(
            "Static inspection cannot prove lock freshness, resolver consistency, "
            "or that native dependencies can be installed on the target machine."
        ),
        remediation=(
            "Generate and commit the lockfile used by the documented workflow, or "
            "clearly document a supported fully pinned alternative."
        ),
        test_references=(
            "tests/test_phase3_m3_dependencies.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-004)",
        ),
    ),
    "CS-RUNTIME-001": _details(
        purpose=(
            "Find a consistent machine-readable Python runtime declaration for a "
            "clean checkout."
        ),
        applicability=(
            "Python candidates only; other ecosystems are explicitly not applicable."
        ),
        algorithm=(
            "Read bounded .python-version and pyproject.toml runtime records, parse "
            "exact versions and supported ranges, and detect missing, malformed, "
            "or non-overlapping declarations."
        ),
        evidence=(
            "Relative declaration paths, line metadata, normalized version ranges, "
            "and a direct/derived evidence classification."
        ),
        limitations=(
            "The check does not prove the host interpreter, native dependency "
            "availability, or every runtime claim in Docker, CI, or prose."
        ),
        remediation=(
            "Align the pinned runtime, requires-python range, Docker/CI declarations, "
            "and setup documentation."
        ),
        test_references=(
            "tests/test_phase3_m3_runtime_docs.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-005)",
        ),
    ),
    "CS-DOCS-001": _details(
        purpose=(
            "Determine whether a new developer can find prerequisite, installation, "
            "configuration, and run guidance."
        ),
        applicability=(
            "Generic; evaluated for detected repositories when bounded documentation "
            "can be inspected."
        ),
        algorithm=(
            "Scan bounded README and documentation files for headings and supported "
            "setup, runtime, configuration, and run patterns, preserving missing or "
            "unreadable evidence as limitations."
        ),
        evidence=(
            "Relative documentation paths, matched guidance categories, explicit "
            "absence, and parser/coverage limitations; prose is not executed."
        ),
        limitations=(
            "This is bounded English-pattern analysis rather than natural-language "
            "comprehension or proof that every referenced command works."
        ),
        remediation=(
            "Document one clean-checkout sequence covering prerequisites, runtime, "
            "installation, configuration, and how to run the project."
        ),
        test_references=(
            "tests/test_phase3_m3_runtime_docs.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-006)",
        ),
    ),
    "CS-DOCS-002": _details(
        purpose=(
            "Identify a usable documented test command for a test-bearing repository "
            "and compare it with static test metadata."
        ),
        applicability=(
            "Repositories with test files, test configuration, or other bounded test "
            "workflow evidence; unsupported compositions remain unverified."
        ),
        algorithm=(
            "Inspect bounded test files, pytest/tox/nox configuration, Make targets, "
            "CI jobs, dependency groups, and simple command families. Shell chains "
            "are evidence but are never treated as executable candidates."
        ),
        evidence=(
            "Relative test-bearing paths, command family/display, configuration or "
            "CI evidence, and contradiction details without running the command."
        ),
        limitations=(
            "Only supported simple command forms are comparable; tool availability, "
            "test correctness, and shell behavior are not proven statically."
        ),
        remediation=(
            "Document one portable test command and align its declared dependency and "
            "configuration with the repository's actual test layout."
        ),
        test_references=(
            "tests/test_phase4_m4_docs_config.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-007)",
        ),
    ),
    "CS-CONFIG-001": _details(
        purpose=(
            "Find a safe configuration template when source or documentation shows "
            "that configuration is expected."
        ),
        applicability=(
            "Repositories with configuration signals; without such a signal the "
            "check is not applicable."
        ),
        algorithm=(
            "Identify supported example-template paths, extract bounded variable or "
            "key names, reject credential-shaped values, and compare required names "
            "with the safe template."
        ),
        evidence=(
            "Relative source/template paths and variable names only; live environment "
            "values and credential contents are never read into the report."
        ),
        limitations=(
            "Dynamic configuration mechanisms and runtime necessity cannot be fully "
            "inferred from static text."
        ),
        remediation=(
            "Add .env.example, .env.sample, or an example configuration containing "
            "placeholders rather than live credentials."
        ),
        test_references=(
            "tests/test_phase4_m4_docs_config.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-008)",
        ),
    ),
    "CS-CONFIG-002": _details(
        purpose=(
            "Find required-looking environment variables that are not explained to "
            "a new developer."
        ),
        applicability=(
            "Repositories with literal environment-variable access or shell/template "
            "references; dynamic names remain explicitly unverified."
        ),
        algorithm=(
            "Extract literal os.environ, os.getenv, shell export, and ${VAR} names, "
            "ignore common system variables, and compare the remainder with docs and "
            "safe configuration templates."
        ),
        evidence=(
            "Variable names and relative source/documentation/template locations; "
            "values are omitted and redacted."
        ),
        limitations=(
            "Static analysis cannot prove runtime necessity, secret validity, or the "
            "names created by dynamic string construction."
        ),
        remediation=(
            "Document each variable's purpose, required/optional status, safe "
            "placeholder, and secure value-provision method."
        ),
        test_references=(
            "tests/test_phase4_m4_docs_config.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-009)",
        ),
    ),
    "CS-PORT-001": _details(
        purpose=(
            "Detect host-specific absolute paths likely to prevent use on another "
            "machine."
        ),
        applicability=(
            "Generic; bounded text/configuration/script/Docker/CI files are inspected "
            "when readable."
        ),
        algorithm=(
            "Scan bounded text for home, Windows drive/UNC, and Unix absolute-path "
            "indicators while suppressing URLs, system paths, examples, regexes, and "
            "known container WORKDIR patterns."
        ),
        evidence=(
            "Relative path and line metadata plus a redacted indicator category such "
            "as windows-drive-path or host-home-path; raw host paths are omitted."
        ),
        limitations=(
            "Legitimate container or system paths can be flagged, while generated, "
            "encoded, or split paths can evade detection."
        ),
        remediation=(
            "Replace host paths with repository-relative paths, environment variables, "
            "or portable tool discovery."
        ),
        test_references=(
            "tests/test_phase4_m4_quality.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-010)",
        ),
    ),
    "CS-SEC-001": _details(
        purpose=(
            "Identify likely committed credentials, key markers, or sensitive "
            "assignments without exposing their values."
        ),
        applicability=(
            "Generic; bounded text and security-shaped filenames are inspected when "
            "readable, while binary content is skipped."
        ),
        algorithm=(
            "Scan for private-key markers and contextual credential assignments, "
            "suppress placeholders/examples, classify strong and weak indicators, and "
            "redact values before evidence is emitted."
        ),
        evidence=(
            "Indicator type, relative path/line, bounded digest, and raw_value=omitted; "
            "the report never includes the suspected secret."
        ),
        limitations=(
            "No pattern set proves absence or compromise; encoded, split, generated, "
            "encrypted, and provider-specific values may evade detection."
        ),
        remediation=(
            "Remove and rotate exposed credentials, retain placeholders or environment "
            "references, update ignore rules, and review repository history."
        ),
        test_references=(
            "tests/test_phase4_m4_quality.py",
            "tests/test_phase4_m4_integration.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-011)",
        ),
    ),
    "CS-BUILD-001": _details(
        purpose=(
            "Discover container build configuration and compare it with explicit "
            "container workflow claims."
        ),
        applicability=(
            "Generic; applicable when a Docker/compose configuration or a clear "
            "container claim is present, otherwise not applicable."
        ),
        algorithm=(
            "Detect Dockerfiles, compose files, .dockerignore, documented claims, "
            "and bounded Docker FROM/COPY/ADD metadata. The audit never builds an "
            "image."
        ),
        evidence=(
            "Relative configuration or documentation paths, selected Docker metadata, "
            "and explicit missing-configuration evidence for a container claim."
        ),
        limitations=(
            "Static discovery cannot prove base-image availability, dependency pulls, "
            "or build success; use authorized P1 verification for an actual build."
        ),
        remediation=(
            "Add or correct the documented container configuration and keep referenced "
            "resources inside the repository."
        ),
        test_references=(
            "tests/test_phase4_m4_quality.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-012)",
        ),
    ),
    "CS-PATH-001": _details(
        purpose=(
            "Detect required local references that escape the repository, are missing, "
            "or depend on external symlinks."
        ),
        applicability=(
            "Generic; checks supported resource references in bounded Docker, compose, "
            "packaging, configuration, script, and documentation evidence."
        ),
        algorithm=(
            "Normalize candidate paths lexically, classify absolute/system/placeholder, "
            "dynamic, parent-escape, missing, and present references, and record "
            "external symlinks without opening or traversing their targets."
        ),
        evidence=(
            "Relative reference path, classification, containing source path, and "
            "bounded inventory limitations; external targets are not read."
        ),
        limitations=(
            "Dynamic path construction, generated files, and platform case-collision "
            "behavior cannot be fully resolved statically."
        ),
        remediation=(
            "Keep required resources inside the repository, use contained relative "
            "paths, and remove or contain external symlinks."
        ),
        test_references=(
            "tests/test_phase4_m4_quality.py",
            "docs/08_REQUIREMENT_TRACEABILITY.md (AT-CS-013)",
        ),
    ),
}


def _build_explanation(entry: CatalogEntry) -> CheckExplanation:
    """Combine stable catalog identity with its reviewed explanation details."""

    details = _DETAILS[entry.check_id]
    return CheckExplanation(
        check_id=entry.check_id,
        name=entry.name,
        severity=entry.severity,
        category=entry.category,
        adapters=entry.adapters,
        purpose=details.purpose,
        applicability=details.applicability,
        algorithm=details.algorithm,
        evidence=details.evidence,
        limitations=details.limitations,
        remediation=details.remediation,
        test_references=details.test_references,
    )


def validate_explanations() -> None:
    """Ensure every registered check has complete explanation metadata."""

    catalog_ids = set(CATALOG_CHECK_IDS)
    detail_ids = set(_DETAILS)
    missing = sorted(catalog_ids - detail_ids)
    extra = sorted(detail_ids - catalog_ids)
    if missing or extra:
        problems: list[str] = []
        if missing:
            problems.append("missing: " + ", ".join(missing))
        if extra:
            problems.append("unregistered: " + ", ".join(extra))
        raise RuntimeError("invalid check explanations (" + "; ".join(problems) + ")")

    for check_id, details in _DETAILS.items():
        fields = (
            details.purpose,
            details.applicability,
            details.algorithm,
            details.evidence,
            details.limitations,
            details.remediation,
        )
        if any(not field.strip() for field in fields) or not details.test_references:
            raise RuntimeError(f"incomplete explanation metadata for {check_id}")


validate_explanations()


def explanation_for(check_id: str) -> CheckExplanation:
    """Return the exact registered explanation for ``check_id``."""

    entry = CATALOG_BY_ID.get(check_id)
    if entry is None:
        raise UnknownCheckError(check_id)
    return _build_explanation(entry)


def all_explanations() -> tuple[CheckExplanation, ...]:
    """Return explanations in the stable catalog order."""

    return tuple(_build_explanation(entry) for entry in CATALOG)


def render_explanation(explanation: CheckExplanation) -> str:
    """Render one explanation as deterministic, plain terminal text."""

    lines = [
        "ColdStart rule explanation",
        f"Check: {explanation.check_id} -- {explanation.name}",
        f"Default severity: {explanation.severity}",
        f"Category: {explanation.category}",
        f"Adapters: {', '.join(explanation.adapters)}",
        f"Applicability: {explanation.applicability}",
        f"Purpose: {explanation.purpose}",
        f"Algorithm: {explanation.algorithm}",
        f"Evidence: {explanation.evidence}",
        f"Limitations: {explanation.limitations}",
        f"Remediation: {explanation.remediation}",
        "Test references:",
    ]
    lines.extend(f"  - {reference}" for reference in explanation.test_references)
    return "\n".join(lines) + "\n"


__all__ = [
    "CheckExplanation",
    "UnknownCheckError",
    "all_explanations",
    "explanation_for",
    "render_explanation",
    "validate_explanations",
]
