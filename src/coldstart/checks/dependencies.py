"""Bounded static dependency checks for Python repositories.

The functions in this module intentionally consume the immutable discovery
objects rather than walking a repository themselves.  Every file read is for a
file already present in ``InventoryResult`` and is capped at
``DEPENDENCY_READ_LIMIT`` bytes.  Python source is parsed with :mod:`ast`; it
is never imported or executed.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from ..discovery import DetectionResult, FileRecord, InventoryResult
from ..findings import Applicability, Evidence, Finding


RULE_VERSION = "3"
DEPENDENCY_READ_LIMIT = 64 * 1024
MAX_INSPECTED_FILES = 256

_PYTHON_SUFFIXES = {".py", ".pyi"}
_REQUIREMENTS_SUFFIXES = {".txt", ".in", ".lock"}
_KNOWN_LOCK_NAMES = {"poetry.lock", "uv.lock", "pipfile.lock", "pdm.lock"}
_NODE_LOCK_NAMES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
}
_DOC_BASENAMES = {"readme", "readme.md", "readme.rst", "readme.txt"}

_REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REQUIREMENT_START = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<rest>.*)$"
)
_VERSION_OPERATOR = re.compile(r"^(===|==|!=|<=|>=|~=|<|>)(?P<version>[^\s;]+)")
_EGG_NAME = re.compile(r"[#&]egg=(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)")

_IGNORED_REQUIREMENT_OPTIONS = (
    "--hash=",
    "--index-url",
    "--extra-index-url",
    "--find-links",
    "-f ",
    "--trusted-host",
    "--no-index",
    "--require-hashes",
    "--pre",
    "--prefer-binary",
    "--no-binary",
    "--only-binary",
)

# ``sys.stdlib_module_names`` is available on every supported runtime.  The
# fallback keeps the module usable on older interpreters used by contributors.
try:
    _STDLIB_MODULES = set(sys.stdlib_module_names)
except AttributeError:  # pragma: no cover - compatibility fallback
    _STDLIB_MODULES = {
        "abc",
        "argparse",
        "ast",
        "asyncio",
        "base64",
        "collections",
        "contextlib",
        "dataclasses",
        "datetime",
        "functools",
        "hashlib",
        "itertools",
        "json",
        "logging",
        "math",
        "os",
        "pathlib",
        "re",
        "subprocess",
        "sys",
        "tempfile",
        "tomllib",
        "typing",
        "unittest",
        "urllib",
        "uuid",
    }
_STDLIB_MODULE_KEYS = {
    name.casefold().replace("-", "_") for name in _STDLIB_MODULES
}

# A small, conservative import-to-distribution map avoids known false
# positives without pretending that static import mapping is complete.
_IMPORT_DISTRIBUTION_ALIASES: dict[str, tuple[str, ...]] = {
    "bs4": ("beautifulsoup4",),
    "cv2": ("opencv-python", "opencv-contrib-python"),
    "crypto": ("pycryptodome", "pycrypto"),
    "dateutil": ("python-dateutil",),
    "dotenv": ("python-dotenv",),
    "pil": ("pillow",),
    "sklearn": ("scikit-learn",),
    "yaml": ("pyyaml",),
}


@dataclass(frozen=True)
class _ReadText:
    """Result of one bounded, repository-contained text read."""

    path: str
    text: str | None
    digest: str | None
    error: str | None = None


@dataclass(frozen=True)
class _RequirementInfo:
    path: str
    dependency_count: int
    names: frozenset[str]
    fully_pinned: bool
    uncertain: bool


@dataclass(frozen=True)
class _ImportUse:
    path: str
    module: str
    line: int | None


@dataclass
class _Analysis:
    declaration_paths: list[str] = field(default_factory=list)
    declared_names: set[str] = field(default_factory=set)
    declaration_count: int = 0
    declaration_seen: bool = False
    manager_hints: set[str] = field(default_factory=set)
    project_names: set[str] = field(default_factory=set)
    source_imports: list[_ImportUse] = field(default_factory=list)
    source_errors: list[tuple[str | None, str]] = field(default_factory=list)
    parse_errors: list[tuple[str | None, str]] = field(default_factory=list)
    requirement_files: list[_RequirementInfo] = field(default_factory=list)
    lock_paths: list[str] = field(default_factory=list)
    unrelated_node_locks: list[str] = field(default_factory=list)
    documentation: list[tuple[str, str]] = field(default_factory=list)
    documentation_errors: list[tuple[str | None, str]] = field(default_factory=list)
    local_module_names: set[str] = field(default_factory=set)
    inspection_limited: bool = False

    @property
    def errors(self) -> list[tuple[str | None, str]]:
        return self.source_errors + self.parse_errors + self.documentation_errors


def _canonical_name(value: str) -> str:
    """Normalize a distribution or module name for conservative comparison."""

    return re.sub(r"[-_.]+", "-", value.strip()).casefold()


def _module_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_")


def _normal_relative_path(value: object) -> str | None:
    """Normalize an inventory path without allowing a boundary escape."""

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
    """Return a contained path, rejecting symlinks and malformed records."""

    relative = _normal_relative_path(record.relative_path)
    if relative is None or relative == ".":
        return None, "invalid relative inventory path"
    try:
        resolved_root = root.resolve(strict=False)
    except (OSError, RuntimeError):
        return None, "repository root could not be resolved"

    candidate = resolved_root.joinpath(*relative.split("/"))
    # Discovery does not follow symlinks.  Check each component again so a
    # caller-provided InventoryResult cannot turn this rule into an external
    # file reader.
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
            (os.path.normcase(os.fspath(resolved_root)), os.path.normcase(os.fspath(resolved_candidate)))
        )
    except (OSError, ValueError, RuntimeError):
        return None, "inventory entry escaped the repository boundary"
    if common != os.path.normcase(os.fspath(resolved_root)):
        return None, "inventory entry escaped the repository boundary"
    return candidate, None


def _read_bounded_text(root: Path, record: FileRecord) -> _ReadText:
    """Read one discovered regular file with a hard byte limit."""

    path = _normal_relative_path(record.relative_path)
    safe_path = path if path is not None else str(record.relative_path)
    if record.kind != "file":
        return _ReadText(safe_path, None, None, "inventory record is not a regular file")
    if not record.readable:
        return _ReadText(safe_path, None, None, "inventory record is unreadable")
    if record.size is not None:
        if isinstance(record.size, bool) or not isinstance(record.size, int) or record.size < 0:
            return _ReadText(safe_path, None, None, "inventory record has an invalid size")
        if record.size > DEPENDENCY_READ_LIMIT:
            return _ReadText(safe_path, None, None, "file exceeds the bounded text limit")
    candidate, error = _safe_record_path(root, record)
    if candidate is None:
        return _ReadText(safe_path, None, None, error or "file path is not contained")
    try:
        with candidate.open("rb") as handle:
            data = handle.read(DEPENDENCY_READ_LIMIT + 1)
    except (OSError, PermissionError):
        return _ReadText(safe_path, None, None, "file could not be read")
    if len(data) > DEPENDENCY_READ_LIMIT:
        return _ReadText(safe_path, None, None, "file exceeds the bounded text limit")
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _ReadText(safe_path, None, digest, "file is not valid UTF-8 text")
    return _ReadText(safe_path, text, digest)


def _requirement_name(value: str) -> str | None:
    match = _REQUIREMENT_NAME.fullmatch(value.strip())
    if match is None:
        return None
    return _canonical_name(value)


def _parse_requirement_expression(value: str) -> tuple[str | None, bool, bool]:
    """Return ``(name, pinned, uncertain)`` for one requirement expression."""

    expression = value.strip()
    if not expression:
        return None, False, False
    if expression.startswith("#"):
        return None, False, False

    # A local editable install is a project reference, not a third-party
    # dependency.  A VCS editable without an egg name is intentionally
    # uncertain rather than guessed.
    if expression == "-e ." or expression == "--editable .":
        return None, False, False
    if expression.startswith(("-e ", "--editable ")):
        match = _EGG_NAME.search(expression)
        if match:
            return _canonical_name(match.group("name")), False, False
        return None, False, True
    if expression.startswith(("./", "../", "/", "~/") ):
        return None, False, False
    if expression.startswith(("git+", "hg+", "svn+", "bzr+", "http://", "https://")):
        match = _EGG_NAME.search(expression)
        if match:
            return _canonical_name(match.group("name")), False, False
        return None, False, True

    match = _REQUIREMENT_START.match(expression)
    if match is None:
        return None, False, True
    name = _requirement_name(match.group("name"))
    if name is None:
        return None, False, True
    rest = match.group("rest").strip()
    if not rest:
        return name, False, False
    if rest.startswith("["):
        closing = rest.find("]")
        if closing < 0:
            return None, False, True
        rest = rest[closing + 1 :].strip()
        if not rest:
            return name, False, False
    if rest.startswith(";"):
        return name, False, True if not rest[1:].strip() else False
    if rest.startswith("@"):
        return name, False, False

    version_match = _VERSION_OPERATOR.match(rest)
    if version_match is None:
        return None, False, True
    remainder = rest[version_match.end() :].strip()
    if not remainder:
        return name, version_match.group(1) in {"==", "==="}, False
    # Hashes and environment markers may follow a valid version.  Unknown
    # trailing tokens remain unverified instead of being silently accepted.
    if ";" in remainder:
        version_part, marker = remainder.split(";", 1)
        # A marker may follow the version immediately (``pkg==1; ...``), so
        # an empty version_part here is valid because the version was already
        # captured by ``_VERSION_OPERATOR``.
        if marker.strip() == "":
            return None, False, True
        remainder = version_part.strip()
    if " --" in remainder or remainder.startswith("--"):
        remainder = remainder.split(" --", 1)[0].strip()
    if any(character.isspace() for character in remainder):
        return None, False, True
    pinned = version_match.group(1) in {"==", "==="}
    return name, pinned, False


def _parse_requirements(path: str, text: str) -> _RequirementInfo:
    names: set[str] = set()
    count = 0
    uncertain = False
    fully_pinned = True
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            uncertain = True
            fully_pinned = False
            continue
        if line.startswith(("--", "-c ", "--constraint ", "-r ", "--requirement ")):
            # Includes and constraints are not expanded by this bounded rule.
            # They remain declaration evidence, but their contents are partial.
            if line.startswith(("-c ", "--constraint ", "-r ", "--requirement ")):
                uncertain = True
                fully_pinned = False
            continue
        if any(line == option.rstrip() or line.startswith(option) for option in _IGNORED_REQUIREMENT_OPTIONS):
            continue
        if " #" in line:
            line = line.split(" #", 1)[0].rstrip()
        name, pinned, expression_uncertain = _parse_requirement_expression(line)
        if expression_uncertain:
            uncertain = True
            fully_pinned = False
            continue
        if name is None:
            continue
        names.add(name)
        count += 1
        if not pinned:
            fully_pinned = False
    if count == 0:
        fully_pinned = False
    return _RequirementInfo(
        path=path,
        dependency_count=count,
        names=frozenset(names),
        fully_pinned=fully_pinned and not uncertain,
        uncertain=uncertain,
    )


def _add_dependency_value(analysis: _Analysis, value: object, path: str, *, context: str) -> None:
    if not isinstance(value, str):
        analysis.parse_errors.append((path, f"{context} contains a non-text dependency entry"))
        return
    name, _pinned, uncertain = _parse_requirement_expression(value)
    if uncertain:
        analysis.parse_errors.append((path, f"{context} contains an unsupported dependency expression"))
        return
    if name is None:
        # Local/editable references do not identify a third-party package.
        return
    if name == "python":
        # Poetry's ``python = ">=3.12"`` is a runtime constraint, not a
        # package dependency for either check.
        return
    analysis.declared_names.add(name)
    analysis.declaration_count += 1


def _add_dependency_list(analysis: _Analysis, value: object, path: str, *, context: str) -> None:
    if not isinstance(value, list):
        analysis.parse_errors.append((path, f"{context} must be a list of dependency strings"))
        return
    for entry in value:
        if isinstance(entry, Mapping):
            # PEP 735 permits explicit group inclusion entries.  The included
            # group's package names are not duplicated here, but the table is
            # still valid evidence.
            if set(entry) == {"include-group"} and isinstance(entry.get("include-group"), str):
                continue
            analysis.parse_errors.append((path, f"{context} contains an unsupported table entry"))
            continue
        _add_dependency_value(analysis, entry, path, context=context)


def _add_dependency_mapping(analysis: _Analysis, value: object, path: str, *, context: str) -> None:
    if not isinstance(value, Mapping):
        analysis.parse_errors.append((path, f"{context} must be a dependency table"))
        return
    for key, requirement in sorted(value.items(), key=lambda item: str(item[0]).casefold()):
        if not isinstance(key, str):
            analysis.parse_errors.append((path, f"{context} contains a non-text package name"))
            continue
        if key.casefold() == "python":
            continue
        name = _requirement_name(key)
        if name is None:
            analysis.parse_errors.append((path, f"{context} contains an invalid package name"))
            continue
        if not isinstance(requirement, (str, Mapping)):
            analysis.parse_errors.append((path, f"{context} contains an invalid version value"))
            continue
        analysis.declared_names.add(name)
        analysis.declaration_count += 1


def _parse_pyproject(path: str, text: str, analysis: _Analysis) -> None:
    try:
        document = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError, TypeError):
        analysis.parse_errors.append((path, "pyproject.toml is malformed"))
        return
    if not isinstance(document, Mapping):
        analysis.parse_errors.append((path, "pyproject.toml did not contain a TOML table"))
        return

    project = document.get("project")
    if project is not None:
        if not isinstance(project, Mapping):
            analysis.parse_errors.append((path, "the project table is malformed"))
        else:
            analysis.manager_hints.add("pyproject")
            project_name = project.get("name")
            if isinstance(project_name, str):
                normalized = _canonical_name(project_name)
                analysis.project_names.add(normalized)
                analysis.project_names.add(normalized.replace("-", "_"))
            elif project_name is not None:
                analysis.parse_errors.append((path, "project.name is not text"))
            if "dependencies" in project:
                analysis.declaration_seen = True
                _add_dependency_list(
                    analysis,
                    project.get("dependencies"),
                    path,
                    context="project.dependencies",
                )
            optional = project.get("optional-dependencies")
            if optional is not None:
                analysis.declaration_seen = True
                if not isinstance(optional, Mapping):
                    analysis.parse_errors.append((path, "project.optional-dependencies must be a table"))
                else:
                    for group_name, values in sorted(optional.items(), key=lambda item: str(item[0]).casefold()):
                        if not isinstance(group_name, str):
                            analysis.parse_errors.append((path, "optional dependency group name is not text"))
                            continue
                        _add_dependency_list(
                            analysis,
                            values,
                            path,
                            context=f"project.optional-dependencies.{group_name}",
                        )

    dependency_groups = document.get("dependency-groups")
    if dependency_groups is not None:
        analysis.declaration_seen = True
        if not isinstance(dependency_groups, Mapping):
            analysis.parse_errors.append((path, "dependency-groups must be a table"))
        else:
            for group_name, values in sorted(dependency_groups.items(), key=lambda item: str(item[0]).casefold()):
                if not isinstance(group_name, str):
                    analysis.parse_errors.append((path, "dependency group name is not text"))
                    continue
                _add_dependency_list(
                    analysis,
                    values,
                    path,
                    context=f"dependency-groups.{group_name}",
                )

    tool = document.get("tool")
    if tool is not None and not isinstance(tool, Mapping):
        analysis.parse_errors.append((path, "tool table is malformed"))
        return
    if not isinstance(tool, Mapping):
        return

    poetry = tool.get("poetry")
    if poetry is not None:
        analysis.manager_hints.add("poetry")
        if not isinstance(poetry, Mapping):
            analysis.parse_errors.append((path, "tool.poetry table is malformed"))
        else:
            for key in ("dependencies", "dev-dependencies"):
                if key in poetry:
                    analysis.declaration_seen = True
                    _add_dependency_mapping(analysis, poetry.get(key), path, context=f"tool.poetry.{key}")
            groups = poetry.get("group")
            if groups is not None:
                if not isinstance(groups, Mapping):
                    analysis.parse_errors.append((path, "tool.poetry.group table is malformed"))
                else:
                    for group_name, group in sorted(groups.items(), key=lambda item: str(item[0]).casefold()):
                        if not isinstance(group, Mapping):
                            analysis.parse_errors.append((path, "tool.poetry.group entry is malformed"))
                            continue
                        if "dependencies" in group:
                            analysis.declaration_seen = True
                            _add_dependency_mapping(
                                analysis,
                                group.get("dependencies"),
                                path,
                                context=f"tool.poetry.group.{group_name}.dependencies",
                            )

    uv = tool.get("uv")
    if uv is not None:
        analysis.manager_hints.add("uv")
        if not isinstance(uv, Mapping):
            analysis.parse_errors.append((path, "tool.uv table is malformed"))

    pdm = tool.get("pdm")
    if pdm is not None:
        analysis.manager_hints.add("pdm")
        if not isinstance(pdm, Mapping):
            analysis.parse_errors.append((path, "tool.pdm table is malformed"))
        else:
            for key in ("dependencies", "dev-dependencies"):
                if key in pdm:
                    analysis.declaration_seen = True
                    value = pdm.get(key)
                    if isinstance(value, Mapping):
                        _add_dependency_mapping(analysis, value, path, context=f"tool.pdm.{key}")
                    else:
                        _add_dependency_list(analysis, value, path, context=f"tool.pdm.{key}")


def _is_requirements_path(path: str) -> bool:
    basename = path.rsplit("/", 1)[-1].casefold()
    return basename.startswith("requirements") and Path(basename).suffix in _REQUIREMENTS_SUFFIXES


def _is_lock_path(path: str) -> bool:
    basename = path.rsplit("/", 1)[-1].casefold()
    if basename in _KNOWN_LOCK_NAMES:
        return True
    return basename.startswith("requirements") and basename.endswith(".lock")


def _is_node_lock_path(path: str) -> bool:
    return path.rsplit("/", 1)[-1].casefold() in _NODE_LOCK_NAMES


def _is_python_source(path: str) -> bool:
    return Path(path).suffix.casefold() in _PYTHON_SUFFIXES


def _is_documentation(path: str) -> bool:
    basename = path.rsplit("/", 1)[-1].casefold()
    if basename in _DOC_BASENAMES or basename.startswith("readme."):
        return True
    parts = path.casefold().split("/")
    return len(parts) > 1 and parts[-2] in {"docs", "documentation"} and Path(basename).suffix in {".md", ".rst", ".txt"}


def _local_modules(records: Iterable[FileRecord], project_names: Iterable[str]) -> set[str]:
    names = {_module_key(name) for name in project_names}
    generic_directories = {"src", "lib", "source", "python", "tests", "test"}
    for record in records:
        if record.kind != "file" or not _is_python_source(record.relative_path):
            continue
        relative = _normal_relative_path(record.relative_path)
        if relative is None:
            continue
        parts = relative.split("/")
        stem = Path(parts[-1]).stem
        if stem != "__init__":
            names.add(_module_key(stem))
        if len(parts) > 1:
            for part in parts[:-1]:
                if part.casefold() not in generic_directories and part not in {".", ".."}:
                    names.add(_module_key(part))
        elif stem == "__init__":
            continue
    return names


def _parse_source(path: str, text: str, analysis: _Analysis) -> None:
    try:
        tree = ast.parse(text, filename=path, mode="exec")
    except (SyntaxError, ValueError, TypeError, MemoryError):
        analysis.source_errors.append((path, "Python source could not be parsed"))
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".", 1)[0]
                analysis.source_imports.append(_ImportUse(path, module, getattr(node, "lineno", None)))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            module = node.module.split(".", 1)[0]
            analysis.source_imports.append(_ImportUse(path, module, getattr(node, "lineno", None)))


def _documentation_mentions_pinned_requirements(
    documentation: Iterable[tuple[str, str]], requirement_path: str
) -> bool:
    basename = requirement_path.rsplit("/", 1)[-1].casefold()
    keyword = re.compile(
        r"(?:fully\s+)?pinn(?:ed|ing)|lock(?:file|\s*file)?|hash[- ]?pinn(?:ed|ing)|reproduc",
        re.IGNORECASE,
    )
    for _path, text in documentation:
        lowered = text.casefold()
        if basename not in lowered and "requirements file" not in lowered:
            continue
        if keyword.search(text):
            return True
    return False


def _record_sort_key(record: FileRecord) -> tuple[str, str]:
    path = str(record.relative_path)
    return path.casefold(), path


def _prepare_analysis(root: Path, inventory: InventoryResult) -> _Analysis:
    analysis = _Analysis()
    try:
        if not root.is_dir():
            analysis.parse_errors.append((None, "repository root is not a readable directory"))
            return analysis
    except OSError:
        analysis.parse_errors.append((None, "repository root could not be inspected"))
        return analysis
    records = sorted(
        (record for record in inventory.records if record.kind == "file"),
        key=_record_sort_key,
    )
    candidate_records = [
        record
        for record in records
        if (
            Path(str(record.relative_path)).name.casefold() == "pyproject.toml"
            or _is_requirements_path(str(record.relative_path))
            or _is_lock_path(str(record.relative_path))
            or _is_node_lock_path(str(record.relative_path))
            or _is_python_source(str(record.relative_path))
            or _is_documentation(str(record.relative_path))
        )
    ]
    if len(candidate_records) > MAX_INSPECTED_FILES:
        analysis.inspection_limited = True
        candidate_records = candidate_records[:MAX_INSPECTED_FILES]

    analysis.local_module_names = _local_modules(records, ())
    for record in candidate_records:
        relative = _normal_relative_path(record.relative_path)
        if relative is None:
            analysis.parse_errors.append((None, "inventory contained an invalid relative path"))
            continue
        basename = relative.rsplit("/", 1)[-1].casefold()
        should_read = (
            basename == "pyproject.toml"
            or _is_requirements_path(relative)
            or _is_python_source(relative)
            or _is_documentation(relative)
        )
        read_result: _ReadText | None = None
        if should_read:
            read_result = _read_bounded_text(root, record)
            if read_result.error is not None:
                if _is_documentation(relative):
                    analysis.documentation_errors.append((relative, read_result.error))
                else:
                    analysis.parse_errors.append((relative, read_result.error))
                continue
        if basename == "pyproject.toml":
            analysis.declaration_paths.append(relative)
            _parse_pyproject(relative, read_result.text or "", analysis)
        elif _is_requirements_path(relative):
            analysis.declaration_paths.append(relative)
            analysis.declaration_seen = True
            requirement = _parse_requirements(relative, read_result.text or "")
            analysis.requirement_files.append(requirement)
            analysis.declared_names.update(requirement.names)
            analysis.declaration_count += requirement.dependency_count
            if requirement.uncertain:
                analysis.parse_errors.append((relative, "requirements file contains unsupported or partial syntax"))
            if _is_lock_path(relative):
                analysis.lock_paths.append(relative)
        elif _is_lock_path(relative):
            analysis.lock_paths.append(relative)
        elif _is_node_lock_path(relative):
            analysis.unrelated_node_locks.append(relative)
        elif _is_python_source(relative):
            _parse_source(relative, read_result.text or "", analysis)
        elif _is_documentation(relative):
            analysis.documentation.append((relative, read_result.text or ""))

    # The project name is learned while parsing pyproject.  Add it after all
    # records have been classified so local import filtering is deterministic.
    analysis.local_module_names.update(_local_modules(records, analysis.project_names))
    analysis.source_imports = sorted(
        {
            item for item in analysis.source_imports
        },
        key=lambda item: (item.path.casefold(), item.path, item.line or 0, item.module.casefold(), item.module),
    )
    analysis.declaration_paths = sorted(set(analysis.declaration_paths), key=lambda value: (value.casefold(), value))
    analysis.lock_paths = sorted(set(analysis.lock_paths), key=lambda value: (value.casefold(), value))
    analysis.unrelated_node_locks = sorted(set(analysis.unrelated_node_locks), key=lambda value: (value.casefold(), value))
    analysis.requirement_files.sort(key=lambda item: (item.path.casefold(), item.path))
    return analysis


def _third_party_imports(analysis: _Analysis) -> tuple[_ImportUse, ...]:
    declared = set(analysis.declared_names)
    imports: dict[tuple[str, str, int | None], _ImportUse] = {}
    for item in analysis.source_imports:
        module_key = _module_key(item.module)
        if module_key in _STDLIB_MODULE_KEYS or module_key in analysis.local_module_names:
            continue
        imports[(item.path, item.module, item.line)] = item
    return tuple(
        sorted(
            imports.values(),
            key=lambda item: (item.path.casefold(), item.path, item.line or 0, item.module.casefold(), item.module),
        )
    )


def _distribution_matches_import(module: str, declared_names: set[str]) -> bool:
    module_name = _canonical_name(module)
    candidates = {module_name, module_name.replace("-", "_")}
    candidates.update(_canonical_name(alias) for alias in _IMPORT_DISTRIBUTION_ALIASES.get(module.casefold(), ()))
    return bool(candidates & declared_names)


def _applicability_for_python() -> Applicability:
    return Applicability(
        applicable=True,
        reason="A Python project candidate was detected from bounded inventory signals.",
        adapter="python",
    )


def _not_applicable(check_id: str, title: str, excluded: bool, detection: DetectionResult) -> Finding:
    if excluded:
        return _skipped(check_id, title)
    reason = (
        "No Python project candidate was detected; this Python dependency check does not apply "
        "to the detected repository type."
    )
    return Finding(
        check_id=check_id,
        severity="info",
        status="not_applicable",
        title=title,
        message=reason,
        evidence=(
            Evidence(
                kind="absence",
                path=None,
                detail="Bounded project detection contained no Python candidate for this check.",
            ),
        ),
        remediation="Use the dependency adapter for the detected ecosystem when one is available.",
        affected_path=None,
        category="dependencies",
        applicability=Applicability(applicable=False, reason=reason, adapter="python"),
        rule_version=RULE_VERSION,
        evidence_strength="absence",
    )


def _skipped(check_id: str, title: str) -> Finding:
    reason = "The configured policy excludes this dependency check; no rule logic was run."
    return Finding(
        check_id=check_id,
        severity="error",
        status="skipped",
        title=title,
        message=reason,
        evidence=(
            Evidence(
                kind="policy",
                path=None,
                detail="The check ID is present in excluded_checks; evaluation was intentionally skipped.",
            ),
        ),
        remediation="Remove this check from excluded_checks when dependency coverage is required.",
        affected_path=None,
        category="dependencies",
        applicability=Applicability(applicable=False, reason=reason, adapter="policy"),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _error_evidence(errors: Iterable[tuple[str | None, str]]) -> tuple[Evidence, ...]:
    unique = sorted(
        set(errors),
        key=lambda item: (str(item[0] or "").casefold(), str(item[0] or ""), item[1]),
    )
    if not unique:
        unique = [(None, "Bounded dependency evidence was incomplete.")]
    return tuple(
        Evidence(
            kind="error",
            path=path,
            detail=f"Dependency evidence was not verified: {detail}.",
        )
        for path, detail in unique[:16]
    )


def _declaration_finding(analysis: _Analysis, inventory: InventoryResult) -> Finding:
    imports = _third_party_imports(analysis)
    undeclared = tuple(
        item for item in imports if not _distribution_matches_import(item.module, analysis.declared_names)
    )
    coverage_errors = list(analysis.errors)
    if inventory.incomplete:
        coverage_errors.append((None, "inventory coverage is partial or contains unreadable entries"))
    if analysis.inspection_limited:
        coverage_errors.append((None, "the bounded dependency inspection file limit was reached"))
    if coverage_errors:
        evidence = _error_evidence(coverage_errors)
        return Finding(
            check_id="CS-DEPS-001",
            severity="warning",
            status="not_verified",
            title="Dependency declaration discovery",
            message="Dependency declarations or import evidence could not be evaluated completely within the bounded inventory.",
            evidence=evidence,
            remediation="Resolve malformed or unreadable dependency/source files and rerun with complete permitted inventory coverage.",
            affected_path=evidence[0].path,
            category="dependencies",
            applicability=_applicability_for_python(),
            rule_version=RULE_VERSION,
            evidence_strength="unverified",
        )

    if undeclared:
        evidence_items: list[Evidence] = []
        for item in undeclared[:16]:
            evidence_items.append(
                Evidence(
                    kind="file",
                    path=item.path,
                    line_start=item.line,
                    line_end=item.line,
                    detail=f"High-confidence top-level import '{item.module}' has no matching declared distribution.",
                )
            )
        evidence_items.append(
            Evidence(
                kind="absence",
                path=None,
                detail="The bounded dependency declarations did not contain a matching normalized package name.",
            )
        )
        return Finding(
            check_id="CS-DEPS-001",
            severity="error",
            status="failed",
            title="Dependency declaration discovery",
            message="A high-confidence third-party import is not represented by a discovered dependency declaration.",
            evidence=tuple(evidence_items),
            remediation="Declare each runtime or development dependency in pyproject.toml, a supported requirements file, or the documented package-manager metadata.",
            affected_path=undeclared[0].path,
            category="dependencies",
            applicability=_applicability_for_python(),
            rule_version=RULE_VERSION,
            evidence_strength="derived",
        )

    declaration_evidence = tuple(
        Evidence(
            kind="metadata",
            path=path,
            detail="A bounded dependency declaration file was discovered and statically inspected.",
        )
        for path in analysis.declaration_paths[:16]
    )
    if declaration_evidence:
        status_message = (
            "Discovered dependency declarations cover all high-confidence third-party imports, "
            "including the empty dependency case when no external imports were found."
        )
        strength = "direct"
        evidence = declaration_evidence
    else:
        status_message = "No high-confidence third-party imports were found; no external dependency declaration is required by the bounded evidence."
        strength = "absence"
        evidence = (
            Evidence(
                kind="absence",
                path=None,
                detail="The bounded Python source inventory contained no high-confidence third-party import requiring a declaration.",
            ),
        )
    return Finding(
        check_id="CS-DEPS-001",
        severity="info",
        status="passed",
        title="Dependency declaration discovery",
        message=status_message,
        evidence=evidence,
        remediation=[],
        affected_path=analysis.declaration_paths[0] if analysis.declaration_paths else None,
        category="dependencies",
        applicability=_applicability_for_python(),
        rule_version=RULE_VERSION,
        evidence_strength=strength,
    )


def _lock_finding(analysis: _Analysis, inventory: InventoryResult) -> Finding:
    imports = _third_party_imports(analysis)
    has_dependencies = bool(analysis.declared_names or imports)
    coverage_errors = list(analysis.errors)
    if inventory.incomplete:
        coverage_errors.append((None, "inventory coverage is partial or contains unreadable entries"))
    if analysis.inspection_limited:
        coverage_errors.append((None, "the bounded dependency inspection file limit was reached"))
    if coverage_errors:
        evidence = _error_evidence(coverage_errors)
        return Finding(
            check_id="CS-DEPS-002",
            severity="warning",
            status="not_verified",
            title="Applicable lockfile presence",
            message="Lockfile applicability could not be evaluated because bounded dependency evidence is incomplete.",
            evidence=evidence,
            remediation="Resolve malformed or unreadable dependency evidence and rerun the bounded check.",
            affected_path=evidence[0].path,
            category="dependencies",
            applicability=_applicability_for_python(),
            rule_version=RULE_VERSION,
            evidence_strength="unverified",
        )

    if not has_dependencies:
        evidence_items: list[Evidence] = [
            Evidence(
                kind="absence",
                path=None,
                detail="No declared or high-confidence third-party dependency was found; a Python lockfile is not applicable to this dependency-free workflow.",
            )
        ]
        evidence_items.extend(
            Evidence(
                kind="file",
                path=path,
                detail="A discovered Node lockfile was not accepted as Python lock evidence.",
            )
            for path in analysis.unrelated_node_locks[:8]
        )
        reason = "No dependency or package-manager signal requires a Python lockfile for the bounded dependency-free project."
        return Finding(
            check_id="CS-DEPS-002",
            severity="info",
            status="not_applicable",
            title="Applicable lockfile presence",
            message=reason,
            evidence=tuple(evidence_items),
            remediation="Add and document a Python lockfile when the project gains external dependencies or a lock-required workflow.",
            affected_path=None,
            category="dependencies",
            applicability=Applicability(applicable=False, reason=reason, adapter="python"),
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )

    if analysis.lock_paths:
        evidence = tuple(
            Evidence(
                kind="file",
                path=path,
                detail="A recognized Python lockfile was discovered within the bounded inventory.",
            )
            for path in analysis.lock_paths[:16]
        )
        return Finding(
            check_id="CS-DEPS-002",
            severity="info",
            status="passed",
            title="Applicable lockfile presence",
            message="A recognized Python lockfile matches the applicable dependency workflow.",
            evidence=evidence,
            remediation=[],
            affected_path=analysis.lock_paths[0],
            category="dependencies",
            applicability=_applicability_for_python(),
            rule_version=RULE_VERSION,
            evidence_strength="direct",
        )

    pinned_alternative: list[str] = []
    for requirement in analysis.requirement_files:
        suffix = Path(requirement.path).suffix.casefold()
        if suffix in {".txt"} and requirement.fully_pinned and _documentation_mentions_pinned_requirements(
            analysis.documentation, requirement.path
        ):
            pinned_alternative.append(requirement.path)
    if pinned_alternative:
        evidence_items = [
            Evidence(
                kind="file",
                path=path,
                detail="A fully pinned requirements file was discovered and bounded documentation identifies it as the reproducibility lock evidence.",
            )
            for path in sorted(pinned_alternative, key=lambda value: (value.casefold(), value))
        ]
        return Finding(
            check_id="CS-DEPS-002",
            severity="info",
            status="passed",
            title="Applicable lockfile presence",
            message="A clearly documented fully pinned requirements file provides the applicable Python lock evidence.",
            evidence=tuple(evidence_items),
            remediation=[],
            affected_path=pinned_alternative[0],
            category="dependencies",
            applicability=_applicability_for_python(),
            rule_version=RULE_VERSION,
            evidence_strength="derived",
        )

    evidence_items = [
        Evidence(
            kind="absence",
            path=None,
            detail="No recognized Python lockfile or clearly documented fully pinned requirements alternative was found for the declared dependency workflow.",
        )
    ]
    evidence_items.extend(
        Evidence(
            kind="file",
            path=path,
            detail="A discovered Node lockfile was not accepted as Python lock evidence.",
        )
        for path in analysis.unrelated_node_locks[:8]
    )
    return Finding(
        check_id="CS-DEPS-002",
        severity="error",
        status="failed",
        title="Applicable lockfile presence",
        message="The Python dependency workflow has declared dependencies but no applicable lockfile was discovered.",
        evidence=tuple(evidence_items),
        remediation="Generate and commit the lockfile used by the documented Python setup workflow, or clearly document a fully pinned requirements alternative.",
        affected_path=analysis.declaration_paths[0] if analysis.declaration_paths else None,
        category="dependencies",
        applicability=_applicability_for_python(),
        rule_version=RULE_VERSION,
        evidence_strength="absence",
    )


def evaluate_dependency_checks(
    root: Path | str,
    inventory: InventoryResult,
    detection: DetectionResult,
    *,
    excluded_checks: Iterable[str] = (),
) -> tuple[Finding, ...]:
    """Evaluate CS-DEPS-001 and CS-DEPS-002 from bounded discovery evidence.

    The returned tuple is always in check-ID order.  A non-Python or unknown
    detection produces explicit ``not_applicable`` findings; policy exclusions
    remain visible as ``skipped`` findings with policy evidence.
    """

    if isinstance(excluded_checks, str):
        excluded = {excluded_checks}
    else:
        excluded = {str(check_id) for check_id in excluded_checks}
    check_ids = ("CS-DEPS-001", "CS-DEPS-002")
    titles = {
        "CS-DEPS-001": "Dependency declaration discovery",
        "CS-DEPS-002": "Applicable lockfile presence",
    }
    results: list[Finding] = []
    python_candidate = False
    try:
        python_candidate = detection.primary in {"python", "mixed"}
        for candidate in detection.candidates:
            if candidate.id == "python" or "python" in candidate.members:
                python_candidate = True
    except (AttributeError, TypeError):
        python_candidate = False

    for check_id in check_ids:
        if check_id in excluded:
            results.append(_skipped(check_id, titles[check_id]))
        elif not python_candidate:
            results.append(_not_applicable(check_id, titles[check_id], False, detection))

    if len(results) == 2:
        return tuple(results)

    repository_root = Path(root)
    try:
        analysis = _prepare_analysis(repository_root, inventory)
        # Metadata errors/partial detection are a coverage limitation even when
        # a manually supplied DetectionResult does not expose a matching file.
        if detection.incomplete:
            analysis.parse_errors.append((None, "project detection metadata or inventory coverage is incomplete"))
    except (AttributeError, TypeError, OSError, RuntimeError):
        analysis = _Analysis()
        analysis.parse_errors.append((None, "dependency analysis inputs could not be inspected"))

    for check_id in check_ids:
        if check_id in excluded or not python_candidate:
            continue
        if check_id == "CS-DEPS-001":
            results.append(_declaration_finding(analysis, inventory))
        else:
            results.append(_lock_finding(analysis, inventory))

    # The first loop emitted any excluded/non-applicable entries in catalog
    # order; rebuild by ID to keep the public result deterministic for every
    # exclusion combination.
    by_id = {finding.check_id: finding for finding in results}
    return tuple(by_id[check_id] for check_id in check_ids if check_id in by_id)


__all__ = [
    "DEPENDENCY_READ_LIMIT",
    "MAX_INSPECTED_FILES",
    "RULE_VERSION",
    "evaluate_dependency_checks",
]
