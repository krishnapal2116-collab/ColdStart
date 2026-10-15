"""Repository and output-boundary validation for the static audit.

The repository under inspection is untrusted input.  Boundary validation keeps
the root canonical and supplies the bounded, read-only rules used by M2
discovery.  It never creates a staging copy and it never follows a repository
symlink while inventory is collected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, TypeAlias


DEFAULT_MAX_FILES = 10_000
DEFAULT_MAX_BYTES = 50_000_000
DEFAULT_MAX_DEPTH = 32
DEFAULT_MAX_SECONDS = 30

# These upper bounds keep a malformed local policy from turning a static audit
# into an effectively unbounded walk.  They are deliberately generous enough
# for ordinary repositories while remaining representable by every supported
# platform.
MAX_ALLOWED_FILES = 1_000_000
MAX_ALLOWED_BYTES = 2_000_000_000
MAX_ALLOWED_DEPTH = 512
MAX_ALLOWED_SECONDS = 3_600

BUILTIN_EXCLUSIONS = (
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
)


class BoundaryValidationError(ValueError):
    """An input repository or output path does not satisfy the CLI contract."""


class OutputValidationError(ValueError):
    """The requested report destination is not a writable file selection."""


PathLike: TypeAlias = str | os.PathLike[str]


def safe_text(value: object, *, limit: int = 160) -> str:
    """Return bounded text with terminal control characters represented safely."""

    text = str(value)
    escaped: list[str] = []
    for character in text:
        codepoint = ord(character)
        if character.isprintable() and character not in {"\x1b"}:
            escaped.append(character)
        else:
            escaped.append(f"\\u{codepoint:04x}")
    result = "".join(escaped)
    if len(result) > limit:
        return result[: max(0, limit - 1)] + "…"
    return result


def safe_path_label(value: object) -> str:
    """Describe a user path without echoing an absolute host path."""

    try:
        raw = os.fsdecode(os.fspath(value))
    except (TypeError, ValueError):
        return "<path>"
    candidate = Path(raw)
    # Absolute paths can contain a home-directory username.  Error messages
    # need a useful category, not a second copy of the user's host path.
    if candidate.is_absolute() or raw.startswith("~"):
        return "<provided-path>"
    name = candidate.name
    if not name or name in {".", ".."}:
        name = "repository"
    return safe_text(name)


@dataclass(frozen=True)
class BoundaryLimits:
    """Bounded limits recorded in every audit invocation."""

    max_files: int = DEFAULT_MAX_FILES
    max_bytes: int = DEFAULT_MAX_BYTES
    max_seconds: int = DEFAULT_MAX_SECONDS
    max_depth: int = DEFAULT_MAX_DEPTH

    def __post_init__(self) -> None:
        maximums = {
            "max_files": MAX_ALLOWED_FILES,
            "max_bytes": MAX_ALLOWED_BYTES,
            "max_depth": MAX_ALLOWED_DEPTH,
            "max_seconds": MAX_ALLOWED_SECONDS,
        }
        for name, maximum in maximums.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise BoundaryValidationError(f"{name} must be a positive integer")
            if value > maximum:
                raise BoundaryValidationError(
                    f"{name} exceeds the safe maximum of {maximum}"
                )

    def as_dict(self) -> dict[str, int]:
        return {
            "max_files": self.max_files,
            "max_bytes": self.max_bytes,
            "max_depth": self.max_depth,
            "max_seconds": self.max_seconds,
        }


def default_limits() -> BoundaryLimits:
    """Return the safe bounded defaults used by the M1 command."""

    return BoundaryLimits()


def validate_limits(values: BoundaryLimits | Mapping[str, object] | None) -> BoundaryLimits:
    """Validate and normalize configured bounds without accepting loose numbers."""

    if values is None:
        return default_limits()
    if isinstance(values, BoundaryLimits):
        return values
    if not isinstance(values, Mapping):
        raise BoundaryValidationError("limits must be a mapping")
    allowed_keys = {"max_files", "max_bytes", "max_total_bytes", "max_depth", "max_seconds"}
    unknown_keys = sorted(
        (str(key) for key in values if key not in allowed_keys),
    )
    if unknown_keys:
        raise BoundaryValidationError(f"unsupported limit: {unknown_keys[0]}")
    # ``max_total_bytes`` is accepted as an API synonym, while the report and
    # CLI use the shorter ``max_bytes`` spelling from the public contract.
    max_bytes = values.get("max_bytes", values.get("max_total_bytes", DEFAULT_MAX_BYTES))
    try:
        return BoundaryLimits(
            max_files=values.get("max_files", DEFAULT_MAX_FILES),  # type: ignore[arg-type]
            max_bytes=max_bytes,  # type: ignore[arg-type]
            max_seconds=values.get("max_seconds", DEFAULT_MAX_SECONDS),  # type: ignore[arg-type]
            max_depth=values.get("max_depth", DEFAULT_MAX_DEPTH),  # type: ignore[arg-type]
        )
    except TypeError as error:
        raise BoundaryValidationError("limits must contain integer values") from error


def normalize_exclusion(value: object) -> str:
    """Normalize one user exclusion and reject paths outside the boundary."""

    if not isinstance(value, str) or not value.strip():
        raise BoundaryValidationError("exclusions must contain non-empty strings")
    normalized = value.replace("\\", "/").strip()
    if ":" in normalized:
        raise BoundaryValidationError("exclusions cannot contain a drive or URL scheme")
    if normalized.startswith("/") or (
        len(normalized) >= 2
        and normalized[1] == ":"
        and normalized[0].isalpha()
    ):
        raise BoundaryValidationError("exclusions must be repository-relative")
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise BoundaryValidationError(
                "exclusions cannot escape the repository boundary"
            )
        parts.append(part)
    if not parts:
        raise BoundaryValidationError("exclusions must identify a relative path")
    return "/".join(parts)


def normalize_exclusions(values: object | None) -> tuple[str, ...]:
    """Return stable user exclusions; built-in exclusions are added separately."""

    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, (list, tuple, set, frozenset)):
        raise BoundaryValidationError("exclusions must be a list of relative paths")
    normalized = {normalize_exclusion(value) for value in values}
    return tuple(sorted(normalized))


def effective_exclusions(values: object | None = None) -> tuple[str, ...]:
    """Combine immutable built-ins with validated user exclusions."""

    return tuple(sorted(set(BUILTIN_EXCLUSIONS) | set(normalize_exclusions(values))))


def is_excluded(relative_path: str, exclusions: tuple[str, ...]) -> bool:
    """Return whether a normalized relative path is under an exclusion."""

    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized:
        return False
    parts = normalized.split("/")
    for exclusion in exclusions:
        exclusion_parts = exclusion.split("/")
        # Built-ins name generated directories wherever they occur; explicit
        # paths are exact prefixes and therefore remain useful for nested roots.
        if exclusion in BUILTIN_EXCLUSIONS:
            if exclusion in parts:
                return True
        elif parts[: len(exclusion_parts)] == exclusion_parts:
            return True
    return False


@dataclass(frozen=True)
class RepositoryBoundary:
    """The validated root and safe metadata exposed to the report builder."""

    root: Path
    label: str
    limits: BoundaryLimits
    readable: bool = True
    external_symlinks: str = "not_followed"
    exclusions: tuple[str, ...] = ()

    def report_metadata(self) -> dict[str, object]:
        """Return a report-safe boundary summary with no absolute path."""

        return {
            "root_kind": "directory",
            "readability": "readable" if self.readable else "unreadable",
            "inspection": "root metadata only",
            "external_symlinks": self.external_symlinks,
            "exclusions": list(self.exclusions),
            "staging": "none",
        }


def validate_repository(
    path: PathLike,
    *,
    limits: BoundaryLimits | Mapping[str, object] | None = None,
    exclusions: object | None = None,
) -> RepositoryBoundary:
    """Validate an existing readable directory without reading project files."""

    try:
        raw = os.fsdecode(os.fspath(path))
    except (TypeError, ValueError) as error:
        raise BoundaryValidationError("repository path is invalid") from error
    if not raw.strip():
        raise BoundaryValidationError("repository path is empty")

    normalized_limits = validate_limits(limits)
    candidate = Path(raw)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise BoundaryValidationError(
            f"repository path does not exist: {safe_path_label(raw)}"
        ) from error
    except PermissionError as error:
        raise BoundaryValidationError(
            f"repository path cannot be resolved: {safe_path_label(raw)}"
        ) from error
    except OSError as error:
        raise BoundaryValidationError(
            f"repository path cannot be resolved: {safe_path_label(raw)}"
        ) from error

    if not resolved.is_dir():
        raise BoundaryValidationError(
            f"repository path is not a directory: {safe_path_label(raw)}"
        )

    # os.scandir opens the directory and is intentionally not iterated.  This
    # establishes read access while avoiding M2-style repository discovery.
    try:
        with os.scandir(resolved):
            pass
    except (PermissionError, OSError) as error:
        raise BoundaryValidationError(
            f"repository directory is not readable: {safe_path_label(raw)}"
        ) from error

    label = safe_text(resolved.name or "repository", limit=80)
    return RepositoryBoundary(
        root=resolved,
        label=label,
        limits=normalized_limits,
        exclusions=effective_exclusions(exclusions),
    )


def validate_output_path(path: PathLike | None) -> Path | None:
    """Validate an explicit report destination; never create its parent."""

    if path is None:
        return None
    try:
        raw = os.fsdecode(os.fspath(path))
    except (TypeError, ValueError) as error:
        raise OutputValidationError("output path is invalid") from error
    if not raw.strip():
        raise OutputValidationError("output path is empty")

    destination = Path(raw)
    try:
        parent = destination.parent.resolve(strict=True)
    except FileNotFoundError as error:
        raise OutputValidationError(
            f"output parent does not exist: {safe_path_label(raw)}"
        ) from error
    except (PermissionError, OSError) as error:
        raise OutputValidationError(
            f"output parent cannot be resolved: {safe_path_label(raw)}"
        ) from error
    if not parent.is_dir():
        raise OutputValidationError(
            f"output parent is not a directory: {safe_path_label(raw)}"
        )
    if destination.exists() and destination.is_dir():
        raise OutputValidationError(
            f"output path is a directory: {safe_path_label(raw)}"
        )
    return destination
