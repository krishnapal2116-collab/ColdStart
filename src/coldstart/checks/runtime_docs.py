"""Bounded, read-only runtime and setup-documentation checks.

This module deliberately consumes the immutable discovery results supplied by
the caller.  It does not walk the repository, import project modules, execute
commands, or resolve files outside the inspected root.  Every candidate file
is already present in :class:`~coldstart.discovery.InventoryResult` and every
text read has a hard byte limit.
"""

from __future__ import annotations

import hashlib
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..discovery import DetectionResult, FileRecord, InventoryResult
from ..findings import Applicability, Evidence, Finding


RULE_VERSION = "3"
RUNTIME_READ_LIMIT = 64 * 1024
DOCS_READ_LIMIT = 64 * 1024
MAX_INSPECTED_FILES = 256

_VERSION_TOKEN = re.compile(
    r"^v?(?P<major>\d+)(?:\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?)?(?P<wildcard>\.\*)?$",
    re.IGNORECASE,
)
_SPECIFIER = re.compile(
    r"^(?P<operator>===|==|!=|~=|>=|<=|>|<)?\s*(?P<version>v?\d+(?:\.\d+(?:\.\d+)?)?(?:\.\*)?)$",
    re.IGNORECASE,
)

_README_SUFFIXES = {
    "",
    ".adoc",
    ".asciidoc",
    ".markdown",
    ".md",
    ".rst",
    ".txt",
}
_DOC_SUFFIXES = _README_SUFFIXES - {""}

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.+?)\s*#*\s*$")
_SETEXT = re.compile(r"^\s*(?:=+|-+)\s*$")

_PREREQUISITE_HEADING = re.compile(
    r"\b(?:prerequisites?|pre-requisites?|system\s+requirements?|runtime|"
    r"requirements?|environment|getting\s+started|dependencies)\b",
    re.IGNORECASE,
)
_INSTALL_HEADING = re.compile(
    r"\b(?:install(?:ation)?|setup|set[- ]?up|bootstrap|getting\s+started|"
    r"quick\s+start|dependencies)\b",
    re.IGNORECASE,
)
_CONFIG_HEADING = re.compile(
    r"\b(?:config(?:uration)?|configure|environment\s+variables?|"
    r"env(?:ironment)?|settings?|secrets?)\b",
    re.IGNORECASE,
)
_RUN_HEADING = re.compile(
    r"\b(?:run(?:ning)?|start(?:ing)?|serve|usage|launch|development|"
    r"quick\s+start)\b",
    re.IGNORECASE,
)

_RUNTIME_TEXT = re.compile(
    r"\b(?:python(?:\s*(?:version|3(?:\.\d+){0,2}))?|node(?:\.js)?|"
    r"ruby|java|go|rust)\b",
    re.IGNORECASE,
)
_RUNTIME_VERSION_TEXT = re.compile(
    r"\b(?:python|node(?:\.js)?|ruby|java|go|rust)\b\s*"
    r"(?:(?:version|requires?)\b|[<>=~!]*\s*v?\d+(?:\.\d+){0,2})",
    re.IGNORECASE,
)
_INSTALL_COMMAND = re.compile(
    r"(?:^|[`\s])(?:python(?:\d(?:\.\d+)*)?\s+-m\s+(?:pip\s+install|venv\b)|"
    r"python(?:\d(?:\.\d+)*)?\s+setup\.py\s+install|virtualenv\b|"
    r"pip(?:3)?\s+install|uv\s+(?:sync|pip\s+install)|poetry\s+install|"
    r"pdm\s+install|conda\s+install|npm\s+(?:install|ci)|"
    r"yarn(?:\s+install)?|pnpm\s+(?:install|i)|make\s+(?:install|setup)|"
    r"docker(?:\s+compose)?\s+(?:build|run))(?=\s|[`$]|$)",
    re.IGNORECASE,
)
_CONFIG_TEXT = re.compile(
    r"(?:\.env(?:\.(?:example|sample|template))?|environment\s+variables?|"
    r"(?:export|set)\s+[A-Z][A-Z0-9_]*\s*=|"
    r"no\s+configuration\s+(?:is\s+)?required|without\s+configuration|"
    r"configure(?:d|s|ation)?)",
    re.IGNORECASE,
)
_RUN_COMMAND = re.compile(
    r"(?:^|[`\s])(?:python(?:\d(?:\.\d+)*)?\s+(?:-m\s+\S+|\S+\.py(?:\s|$)|"
    r"-[A-Za-z])|uv\s+run\s+\S+|poetry\s+run\s+\S+|pdm\s+run\s+\S+|"
    r"npm\s+(?:run\s+\S+|start|dev)\b|node\s+\S+\.(?:js|mjs|cjs)\b|"
    r"yarn\s+(?:start|dev|run)\b|pnpm\s+(?:run|start|dev)\b|"
    r"make\s+(?:run|start|serve|dev)\b|docker(?:\s+compose)?\s+up\b|"
    r"(?:flask|uvicorn|gunicorn|streamlit)\s+(?:run|[\w.-]+)|"
    r"(?:cargo\s+run|go\s+run\s+\S+|ruby\s+\S+\.rb|java\s+-jar\s+\S+))(?=\s|[`$]|$)",
    re.IGNORECASE,
)

