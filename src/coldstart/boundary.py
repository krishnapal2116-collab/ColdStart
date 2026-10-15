"""Repository and output-boundary validation for the static audit.

The repository under inspection is untrusted input.  M1 therefore validates the
root directory and opens it only far enough to establish readability; it does
not enumerate, import, parse, or execute project files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, TypeAlias


DEFAULT_MAX_FILES = 10_000
DEFAULT_MAX_BYTES = 50_000_000
DEFAULT_MAX_SECONDS = 30


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

    def __post_init__(self) -> None:
        for name in ("max_files", "max_bytes", "max_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise BoundaryValidationError(f"{name} must be a positive integer")

    def as_dict(self) -> dict[str, int]:
        return {
            "max_files": self.max_files,
            "max_bytes": self.max_bytes,
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
    try:
        return BoundaryLimits(
            max_files=values["max_files"],  # type: ignore[arg-type]
            max_bytes=values["max_bytes"],  # type: ignore[arg-type]
            max_seconds=values["max_seconds"],  # type: ignore[arg-type]
        )
    except KeyError as error:
        raise BoundaryValidationError(f"missing limit: {error.args[0]}") from error
    except TypeError as error:
        raise BoundaryValidationError("limits must contain integer values") from error


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
        }


def validate_repository(
    path: PathLike,
    *,
    limits: BoundaryLimits | Mapping[str, object] | None = None,
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
    return RepositoryBoundary(root=resolved, label=label, limits=normalized_limits)


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
