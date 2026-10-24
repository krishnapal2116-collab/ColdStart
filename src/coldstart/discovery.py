"""Deterministic, bounded repository inventory and project detection.

The discovery layer treats every repository entry as untrusted data.  It uses
``os.scandir`` with ``follow_symlinks=False``, sorts each directory before
walking it, and reads only a small allowlist of metadata files for detection.
No source module is imported, no command is spawned, and no staging directory is
created.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .boundary import (
    BoundaryLimits,
    BoundaryValidationError,
    effective_exclusions,
    is_excluded,
    normalize_exclusion,
    validate_limits,
)
DETECTION_READ_LIMIT = 64 * 1024
_PYTHON_METADATA = {
    "pyproject.toml": ("python-pyproject", 5),
    "setup.py": ("python-setup", 4),
    "setup.cfg": ("python-setup-config", 4),
    ".python-version": ("python-runtime", 2),
}
_NODE_METADATA = {
    "package.json": ("node-package", 5),
    "package-lock.json": ("node-lock", 3),
    "npm-shrinkwrap.json": ("node-lock", 3),
    "yarn.lock": ("node-lock", 3),
    "pnpm-lock.yaml": ("node-lock", 3),
    ".nvmrc": ("node-runtime", 2),
    ".node-version": ("node-runtime", 2),
}
_PYTHON_SUFFIXES = {".py", ".pyi"}
_NODE_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
_METADATA_FILENAMES = set(_PYTHON_METADATA) | set(_NODE_METADATA)


@dataclass(frozen=True)
class FileRecord:
    """Safe metadata for one inventory entry; no file contents are retained."""

    relative_path: str
    kind: str
    size: int | None
    depth: int
    readable: bool = True
    external_symlink: bool = False
    symlink_target: str | None = None

    @property
    def path(self) -> str:
        return self.relative_path

    @property
    def size_bytes(self) -> int | None:
        return self.size

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.relative_path,
            "kind": self.kind,
            "size": self.size,
            "depth": self.depth,
            "readable": self.readable,
            "external_symlink": self.external_symlink,
            "symlink_target": self.symlink_target,
        }

    def fingerprint_dict(self) -> dict[str, object]:
        """Return only deterministic, non-host-specific fingerprint metadata."""

        return {
            "path": self.relative_path,
            "kind": self.kind,
            "size": self.size,
            "depth": self.depth,
            "readable": self.readable,
            "external_symlink": self.external_symlink,
        }


@dataclass(frozen=True)
class InventoryResult:
    """Bounded inventory output and truthful coverage metadata."""

    records: tuple[FileRecord, ...]
    limits: BoundaryLimits
    exclusions: tuple[str, ...]
    total_bytes: int
    max_depth_observed: int
    truncated: bool
    omission_reasons: tuple[str, ...]
    omitted_count: int
    unreadable_paths: tuple[str, ...]
    external_symlinks: tuple[dict[str, str], ...]
    excluded_paths: tuple[str, ...]
    staging: str = "none"

    @property
    def file_count(self) -> int:
        return self.regular_file_count

    @property
    def files(self) -> tuple[FileRecord, ...]:
        """Compatibility name for callers treating the inventory as a file list."""

        return self.records

    @property
    def paths(self) -> tuple[str, ...]:
        return self.relative_paths

    @property
    def byte_count(self) -> int:
        return self.total_bytes

    @property
    def total_byte_count(self) -> int:
        return self.total_bytes

    @property
    def regular_file_count(self) -> int:
        return sum(1 for record in self.records if record.kind == "file")

    @property
    def entry_count(self) -> int:
        return len(self.records)

    @property
    def external_symlink_evidence(self) -> tuple[dict[str, str], ...]:
        return self.external_symlinks

    @property
    def stats(self) -> dict[str, object]:
        return self.stats_dict()

    @property
    def incomplete(self) -> bool:
        return self.truncated or bool(self.unreadable_paths)

    @property
    def coverage(self) -> str:
        return "partial" if self.incomplete else "complete"

    @property
    def relative_paths(self) -> tuple[str, ...]:
        return tuple(record.relative_path for record in self.records)

    def stats_dict(self) -> dict[str, object]:
        return {
            "file_count": self.file_count,
            "entry_count": self.entry_count,
            "regular_file_count": self.regular_file_count,
            "total_bytes": self.total_bytes,
            "max_depth_observed": self.max_depth_observed,
            "omitted_count": self.omitted_count,
            "unreadable_count": len(self.unreadable_paths),
            "external_symlink_count": len(self.external_symlinks),
            "excluded_count": len(self.excluded_paths),
            "coverage": self.coverage,
            "truncated": self.truncated,
            "staging": self.staging,
            "limits": self.limits.as_dict(),
            "exclusions": list(self.exclusions),
            "omission_reasons": list(self.omission_reasons),
            "external_symlinks": [dict(item) for item in self.external_symlinks],
        }

    def fingerprint_inputs(self) -> dict[str, object]:
        return {
            "paths": list(self.relative_paths),
            "file_metadata": [
                record.fingerprint_dict()
                for record in self.records
            ],
            "inventory": self.stats_dict(),
        }


@dataclass(frozen=True)
class DetectionCandidate:
    id: str
    confidence: str
    evidence: tuple[str, ...]
    signals: tuple[dict[str, object], ...] = ()
    members: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "signals": [
                {
                    "id": signal.get("id"),
                    "path": signal.get("path"),
                }
                for signal in self.signals
            ],
        }
        if self.members:
            result["members"] = list(self.members)
        if self.reason:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class DetectionResult:
    candidates: tuple[DetectionCandidate, ...]
    primary: str
    metadata_inputs: tuple[dict[str, object], ...]
    metadata_errors: tuple[str, ...]
    inventory_complete: bool = True

    @property
    def incomplete(self) -> bool:
        return bool(self.metadata_errors) or not self.inventory_complete

    @property
    def project_type(self) -> str:
        return self.primary

    @property
    def fingerprint_inputs(self) -> tuple[dict[str, object], ...]:
        return self.metadata_inputs

    @property
    def recognized_paths(self) -> tuple[str, ...]:
        paths: set[str] = set()
        for candidate in self.candidates:
            if candidate.id == "unknown":
                continue
            paths.update(candidate.evidence)
        return tuple(sorted(paths))

    def to_dict(self) -> dict[str, object]:
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "primary": self.primary,
            "metadata_inputs": [dict(item) for item in self.metadata_inputs],
            "metadata_errors": list(self.metadata_errors),
            "inventory_complete": self.inventory_complete,
            "status": "partial" if self.incomplete else "complete",
        }


# Descriptive aliases keep the public M2 surface discoverable without creating
# a second implementation or changing the report model.
InventoryLimits = BoundaryLimits
FileInventory = InventoryResult
ProjectCandidate = DetectionCandidate


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _symlink_classification(root: Path, path: Path) -> tuple[bool, str]:
    """Classify a symlink target without opening or traversing it."""

    try:
        raw_target = os.readlink(path)
    except (OSError, UnicodeError):
        return False, "unreadable-target"
    try:
        root_path = root.resolve(strict=False)
        target_path = (path.parent / raw_target).resolve(strict=False)
        root_text = os.path.normcase(
            os.path.normpath(os.path.abspath(os.fspath(root_path)))
        )
        target_text = os.path.normcase(
            os.path.normpath(os.path.abspath(os.fspath(target_path)))
        )
        # Windows can expose extended-length paths for symlink targets.  Strip
        # only the comparison prefix; the target is never opened or traversed.
        for prefix in ("\\\\?\\UNC\\", "\\\\?\\", "\\??\\"):
            if root_text.startswith(prefix):
                root_text = (
                    "\\\\" + root_text[len(prefix) :]
                    if prefix == "\\\\?\\UNC\\"
                    else root_text[len(prefix) :]
                )
            if target_text.startswith(prefix):
                target_text = (
                    "\\\\" + target_text[len(prefix) :]
                    if prefix == "\\\\?\\UNC\\"
                    else target_text[len(prefix) :]
                )
        common = os.path.commonpath((root_text, target_text))
        if common != root_text:
            return True, "external"
        return False, "internal"
    except (OSError, RuntimeError):
        return False, "unresolved-target"
    except ValueError:
        # Different Windows drives (or roots) are necessarily external.
        return True, "external"


def _bounded_sorted_entries(
    iterator: Iterable[os.DirEntry[str]],
    *,
    maximum: int,
    deadline: float,
) -> tuple[list[os.DirEntry[str]], int, bool]:
    """Keep only the lexicographically earliest entries within a memory bound."""

    selected: list[os.DirEntry[str]] = []
    dropped = 0
    timed_out = False
    for entry in iterator:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        key = (entry.name.casefold(), entry.name)
        if len(selected) < maximum:
            selected.append(entry)
            continue
        worst_index = max(
            range(len(selected)),
            key=lambda index: (selected[index].name.casefold(), selected[index].name),
        )
        worst = selected[worst_index]
        worst_key = (worst.name.casefold(), worst.name)
        if key < worst_key:
            selected[worst_index] = entry
            dropped += 1
        else:
            dropped += 1
    selected.sort(key=lambda entry: (entry.name.casefold(), entry.name))
    return selected, dropped, timed_out


def inventory_repository(
    root: Path | str,
    *,
    limits: BoundaryLimits | dict[str, object] | None = None,
    excludes: Iterable[str] | None = None,
    max_files: int | None = None,
    max_bytes: int | None = None,
    max_depth: int | None = None,
    max_seconds: int | None = None,
) -> InventoryResult:
    """Collect a sorted bounded inventory without following any symlink."""

    repository_root = Path(root)
    if not repository_root.is_dir():
        raise BoundaryValidationError("inventory root is not a directory")
    if limits is None:
        selected_limit_values: dict[str, object] = {}
    elif isinstance(limits, BoundaryLimits):
        selected_limit_values = limits.as_dict()
    else:
        selected_limit_values = dict(limits)
    selected_limit_values.update(
        {
            key: value
            for key, value in {
                "max_files": max_files,
                "max_bytes": max_bytes,
                "max_depth": max_depth,
                "max_seconds": max_seconds,
            }.items()
            if value is not None
        }
    )
    normalized_limits = validate_limits(selected_limit_values or None)
    if isinstance(excludes, str):
        raise BoundaryValidationError("excludes must be an iterable of relative paths")
    user_exclusions = tuple(normalize_exclusion(value) for value in (excludes or ()))
    all_exclusions = effective_exclusions(user_exclusions)
    deadline = time.monotonic() + normalized_limits.max_seconds

    records: list[FileRecord] = []
    external_symlinks: list[dict[str, str]] = []
    excluded_paths: list[str] = []
    unreadable_paths: list[str] = []
    omission_reasons: list[str] = []
    total_bytes = 0
    max_depth_observed = 0
    omitted_count = 0
    truncated = False
    stop_reason: str | None = None
    directories: list[tuple[Path, int]] = [(repository_root, 0)]

    def stop(reason: str) -> None:
        nonlocal truncated, stop_reason
        truncated = True
        if stop_reason is None:
            stop_reason = reason

    while directories and not stop_reason:
        if time.monotonic() >= deadline:
            stop("time_limit")
            break
        current, directory_depth = directories.pop()
        try:
            with os.scandir(current) as iterator:
                entries, dropped_entries, timed_out = _bounded_sorted_entries(
                    iterator,
                    maximum=max(1, normalized_limits.max_files + 1),
                    deadline=deadline,
                )
        except (OSError, PermissionError):
            relative_current = "." if current == repository_root else _relative(repository_root, current)
            unreadable_paths.append(relative_current)
            omitted_count += 1
            omission_reasons.append("unreadable_directory")
            continue

        if dropped_entries:
            truncated = True
            omitted_count += dropped_entries
            omission_reasons.append("directory_entry_limit")
        if timed_out:
            stop("time_limit")
            break

        child_directories: list[tuple[Path, int]] = []
        for entry in entries:
            if time.monotonic() >= deadline:
                stop("time_limit")
                break
            path = Path(entry.path)
            relative_path = _relative(repository_root, path)
            max_depth_observed = max(max_depth_observed, directory_depth)
            if is_excluded(relative_path, all_exclusions):
                excluded_paths.append(relative_path)
                omitted_count += 1
                continue

            try:
                is_link = entry.is_symlink()
            except OSError:
                is_link = False
            if is_link:
                external, target_class = _symlink_classification(repository_root, path)
                if len(records) >= normalized_limits.max_files:
                    stop("file_limit")
                    break
                records.append(
                    FileRecord(
                        relative_path=relative_path,
                        kind="symlink",
                        size=0,
                        depth=directory_depth,
                        readable=True,
                        external_symlink=external,
                        symlink_target=target_class,
                    )
                )
                if external:
                    external_symlinks.append(
                        {"path": relative_path, "target": "external"}
                    )
                continue

            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_directory = False
            if is_directory:
                child_depth = directory_depth + 1
                max_depth_observed = max(max_depth_observed, child_depth)
                if directory_depth >= normalized_limits.max_depth:
                    truncated = True
                    omitted_count += 1
                    omission_reasons.append("depth_limit")
                else:
                    child_directories.append((path, child_depth))
                continue

            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                is_file = False
            if not is_file:
                omitted_count += 1
                omission_reasons.append("unsupported_entry")
                continue

            if len(records) >= normalized_limits.max_files:
                stop("file_limit")
                break

            try:
                size = entry.stat(follow_symlinks=False).st_size
                if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                    raise OSError("invalid file size")
            except (OSError, OverflowError):
                unreadable_paths.append(relative_path)
                omitted_count += 1
                omission_reasons.append("unreadable_file")
                records.append(
                    FileRecord(
                        relative_path=relative_path,
                        kind="file",
                        size=None,
                        depth=directory_depth,
                        readable=False,
                    )
                )
                continue

            if total_bytes + size > normalized_limits.max_bytes:
                stop("byte_limit")
                break
            records.append(
                FileRecord(
                    relative_path=relative_path,
                    kind="file",
                    size=size,
                    depth=directory_depth,
                )
            )
            total_bytes += size

        # Reverse because the stack is LIFO; the resulting walk is stable.
        directories.extend(reversed(child_directories))

    if stop_reason:
        omission_reasons.append(stop_reason)
    records.sort(key=lambda record: (record.relative_path.casefold(), record.relative_path))
    external_symlinks.sort(key=lambda item: item["path"])
    excluded_paths.sort()
    unreadable_paths.sort()
    return InventoryResult(
        records=tuple(records),
        limits=normalized_limits,
        exclusions=all_exclusions,
        total_bytes=total_bytes,
        max_depth_observed=max_depth_observed,
        truncated=truncated,
        omission_reasons=tuple(sorted(set(omission_reasons))),
        omitted_count=omitted_count,
        unreadable_paths=tuple(unreadable_paths),
        external_symlinks=tuple(external_symlinks),
        excluded_paths=tuple(excluded_paths),
    )


def _metadata_signal(path: str) -> tuple[str, int] | None:
    basename = path.rsplit("/", 1)[-1]
    if basename in _PYTHON_METADATA:
        return _PYTHON_METADATA[basename]
    if basename in _NODE_METADATA:
        return _NODE_METADATA[basename]
    suffix = Path(basename).suffix.lower()
    if suffix in _PYTHON_SUFFIXES:
        return ("python-source", 1)
    if suffix in _NODE_SUFFIXES:
        return ("node-source", 1)
    if basename.startswith("requirements") and suffix in {".txt", ".in", ".lock"}:
        return ("python-dependencies", 3)
    return None


def _bounded_metadata(root: Path, record: FileRecord) -> tuple[dict[str, object], str | None]:
    """Read and parse only allowlisted metadata, with a hard byte bound."""

    basename = record.relative_path.rsplit("/", 1)[-1]
    if basename not in _METADATA_FILENAMES or record.kind != "file":
        return {}, None
    item: dict[str, object] = {
        "path": record.relative_path,
        "size": record.size,
        "read_limit": DETECTION_READ_LIMIT,
    }
    if not record.readable or record.size is None:
        item["status"] = "unreadable"
        return item, record.relative_path
    if record.size > DETECTION_READ_LIMIT:
        item["status"] = "too_large_for_detection"
        return item, record.relative_path
    path = root / Path(record.relative_path)
    try:
        with path.open("rb") as handle:
            data = handle.read(DETECTION_READ_LIMIT + 1)
    except OSError:
        item["status"] = "unreadable"
        return item, record.relative_path
    if len(data) > DETECTION_READ_LIMIT:
        item["status"] = "too_large_for_detection"
        return item, record.relative_path
    digest = hashlib.sha256(data).hexdigest()
    item["digest"] = digest
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        item["status"] = "not_utf8"
        return item, record.relative_path
    try:
        if basename == "pyproject.toml":
            tomllib.loads(text)
        elif basename == "package.json":
            json.loads(text)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, ValueError):
        item["status"] = "malformed"
        return item, record.relative_path
    item["status"] = "parsed"
    return item, None


def _confidence(score: int) -> str:
    if score >= 5:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def detect_projects(
    root: Path | str,
    inventory: InventoryResult | None = None,
) -> DetectionResult:
    """Detect Python, Node, unknown, or mixed signals deterministically."""

    repository_root = Path(root)
    if inventory is None:
        inventory = inventory_repository(repository_root)
    python_signals: list[dict[str, object]] = []
    node_signals: list[dict[str, object]] = []
    metadata_inputs: list[dict[str, object]] = []
    metadata_errors: list[str] = []
    for record in inventory.records:
        if record.kind != "file":
            continue
        signal = _metadata_signal(record.relative_path)
        if signal is not None:
            signal_id, weight = signal
            item = {
                "id": signal_id,
                "path": record.relative_path,
                "weight": weight,
            }
            if signal_id.startswith("python"):
                python_signals.append(item)
            elif signal_id.startswith("node"):
                node_signals.append(item)
        metadata, error_path = _bounded_metadata(repository_root, record)
        if metadata:
            metadata_inputs.append(metadata)
        if error_path is not None:
            metadata_errors.append(error_path)

    python_signals.sort(key=lambda item: (str(item["id"]), str(item["path"])))
    node_signals.sort(key=lambda item: (str(item["id"]), str(item["path"])))
    metadata_inputs.sort(key=lambda item: str(item.get("path", "")))
    metadata_errors = sorted(set(metadata_errors))
    python_score = sum(int(item["weight"]) for item in python_signals)
    node_score = sum(int(item["weight"]) for item in node_signals)

    def candidate(
        candidate_id: str,
        score: int,
        signals: list[dict[str, object]],
        *,
        reason: str = "",
        members: tuple[str, ...] = (),
    ) -> DetectionCandidate:
        evidence = tuple(sorted({str(item["path"]) for item in signals}))
        return DetectionCandidate(
            id=candidate_id,
            confidence=_confidence(score),
            evidence=evidence,
            signals=tuple(dict(item) for item in signals),
            members=members,
            reason=reason,
        )

    candidates: list[DetectionCandidate]
    if python_score and node_score:
        mixed_confidence = "high" if min(python_score, node_score) >= 3 else "medium"
        mixed = DetectionCandidate(
            id="mixed",
            confidence=mixed_confidence,
            evidence=tuple(
                sorted(
                    {
                        str(item["path"])
                        for item in python_signals + node_signals
                    }
                )
            ),
            signals=tuple(
                dict(item)
                for item in sorted(
                    python_signals + node_signals,
                    key=lambda item: (str(item["id"]), str(item["path"])),
                )
            ),
            members=("node", "python"),
            reason="Python and Node signals are both present; no ecosystem was silently selected.",
        )
        # Keep the aggregate first for terminal rendering, while retaining the
        # individual candidates as evidence for applicability planning.
        candidates = [
            mixed,
            candidate("python", python_score, python_signals),
            candidate("node", node_score, node_signals),
        ]
        primary = "mixed"
    elif python_score:
        candidates = [candidate("python", python_score, python_signals)]
        primary = "python"
    elif node_score:
        candidates = [candidate("node", node_score, node_signals)]
        primary = "node"
    else:
        candidates = [
            DetectionCandidate(
                id="unknown",
                confidence="low",
                evidence=(),
                reason="No bounded Python or Node project signal was found.",
            )
        ]
        primary = "unknown"

    return DetectionResult(
        candidates=tuple(candidates),
        primary=primary,
        metadata_inputs=tuple(metadata_inputs),
        metadata_errors=tuple(metadata_errors),
        inventory_complete=not inventory.incomplete,
    )


discover_inventory = inventory_repository
discover_repository = inventory_repository
detect_project_types = detect_projects


__all__ = [
    "DETECTION_READ_LIMIT",
    "DetectionCandidate",
    "DetectionResult",
    "FileInventory",
    "FileRecord",
    "InventoryLimits",
    "InventoryResult",
    "ProjectCandidate",
    "detect_project_types",
    "detect_projects",
    "discover_inventory",
    "discover_repository",
    "inventory_repository",
]