Version = tuple[int, int, int]


@dataclass(frozen=True)
class _VersionRange:
    """A small interval model sufficient for Python release declarations."""

    lower: Version | None
    lower_inclusive: bool
    upper: Version | None
    upper_inclusive: bool
    classification: str
    label: str


@dataclass(frozen=True)
class _RuntimeDeclaration:
    path: str
    source: str
    version_range: _VersionRange
    line: int | None
    digest: str | None


@dataclass(frozen=True)
class _ReadText:
    path: str
    text: str | None
    digest: str | None
    error: str | None = None


@dataclass(frozen=True)
class _DocSignal:
    category: str
    path: str
    line: int
    digest: str | None


def _normal_relative_path(value: object) -> str | None:
    """Normalize an inventory path and reject absolute or escaping values."""

    if not isinstance(value, str):
        return None
    raw = value.replace("\\", "/")
    if not raw or raw.startswith("/"):
        return None
    if len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha():
        return None
    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else "."


def _safe_record_path(root: Path, record: FileRecord) -> tuple[Path | None, str | None]:
    """Return a contained path without following an inventory symlink."""

    relative = _normal_relative_path(record.relative_path)
    if relative is None or relative == ".":
        return None, "inventory contained an invalid relative path"
    if record.kind != "file":
        return None, "inventory record is not a regular file"
    if not record.readable:
        return None, "inventory record is unreadable"
    if record.size is not None and (
        isinstance(record.size, bool) or not isinstance(record.size, int) or record.size < 0
    ):
        return None, "inventory record has an invalid size"

    try:
        resolved_root = root.resolve(strict=False)
    except (OSError, RuntimeError):
        return None, "repository root could not be resolved"
    candidate = resolved_root.joinpath(*relative.split("/"))
    cursor = resolved_root
    for component in relative.split("/"):
        cursor = cursor / component
        try:
            if cursor.is_symlink():
                return None, "symlinked inventory entry was not read"
        except OSError:
            return None, "inventory entry could not be classified"
    try:
        resolved_candidate = candidate.resolve(strict=False)
        common = os.path.commonpath(
            (
                os.path.normcase(os.fspath(resolved_root)),
                os.path.normcase(os.fspath(resolved_candidate)),
            )
        )
    except (OSError, RuntimeError, ValueError):
        return None, "inventory entry escaped the repository boundary"
    if common != os.path.normcase(os.fspath(resolved_root)):
        return None, "inventory entry escaped the repository boundary"
    return candidate, None


def _read_bounded_text(root: Path, record: FileRecord, limit: int) -> _ReadText:
    """Read one discovered file as UTF-8, never exceeding ``limit`` bytes."""

    relative = _normal_relative_path(record.relative_path)
    # Error evidence still has to satisfy the report's relative-path contract
    # when a caller supplies a malformed inventory record.
    safe_path = relative if relative is not None else "."
    if record.kind != "file":
        return _ReadText(safe_path, None, None, "inventory record is not a regular file")
    if not record.readable:
        return _ReadText(safe_path, None, None, "inventory record is unreadable")
    if record.size is not None:
        if isinstance(record.size, bool) or not isinstance(record.size, int) or record.size < 0:
            return _ReadText(safe_path, None, None, "inventory record has an invalid size")
        if record.size > limit:
            return _ReadText(safe_path, None, None, "file exceeds the bounded text limit")
    candidate, error = _safe_record_path(root, record)
    if candidate is None:
        return _ReadText(safe_path, None, None, error or "file path is not contained")
    try:
        with candidate.open("rb") as handle:
            data = handle.read(limit + 1)
    except (OSError, PermissionError):
        return _ReadText(safe_path, None, None, "file could not be read")
    if len(data) > limit:
        return _ReadText(safe_path, None, None, "file exceeds the bounded text limit")
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _ReadText(safe_path, None, digest, "file is not valid UTF-8 text")
    return _ReadText(safe_path, text, digest)


def _parse_version_token(value: str, *, allow_major_only: bool = False) -> tuple[Version, int] | None:
    match = _VERSION_TOKEN.fullmatch(value.strip())
    if match is None:
        return None
    if match.group("wildcard") and match.group("patch") is not None:
        return None
    minor = match.group("minor")
    if minor is None and not allow_major_only:
        return None
    patch = match.group("patch")
    precision = 3 if patch is not None else 2 if minor is not None else 1
    return (
        (
            int(match.group("major")),
            int(minor or 0),
            int(patch or 0),
        ),
        precision,
    )


def _increment_prefix(version: Version, precision: int) -> Version:
    if precision == 2:
        return version[0], version[1] + 1, 0
    return version[0] + 1, 0, 0


def _exact_range(version: Version, label: str) -> _VersionRange:
    return _VersionRange(version, True, version, True, "exact", label)


def _prefix_range(version: Version, precision: int, label: str) -> _VersionRange:
    return _VersionRange(
        version,
        True,
        _increment_prefix(version, precision),
        False,
        "bounded",
        label,
    )


def _parse_python_pin(text: str) -> tuple[Version, int] | None:
    """Parse a single pyenv-style version declaration."""

    nonempty = [
        (line_number, line.strip())
        for line_number, line in enumerate(text.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(nonempty) != 1:
        return None
    _line_number, value = nonempty[0]
    return _parse_version_token(value)


def _parse_specifier(text: str) -> _VersionRange | None:
    """Parse the supported, deterministic subset of PEP 440 specifiers."""

    pieces = [piece.strip() for piece in text.split(",")]
    if not pieces or any(not piece for piece in pieces):
        return None

    lower: Version | None = None
    lower_inclusive = True
    upper: Version | None = None
    upper_inclusive = True
    exact: Version | None = None
    exact_label: str | None = None

    for piece in pieces:
        match = _SPECIFIER.fullmatch(piece)
        if match is None:
            return None
        operator = match.group("operator") or "=="
        token = match.group("version")
        wildcard = token.endswith(".*")
        if wildcard:
            token = token[:-2]
        parsed = _parse_version_token(token, allow_major_only=True)
        if parsed is None:
            return None
        version, precision = parsed
        if wildcard and precision not in {1, 2}:
            return None

        if operator in {"==", "==="}:
            if operator == "===" and precision != 3:
                return None
            if precision == 3 and not wildcard:
                candidate = _exact_range(version, token)
                exact = version
                exact_label = token
            else:
                candidate = _prefix_range(version, precision, token)
        elif operator == "~=":
            if precision < 2:
                return None
            compatible_upper = (
                (version[0] + 1, 0, 0)
                if precision == 2
                else (version[0], version[1] + 1, 0)
            )
            candidate = _VersionRange(
                version,
                True,
                compatible_upper,
                False,
                "bounded",
                f"~={token}",
            )
        elif operator == ">=":
            candidate = _VersionRange(version, True, None, True, "broad", f">={token}")
        elif operator == ">":
            candidate = _VersionRange(version, False, None, True, "broad", f">{token}")
        elif operator == "<=":
            candidate = _VersionRange(None, True, version, True, "broad", f"<={token}")
        elif operator == "<":
            candidate = _VersionRange(None, True, version, False, "broad", f"<{token}")
        else:
            # Exclusions and union syntax need a complete version-specifier
            # implementation to evaluate safely.  Treat them as unverified.
            return None

        lower, lower_inclusive, upper, upper_inclusive = _intersect_bounds(
            lower,
            lower_inclusive,
            upper,
            upper_inclusive,
            candidate.lower,
            candidate.lower_inclusive,
            candidate.upper,
            candidate.upper_inclusive,
        )
        if _empty_bounds(lower, lower_inclusive, upper, upper_inclusive):
            return None

    if exact is not None and lower == exact and upper == exact and lower_inclusive and upper_inclusive:
        return _VersionRange(lower, True, upper, True, "exact", exact_label or text.strip())
    if lower is not None and upper is not None:
        classification = "bounded"
    else:
        classification = "broad"
    return _VersionRange(
        lower,
        lower_inclusive,
        upper,
        upper_inclusive,
        classification,
        text.strip(),
    )


def _intersect_bounds(
    first_lower: Version | None,
    first_lower_inclusive: bool,
    first_upper: Version | None,
    first_upper_inclusive: bool,
    second_lower: Version | None,
    second_lower_inclusive: bool,
    second_upper: Version | None,
    second_upper_inclusive: bool,
) -> tuple[Version | None, bool, Version | None, bool]:
    if first_lower is None:
        lower, lower_inclusive = second_lower, second_lower_inclusive
    elif second_lower is None or first_lower > second_lower:
        lower, lower_inclusive = first_lower, first_lower_inclusive
    elif second_lower > first_lower:
        lower, lower_inclusive = second_lower, second_lower_inclusive
    else:
        lower, lower_inclusive = first_lower, first_lower_inclusive and second_lower_inclusive

    if first_upper is None:
        upper, upper_inclusive = second_upper, second_upper_inclusive
    elif second_upper is None or first_upper < second_upper:
        upper, upper_inclusive = first_upper, first_upper_inclusive
    elif second_upper < first_upper:
        upper, upper_inclusive = second_upper, second_upper_inclusive
    else:
        upper, upper_inclusive = first_upper, first_upper_inclusive and second_upper_inclusive
    return lower, lower_inclusive, upper, upper_inclusive


def _empty_bounds(
    lower: Version | None,
    lower_inclusive: bool,
    upper: Version | None,
    upper_inclusive: bool,
) -> bool:
    if lower is None or upper is None:
        return False
    if lower < upper:
        return False
    return lower > upper or not (lower_inclusive and upper_inclusive)


def _ranges_overlap(first: _VersionRange, second: _VersionRange) -> bool:
    lower, lower_inclusive, upper, upper_inclusive = _intersect_bounds(
        first.lower,
        first.lower_inclusive,
        first.upper,
        first.upper_inclusive,
        second.lower,
        second.lower_inclusive,
        second.upper,
        second.upper_inclusive,
    )
    return not _empty_bounds(lower, lower_inclusive, upper, upper_inclusive)


def _python_candidate(detection: DetectionResult) -> bool:
    try:
        if detection.primary in {"python", "mixed"}:
            return True
        for candidate in detection.candidates:
            if candidate.id == "python" or "python" in candidate.members:
                return True
    except (AttributeError, TypeError):
        return False
    return False


def _record_sort_key(record: FileRecord) -> tuple[str, str]:
    path = str(record.relative_path)
    return path.casefold(), path


def _runtime_records(inventory: InventoryResult) -> tuple[FileRecord, ...]:
    records = [
        record
        for record in inventory.records
        if record.kind == "file"
        and Path(str(record.relative_path)).name.casefold() in {".python-version", "pyproject.toml"}
    ]
    return tuple(sorted(records, key=_record_sort_key))


def _runtime_error_evidence(errors: Iterable[tuple[str | None, str]]) -> tuple[Evidence, ...]:
    unique = sorted(
        set(errors),
        key=lambda item: (str(item[0] or "").casefold(), str(item[0] or ""), item[1]),
    )
    if not unique:
        unique = [(None, "bounded runtime evidence was incomplete")]
    return tuple(
        Evidence(
            kind="error",
            path=path,
            detail=f"Python runtime evidence was not verified: {detail}.",
        )
        for path, detail in unique[:16]
    )


def _runtime_declaration_evidence(declaration: _RuntimeDeclaration) -> Evidence:
    kind = "file" if declaration.source == ".python-version" else "metadata"
    return Evidence(
        kind=kind,
        path=declaration.path,
        line_start=declaration.line,
        line_end=declaration.line,
        detail=(
            f"Bounded {declaration.source} evidence declares Python {declaration.version_range.label} "
            f"({declaration.version_range.classification})."
        ),
        digest=declaration.digest,
    )


def _runtime_not_applicable() -> Finding:
    reason = "No Python project candidate was detected; the Python runtime check does not apply."
    return Finding(
        check_id="CS-RUNTIME-001",
        severity="info",
        status="not_applicable",
        title="Runtime version declaration",
        message=reason,
        evidence=(
            Evidence(
                kind="absence",
                path=None,
                detail="Bounded project detection contained no Python candidate for this Python-only check.",
            ),
        ),
        remediation="Use the runtime adapter for the detected ecosystem when one is available.",
        category="runtime",
        applicability=Applicability(applicable=False, reason=reason, adapter="python"),
        rule_version=RULE_VERSION,
        evidence_strength="absence",
    )


def _runtime_skipped() -> Finding:
    reason = "The configured policy excludes this runtime check; no rule logic was run."
    return Finding(
        check_id="CS-RUNTIME-001",
        severity="error",
        status="skipped",
        title="Runtime version declaration",
        message=reason,
        evidence=(
            Evidence(
                kind="policy",
                path=None,
                detail="The check ID is present in excluded_checks; evaluation was intentionally skipped.",
            ),
        ),
        remediation="Remove this check from excluded_checks when runtime coverage is required.",
        category="runtime",
        applicability=Applicability(applicable=False, reason=reason, adapter="policy"),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _evaluate_runtime(root: Path, inventory: InventoryResult, detection: DetectionResult) -> Finding:
    applicability = Applicability(
        applicable=True,
        reason="A Python project candidate was detected from bounded inventory signals.",
        adapter="python",
    )
    if inventory.incomplete:
        evidence = _runtime_error_evidence(
            [(None, "inventory coverage is partial or contains unreadable entries")]
        )
        return Finding(
            check_id="CS-RUNTIME-001",
            severity="warning",
            status="not_verified",
            title="Runtime version declaration",
            message="Python runtime declarations could not be evaluated completely within the bounded inventory.",
            evidence=evidence,
            remediation="Rerun with complete permitted inventory coverage and resolve unreadable entries.",
            category="runtime",
            applicability=applicability,
            rule_version=RULE_VERSION,
            evidence_strength="unverified",
        )
    declarations: list[_RuntimeDeclaration] = []
    errors: list[tuple[str | None, str]] = []
    if detection.incomplete:
        metadata_errors = getattr(detection, "metadata_errors", ())
        normalized_metadata_errors = [
            _normal_relative_path(item) if _normal_relative_path(item) not in {None, "."} else None
            for item in metadata_errors
        ]
        if normalized_metadata_errors:
            errors.extend(
                (path, "project detection metadata or inventory coverage is incomplete")
                for path in normalized_metadata_errors
            )
        else:
            errors.append((None, "project detection metadata or inventory coverage is incomplete"))
    for record in _runtime_records(inventory):
        path = _normal_relative_path(record.relative_path) or "."
        basename = Path(path).name.casefold()
        result = _read_bounded_text(root, record, RUNTIME_READ_LIMIT)
        if result.error is not None:
            errors.append((path, result.error))
            continue
        text = result.text or ""
        if basename == ".python-version":
            parsed = _parse_python_pin(text)
            if parsed is None:
                errors.append((path, ".python-version must contain one numeric Python version"))
                continue
            version, precision = parsed
            version_range = (
                _exact_range(version, _format_version(version, precision))
                if precision == 3
                else _prefix_range(version, precision, _format_version(version, precision))
            )
            line = next(
                (
                    line_number
                    for line_number, line_text in enumerate(text.splitlines(), start=1)
                    if line_text.strip() and not line_text.lstrip().startswith("#")
                ),
                1,
            )
            declarations.append(
                _RuntimeDeclaration(path, ".python-version", version_range, line, result.digest)
            )
            continue

        try:
            document = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, TypeError, ValueError):
            errors.append((path, "pyproject.toml is malformed"))
            continue
        project = document.get("project") if isinstance(document, dict) else None
        if project is None:
            continue
        if not isinstance(project, dict):
            errors.append((path, "the project table is malformed"))
            continue
        if "requires-python" not in project:
            continue
        requires_python = project.get("requires-python")
        if not isinstance(requires_python, str) or not requires_python.strip():
            errors.append((path, "project.requires-python must be a non-empty string"))
            continue
        version_range = _parse_specifier(requires_python)
        if version_range is None:
            errors.append((path, "project.requires-python contains an unsupported or malformed specifier"))
            continue
        line = _requires_python_line(text)
        declarations.append(
            _RuntimeDeclaration(path, "project.requires-python", version_range, line, result.digest)
        )

    if errors:
        evidence = _runtime_error_evidence(errors)
        return Finding(
            check_id="CS-RUNTIME-001",
            severity="warning",
            status="not_verified",
            title="Runtime version declaration",
            message="One or more discovered Python runtime declarations were malformed, unreadable, or only partially evidenced.",
            evidence=evidence,
            remediation="Correct malformed runtime metadata and rerun with readable bounded declaration files.",
            affected_path=evidence[0].path,
            category="runtime",
            applicability=applicability,
            rule_version=RULE_VERSION,
            evidence_strength="unverified",
        )

    if not declarations:
        evidence = (
            Evidence(
                kind="absence",
                path=None,
                detail="No bounded .python-version or project.requires-python declaration was discovered.",
            ),
        )
        return Finding(
            check_id="CS-RUNTIME-001",
            severity="error",
            status="failed",
            title="Runtime version declaration",
            message="The Python project has no machine-readable runtime version declaration.",
            evidence=evidence,
            remediation="Add a precise .python-version pin and/or a consistent project.requires-python constraint.",
            category="runtime",
            applicability=applicability,
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )

    conflicts: list[tuple[_RuntimeDeclaration, _RuntimeDeclaration]] = []
    for index, first in enumerate(declarations):
        for second in declarations[index + 1 :]:
            if not _ranges_overlap(first.version_range, second.version_range):
                conflicts.append((first, second))
    if conflicts:
        evidence_items: list[Evidence] = []
        for first, second in conflicts[:8]:
            evidence_items.extend(
                (
                    _runtime_declaration_evidence(first),
                    _runtime_declaration_evidence(second),
                    Evidence(
                        kind="error",
                        path=second.path,
                        detail=(
                            f"This declaration conflicts with {first.path}; the normalized Python version ranges do not overlap."
                        ),
                    ),
                )
            )
        return Finding(
            check_id="CS-RUNTIME-001",
            severity="error",
            status="failed",
            title="Runtime version declaration",
            message="The discovered Python runtime declarations conflict and cannot identify one supported runtime range.",
            evidence=tuple(evidence_items),
            remediation="Align .python-version, project.requires-python, and any per-project declarations to one supported runtime.",
            affected_path=conflicts[0][0].path,
            category="runtime",
            applicability=applicability,
            rule_version=RULE_VERSION,
            evidence_strength="derived",
        )

    evidence = tuple(_runtime_declaration_evidence(item) for item in declarations)
    strongest = "exact" if any(item.version_range.classification == "exact" for item in declarations) else "bounded"
    severity = "info" if strongest == "exact" else "warning"
    detail = (
        "A consistent exact Python runtime declaration was found."
        if strongest == "exact"
        else "A consistent bounded Python runtime declaration was found; the accepted range is less reproducible than an exact pin."
    )
    return Finding(
        check_id="CS-RUNTIME-001",
        severity=severity,
        status="passed",
        title="Runtime version declaration",
        message=detail,
        evidence=evidence,
        remediation=(),
        affected_path=declarations[0].path,
        category="runtime",
        applicability=applicability,
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _format_version(version: Version, precision: int) -> str:
    if precision == 2:
        return f"{version[0]}.{version[1]}"
    return f"{version[0]}.{version[1]}.{version[2]}"


def _requires_python_line(text: str) -> int | None:
    """Find a stable line number for the requires-python key when present."""

    pattern = re.compile(r"^\s*requires-python\s*=", re.IGNORECASE)
    for line_number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return line_number
    return None


def _is_documentation_path(path: str) -> bool:
    parts = path.casefold().split("/")
    basename = parts[-1]
    suffix = Path(basename).suffix.casefold()
    if basename.startswith("readme"):
        return True
    return any(directory in parts for directory in {"docs", "documentation"}) and suffix in _DOC_SUFFIXES


def _documentation_records(inventory: InventoryResult) -> tuple[FileRecord, ...]:
    records = [
        record
        for record in inventory.records
        if record.kind == "file" and _is_documentation_path(str(record.relative_path))
    ]
    return tuple(sorted(records, key=_record_sort_key))


def _heading_text(lines: list[str], index: int) -> str | None:
    match = _HEADING.match(lines[index])
    if match is not None:
        return match.group("text").strip()
    if index + 1 < len(lines) and lines[index].strip() and _SETEXT.match(lines[index + 1]):
        return lines[index].strip()
    return None


def _documentation_signals(path: str, text: str, digest: str | None) -> tuple[_DocSignal, ...]:
    lines = text.splitlines()
    signals: list[_DocSignal] = []
    for index, line in enumerate(lines):
        line_number = index + 1
        heading = _heading_text(lines, index)
        if heading is not None:
            heading_patterns = (
                ("prerequisites", _PREREQUISITE_HEADING),
                ("installation", _INSTALL_HEADING),
                ("configuration", _CONFIG_HEADING),
                ("run", _RUN_HEADING),
            )
            for category, pattern in heading_patterns:
                if pattern.search(heading):
                    signals.append(_DocSignal(category, path, line_number, digest))

        if _RUNTIME_TEXT.search(line) and (_RUNTIME_VERSION_TEXT.search(line) or heading is not None):
            signals.append(_DocSignal("prerequisites", path, line_number, digest))
        if _INSTALL_COMMAND.search(line):
            signals.append(_DocSignal("installation", path, line_number, digest))
        if _CONFIG_TEXT.search(line):
            signals.append(_DocSignal("configuration", path, line_number, digest))
        if _RUN_COMMAND.search(line):
            signals.append(_DocSignal("run", path, line_number, digest))
    return tuple(signals)


def _docs_skipped() -> Finding:
    reason = "The configured policy excludes setup documentation; no rule logic was run."
    return Finding(
        check_id="CS-DOCS-001",
        severity="warning",
        status="skipped",
        title="Setup documentation presence",
        message=reason,
        evidence=(
            Evidence(
                kind="policy",
                path=None,
                detail="The check ID is present in excluded_checks; evaluation was intentionally skipped.",
            ),
        ),
        remediation="Remove this check from excluded_checks when setup documentation coverage is required.",
        category="documentation",
        applicability=Applicability(applicable=False, reason=reason, adapter="policy"),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _docs_not_applicable() -> Finding:
    reason = (
        "No supported project or documentation signal was detected; setup documentation "
        "cannot be required for an otherwise unknown repository."
    )
    return Finding(
        check_id="CS-DOCS-001",
        severity="info",
        status="not_applicable",
        title="Setup documentation presence",
        message=reason,
        evidence=(
            Evidence(
                kind="absence",
                path=None,
                detail="The complete bounded inventory contained no README or supported project signal for this generic check.",
            ),
        ),
        remediation="Add a project signal and a setup README when the repository is intended to be runnable.",
        category="documentation",
        applicability=Applicability(applicable=False, reason=reason, adapter="generic"),
        rule_version=RULE_VERSION,
        evidence_strength="absence",
    )


def _evaluate_documentation(
    root: Path,
    inventory: InventoryResult,
    detection: DetectionResult,
) -> Finding:
    applicability = Applicability(
        applicable=True,
        reason="Bounded README and docs text is meaningful for every detected repository type.",
        adapter="generic",
    )
    records = _documentation_records(inventory)
    errors: list[tuple[str | None, str]] = []
    if inventory.incomplete:
        errors.append((None, "inventory coverage is partial or contains unreadable entries"))
    if detection.incomplete:
        errors.append((None, "project detection metadata or inventory coverage is incomplete"))
    if len(records) > MAX_INSPECTED_FILES:
        errors.append((None, "the bounded documentation inspection file limit was reached"))
        records = records[:MAX_INSPECTED_FILES]

    all_signals: list[_DocSignal] = []
    for record in records:
        result = _read_bounded_text(root, record, DOCS_READ_LIMIT)
        if result.error is not None:
            errors.append((result.path, result.error))
            continue
        all_signals.extend(_documentation_signals(result.path, result.text or "", result.digest))

    if errors:
        evidence = _documentation_error_evidence(errors)
        return Finding(
            check_id="CS-DOCS-001",
            severity="warning",
            status="not_verified",
            title="Setup documentation presence",
            message="Setup documentation could not be evaluated completely within the bounded readable evidence.",
            evidence=evidence,
            remediation="Resolve unreadable or oversized README/docs files and rerun the bounded documentation check.",
            affected_path=evidence[0].path,
            category="documentation",
            applicability=applicability,
            rule_version=RULE_VERSION,
            evidence_strength="unverified",
        )

    if not records:
        if detection.primary == "unknown" and not errors:
            return _docs_not_applicable()
        evidence = (
            Evidence(
                kind="absence",
                path=None,
                detail="No bounded README or supported docs text file was discovered.",
            ),
        )
        return Finding(
            check_id="CS-DOCS-001",
            severity="warning",
            status="failed",
            title="Setup documentation presence",
            message="No setup documentation entry point was discovered for the repository.",
            evidence=evidence,
            remediation="Add a README or docs setup path covering prerequisites, installation, configuration, and running the project.",
            category="documentation",
            applicability=applicability,
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )

    selected: dict[str, _DocSignal] = {}
    for signal in sorted(all_signals, key=lambda item: (item.path.casefold(), item.path, item.line, item.category)):
        selected.setdefault(signal.category, signal)
    categories = ("prerequisites", "installation", "configuration", "run")
    missing = tuple(category for category in categories if category not in selected)
    if missing:
        evidence_items: list[Evidence] = []
        for category in categories:
            signal = selected.get(category)
            if signal is not None:
                evidence_items.append(_documentation_signal_evidence(signal))
            else:
                evidence_items.append(
                    Evidence(
                        kind="absence",
                        path=None,
                        detail=f"No deterministic {category} guidance heading or command pattern was found in bounded documentation.",
                    )
                )
        return Finding(
            check_id="CS-DOCS-001",
            severity="warning",
            status="failed",
            title="Setup documentation presence",
            message="Setup documentation exists but is incomplete; missing guidance: " + ", ".join(missing) + ".",
            evidence=tuple(evidence_items),
            remediation="Add a clean-checkout sequence with prerequisites/runtime, installation, configuration, and run/start guidance.",
            affected_path=_normal_relative_path(records[0].relative_path),
            category="documentation",
            applicability=applicability,
            rule_version=RULE_VERSION,
            evidence_strength="derived",
        )

    evidence = tuple(_documentation_signal_evidence(selected[category]) for category in categories)
    return Finding(
        check_id="CS-DOCS-001",
        severity="info",
        status="passed",
        title="Setup documentation presence",
        message="Bounded documentation contains deterministic prerequisite, installation, configuration, and run guidance.",
        evidence=evidence,
        remediation=(),
        affected_path=_normal_relative_path(records[0].relative_path),
        category="documentation",
        applicability=applicability,
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _documentation_signal_evidence(signal: _DocSignal) -> Evidence:
    labels = {
        "prerequisites": "prerequisite/runtime",
        "installation": "installation/setup",
        "configuration": "configuration",
        "run": "run/start",
    }
    return Evidence(
        kind="file",
        path=signal.path,
        line_start=signal.line,
        line_end=signal.line,
        detail=f"Bounded documentation contains {labels[signal.category]} guidance using deterministic patterns.",
        digest=signal.digest,
    )


def _documentation_error_evidence(errors: Iterable[tuple[str | None, str]]) -> tuple[Evidence, ...]:
    unique = sorted(
        set(errors),
        key=lambda item: (str(item[0] or "").casefold(), str(item[0] or ""), item[1]),
    )
    if not unique:
        unique = [(None, "bounded documentation evidence was incomplete")]
    return tuple(
        Evidence(
            kind="error",
            path=path,
            detail=f"Setup documentation was not verified: {detail}.",
        )
        for path, detail in unique[:16]
    )


def evaluate_runtime_and_setup_checks(
    root: Path | str,
    inventory: InventoryResult,
    detection: DetectionResult,
    *,
    excluded_checks: Iterable[str] = (),
) -> tuple[Finding, ...]:
    """Evaluate CS-RUNTIME-001 and CS-DOCS-001 from bounded discovery data.

    The result is stable check-ID order.  Excluded checks remain visible as
    policy ``skipped`` findings; runtime is explicitly ``not_applicable`` for
    non-Python and unknown detections while documentation remains generic.
    """

    if isinstance(excluded_checks, str):
        excluded = {excluded_checks}
    else:
        excluded = {str(check_id) for check_id in excluded_checks}
    root_path = Path(root)
    runtime = (
        _runtime_skipped()
        if "CS-RUNTIME-001" in excluded
        else _runtime_not_applicable()
        if not _python_candidate(detection)
        else _evaluate_runtime(root_path, inventory, detection)
    )
    documentation = (
        _docs_skipped()
        if "CS-DOCS-001" in excluded
        else _evaluate_documentation(root_path, inventory, detection)
    )
    return (runtime, documentation)


__all__ = [
    "DOCS_READ_LIMIT",
    "MAX_INSPECTED_FILES",
    "RULE_VERSION",
    "RUNTIME_READ_LIMIT",
    "evaluate_runtime_and_setup_checks",
]
