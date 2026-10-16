"""Bounded portability, security, build, and path checks for M4.

This module is intentionally isolated from the audit integration layer.  The
repository is untrusted input: only regular files named by ``InventoryResult``
are considered, every text read has a hard byte bound, and no repository code
is imported or executed.  Findings contain categories and digests rather than
the untrusted values that caused an indicator.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..discovery import DetectionResult, FileRecord, InventoryResult
from ..findings import Applicability, Evidence, Finding


RULE_VERSION = "4"
QUALITY_READ_LIMIT = 64 * 1024
READ_LIMIT = QUALITY_READ_LIMIT
MAX_INSPECTED_FILES = 256
MAX_RECORDS = 4096
MAX_EVIDENCE = 32


_CHECK_IDS = ("CS-PORT-001", "CS-SEC-001", "CS-BUILD-001", "CS-PATH-001")
_TITLES = {
    "CS-PORT-001": "Developer-specific absolute paths",
    "CS-SEC-001": "Potential secret exposure indicator",
    "CS-BUILD-001": "Container build configuration discovery",
    "CS-PATH-001": "Repository-contained path validation",
}
_CATEGORIES = {
    "CS-PORT-001": "portability",
    "CS-SEC-001": "security",
    "CS-BUILD-001": "build",
    "CS-PATH-001": "portability",
}
_DEFAULT_SEVERITIES = {
    "CS-PORT-001": "warning",
    "CS-SEC-001": "error",
    "CS-BUILD-001": "info",
    "CS-PATH-001": "error",
}


_DOC_SUFFIXES = {".adoc", ".asciidoc", ".markdown", ".md", ".rst", ".txt"}
_SCRIPT_SUFFIXES = {
    ".bat",
    ".bash",
    ".c",
    ".cc",
    ".cmd",
    ".cpp",
    ".cxx",
    ".fish",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".mjs",
    ".php",
    ".pl",
    ".ps1",
    ".py",
    ".pyi",
    ".rb",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zsh",
}
_CONFIG_SUFFIXES = {
    ".cfg",
    ".conf",
    ".env",
    ".ini",
    ".json",
    ".properties",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
_BINARY_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".eot",
    ".exe",
    ".gif",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lockb",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".ttf",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
_CI_BASENAMES = {
    ".circleci/config.yml",
    ".circleci/config.yaml",
    ".gitlab-ci.yml",
    ".gitlab-ci.yaml",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
    "buildkite.yml",
    "buildkite.yaml",
    "circle.yml",
    "circle.yaml",
    "ci.yml",
    "ci.yaml",
    "jenkinsfile",
    "travis.yml",
    "travis.yaml",
}
_PACKAGING_BASENAMES = {
    "manifest.in",
    "package.json",
    "pipfile",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
}
_SECURITY_BASENAMES = {
    ".env",
    ".env.dev",
    ".env.development",
    ".env.local",
    ".env.prod",
    ".env.production",
    ".env.test",
    "credentials",
    "credentials.ini",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secret",
    "secret.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}
_CONTAINER_CLAIM_PATHS = {"readme", "docs", "documentation"}


_PRIVATE_KEY_MARKER = re.compile(
    r"-----BEGIN(?: [A-Z0-9][A-Z0-9 _-]*)? PRIVATE KEY-----",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<name>[A-Za-z][A-Za-z0-9_.-]*)"
    r"\s*(?:=|:)\s*(?P<value>[^\n]*)",
    re.IGNORECASE,
)
_CREDENTIAL_NAME = re.compile(
    r"(?:(?<![A-Za-z0-9])(?:token|password|passwd|secret|credential)(?![A-Za-z0-9])|"
    r"(?:api|private|access|client)[-_]?(?:key|secret|token))",
    re.IGNORECASE,
)
_CONTAINER_CLAIM = re.compile(
    r"(?:\b(?:docker|podman)\s+(?:build|run|compose|container|image|up|start)\b|"
    r"\bdocker[- ]compose\b|\bcompose\s+(?:build|up|run|start)\b|"
    r"\b(?:docker|container|podman)\s+(?:is\s+)?(?:required|needed|must)\b|"
    r"\bdockerfile\b[^\n]{0,48}\b(?:required|needed|must|build|run|use)\b|"
    r"\b(?:compose|container)\b[^\n]{0,48}\b(?:required|needed|must)\b|"
    r"\b(?:requires?|need|must|use|install|build|run|start|launch)\b[^\n]{0,48}"
    r"\b(?:docker|dockerfile|container|podman|compose)\b)",
    re.IGNORECASE,
)
_OPTIONAL_CONTAINER = re.compile(
    r"\b(?:docker|dockerfile|container|podman|compose)\b[^\n]{0,24}\b(?:optional|if you want|not required)\b|"
    r"\b(?:optional|not required)\b[^\n]{0,24}\b(?:docker|dockerfile|container|podman|compose)\b",
    re.IGNORECASE,
)
_DOCKER_INSTRUCTION = re.compile(r"^\s*(?P<instruction>FROM|COPY|ADD)\b(?P<body>.*)$", re.IGNORECASE)
_PATH_KEY = re.compile(
    r"(?<![A-Za-z0-9_])(?:path|file|filename|dir|directory|root|source|target|"
    r"include|includes|exclude|excludes|readme|license|entry(?:_point)?|main|"
    r"script|scripts|workdir|working[-_ ]dir|context|dockerfile|files|"
    r"package[-_]?data|data[-_]?files|package[-_]?dir|manifest)"
    r"(?![A-Za-z0-9_])\s*[\"']?\s*(?:=|:|=>)\s*",
    re.IGNORECASE,
)
_MARKDOWN_LINK = re.compile(r"\]\(\s*(?P<value>[^)\s]+)")
_MANIFEST_DIRECTIVE = re.compile(
    r"^\s*(?:include|recursive[- ]include|global[- ]include|graft|exclude|recursive[- ]exclude)\b\s+(?P<value>.+)$",
    re.IGNORECASE,
)
_QUOTED_VALUE = re.compile(r"(?:\"(?P<double>[^\"\n]{1,1024})\"|'(?P<single>[^'\n]{1,1024})'|`(?P<backtick>[^`\n]{1,1024})`)")
_PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"[A-Za-z]:[\\/][^\s\"'`,;\)\]\}]+|"
    r"\\\\[^\\/\s]+[\\/][^\s\"'`,;\)\]\}]+|"
    r"/(?:[A-Za-z0-9._${}~-]+/)*[A-Za-z0-9._${}~+-]+|"
    r"\.\.?[\\/][A-Za-z0-9_${}~.-]+|"
    r"(?:\.\.?[\\/])?[A-Za-z0-9_${}~.-]+(?:[\\/][A-Za-z0-9_${}~.-]+)+"
    r")"
)
_HOME_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_])(?:~(?:[\\/][^\s\"'`,;\)\]\}]+)?|"
    r"\$HOME|\$\{HOME\}|%USERPROFILE%|%HOMEDRIVE%%HOMEPATH%)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_WINDOWS_DRIVE_PATH = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s\"'`,;\)\]\}]+"
)
_WINDOWS_UNC_PATH = re.compile(r"(?<!\\)\\\\[^\s\"'`,;\)\]\}]+")
_UNIX_HOME_PATH = re.compile(
    r"(?<![A-Za-z0-9_])/(?:home|Users|root)(?:/[^\s\"'`,;\)\]\}]+)+",
    re.IGNORECASE,
)
_UNIX_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9_:])/(?:[A-Za-z0-9._${}~-]+/)+[A-Za-z0-9._${}~+-]+"
)
_COMMAND_CONTEXT = re.compile(
    r"(?:^|[\s$>`])(?:cd|cp|copy|mv|move|rm|del|source|python(?:\d+(?:\.\d+)?)?|"
    r"pip(?:3)?|poetry|uv|pdm|npm|yarn|pnpm|node|make|docker|podman|git|tar|zip|"
    r"export|install|build|setup|configure|run)\b|"
    r"^\s*(?:run|script|command|cmd|shell)\s*:",
    re.IGNORECASE,
)
_CLEAR_SETUP_COMMAND = re.compile(
    r"(?:^|[\s$>`])(?:cd|cp|copy|mv|move|rm|del|source|python(?:\d+(?:\.\d+)?)?|"
    r"pip(?:3)?|poetry|uv|pdm|npm|yarn|pnpm|node|make|docker|podman|git|"
    r"export|install)\b|"
    r"^\s*(?:run|script|command|cmd|shell)\s*:",
    re.IGNORECASE,
)
_REGEX_EXAMPLE = re.compile(
    r"\b(?:regex|regexp|regular expression|pattern)\b|re\.compile|"
    r"\(\?:|\(\?P<|\\[bBdDsSwW]|\\[dDsSwW]|"
    r"\[[A-Za-z0-9_-]+(?:[-,][A-Za-z0-9_-]+)+\][+*?]?|\.\*",
    re.IGNORECASE,
)
_NON_PATH_BARE_VALUES = {
    "bash",
    "cargo",
    "dotnet",
    "echo",
    "false",
    "go",
    "gradle",
    "make",
    "mvn",
    "node",
    "npm",
    "pdm",
    "poetry",
    "pnpm",
    "pytest",
    "python",
    "rollup",
    "sh",
    "true",
    "tsc",
    "uv",
    "vite",
    "webpack",
    "yarn",
}


@dataclass(frozen=True)
class _ReadText:
    path: str
    text: str | None
    digest: str | None
    error: str | None = None
    binary: bool = False


@dataclass(frozen=True)
class _Signal:
    path: str | None
    line: int | None
    indicator: str
    severity: str = "warning"
    digest: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class _Reference:
    raw: str
    normalized: str | None
    absolute: bool = False
    escape: bool = False
    parent: bool = False
    uncertain: bool = False
    external: bool = False
    system: bool = False


@dataclass
class _Analysis:
    root: Path | None
    active: frozenset[str]
    records: dict[str, Any] = field(default_factory=dict)
    file_paths: set[str] = field(default_factory=set)
    symlink_paths: set[str] = field(default_factory=set)
    external_symlink_paths: set[str] = field(default_factory=set)
    texts: dict[str, _ReadText] = field(default_factory=dict)
    errors: list[_Signal] = field(default_factory=list)
    port_signals: list[_Signal] = field(default_factory=list)
    security_signals: list[_Signal] = field(default_factory=list)
    build_claims: list[_Signal] = field(default_factory=list)
    build_config_paths: list[str] = field(default_factory=list)
    build_support_paths: list[_Signal] = field(default_factory=list)
    path_signals: list[_Signal] = field(default_factory=list)
    coverage_incomplete: bool = False


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _parts(path: str) -> tuple[str, ...]:
    return tuple(part.casefold() for part in path.split("/"))


def _suffix(path: str) -> str:
    return Path(_basename(path)).suffix.casefold()


def _normal_inventory_path(value: object) -> str | None:
    """Normalize an inventory path while rejecting absolute/traversal paths."""

    if not isinstance(value, str):
        return None
    raw = value.replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("//"):
        return None
    if len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha():
        return None
    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == ".." or ":" in part:
            return None
        if any(ord(character) < 32 or ord(character) == 127 for character in part):
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def _record_key(record: object) -> tuple[str, str, str, str]:
    try:
        path = str(getattr(record, "relative_path", ""))
    except Exception:
        path = ""
    try:
        kind = str(getattr(record, "kind", ""))
    except Exception:
        kind = ""
    try:
        size = repr(getattr(record, "size", None))
    except Exception:
        size = ""
    return path.casefold(), path, kind, size


def _is_docs_path(path: str) -> bool:
    basename = _basename(path).casefold()
    return basename.startswith("readme") or (
        _suffix(path) in _DOC_SUFFIXES
        and any(part in _CONTAINER_CLAIM_PATHS for part in _parts(path)[:-1])
    )


def _is_ci_path(path: str) -> bool:
    lower = path.casefold()
    basename = _basename(lower)
    if basename in _CI_BASENAMES:
        return True
    parts = _parts(path)
    if len(parts) >= 3 and parts[-3:-1] == (".github", "workflows"):
        return True
    if len(parts) >= 2 and parts[-2:] in {(".circleci", "config.yml"), (".circleci", "config.yaml")}:
        return True
    if ".buildkite" in parts and basename.endswith((".yml", ".yaml")):
        return True
    return ".gitlab" in parts and basename.endswith((".yml", ".yaml"))


def _is_dockerfile(path: str) -> bool:
    basename = _basename(path).casefold()
    return basename == "dockerfile" or basename.startswith("dockerfile.")


def _is_compose_file(path: str) -> bool:
    basename = _basename(path).casefold()
    return (
        basename in {"compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"}
        or ("compose" in basename and basename.endswith((".yml", ".yaml")))
    )


def _is_dockerignore(path: str) -> bool:
    return _basename(path).casefold() == ".dockerignore"


def _is_packaging_path(path: str) -> bool:
    return _basename(path).casefold() in _PACKAGING_BASENAMES


def _is_textual_path(path: str) -> bool:
    basename = _basename(path).casefold()
    return (
        _suffix(path) in _DOC_SUFFIXES | _SCRIPT_SUFFIXES | _CONFIG_SUFFIXES
        or basename in {
            ".dockerignore",
            ".env.example",
            ".env.sample",
            ".env.template",
            "dockerfile",
            "jenkinsfile",
            "makefile",
            "gnumakefile",
            "readme",
            "readme.md",
        }
        or _is_ci_path(path)
        or _is_packaging_path(path)
        or basename in _SECURITY_BASENAMES
        or _suffix(path) in {".crt", ".key", ".pem"}
    )


def _is_security_path(path: str) -> bool:
    return _is_textual_path(path) and _suffix(path) not in _BINARY_SUFFIXES


def _is_port_path(path: str) -> bool:
    return _is_textual_path(path) and _suffix(path) not in _BINARY_SUFFIXES


def _is_path_path(path: str) -> bool:
    return _is_textual_path(path) and _suffix(path) not in _BINARY_SUFFIXES


def _is_example_line(path: str, line: str) -> bool:
    basename = _basename(path).casefold()
    safe_template = basename in {".env.example", ".env.sample", ".env.template"} or (
        basename.startswith(".env.")
        and any(token in basename for token in (".example", ".sample", ".template"))
    )
    if not _is_docs_path(path) and not safe_template:
        return False
    if safe_template or any(part in {"example", "examples", "sample", "samples", "template", "templates"} for part in _parts(path)[:-1]):
        return True
    lowered = line.casefold()
    if re.search(r"\b(?:for\s+)?example\b|\be\.g\.\b|\bsample\b|\bplaceholder\b", lowered):
        return True
    if re.search(r"(?:your|the)[-_ ]?(?:user|username|name|home)|<[^>]{1,64}>", lowered):
        return True
    return False


def _is_regex_example(line: str) -> bool:
    return bool(_REGEX_EXAMPLE.search(line))


def _strip_urls(line: str) -> str:
    return re.sub(r"\b(?:https?|ftp)://[^\s)\]}>]+", " ", line, flags=re.IGNORECASE)


def _is_system_path(value: str) -> bool:
    normalized = value.replace("\\", "/").rstrip("/").casefold()
    if normalized in {"/tmp", "/etc/hosts", "/dev/null"}:
        return True
    if normalized.startswith((
        "/tmp/",
        "/usr/",
        "/bin/",
        "/sbin/",
        "/lib/",
        "/lib64/",
        "/etc/",
        "/var/",
        "/dev/",
        "/proc/",
        "/sys/",
        "/private/tmp/",
        "/opt/homebrew/",
    )):
        return True
    if re.match(r"^[a-z]:/", normalized):
        rest = normalized[3:]
        if rest.startswith(("windows/", "program files/", "program files (x86)/", "programdata/")):
            return True
        if rest.startswith(("python", "msys", "mingw", "git/")):
            return True
    return False


def _looks_placeholder_path(value: str) -> bool:
    normalized = value.replace("\\", "/").casefold()
    return bool(
        re.search(
            r"/(?:your[-_ ]?(?:user|username|name|home)|username|user|example|sample)(?:/|$)",
            normalized,
        )
        or re.search(r"[\\/]<(?:user|username|name|home)>[\\/]", normalized)
    )


def _clear_command(path: str, line: str) -> bool:
    if _is_dockerfile(path) and re.match(r"^\s*(?:RUN|CMD|ENTRYPOINT|COPY|ADD)\b", line, re.IGNORECASE):
        return True
    return bool(_CLEAR_SETUP_COMMAND.search(line))


def _add_signal(items: list[_Signal], signal: _Signal) -> None:
    if signal not in items:
        items.append(signal)


def _signal_key(signal: _Signal) -> tuple[str, str, int, str, str, str]:
    path = signal.path or ""
    reference = signal.reference or ""
    return (
        path.casefold(),
        path,
        signal.line or 0,
        signal.indicator,
        signal.severity,
        reference,
    )


def _severity_first(signal: _Signal) -> tuple[int, str, str, int, str]:
    rank = {"blocking": 0, "error": 1, "warning": 2, "info": 3}
    return (
        rank.get(signal.severity, 9),
        (signal.path or "").casefold(),
        signal.indicator,
        signal.line or 0,
        signal.path or "",
    )


def _mark_incomplete(
    analysis: _Analysis,
    indicator: str,
    *,
    path: str | None = None,
    line: int | None = None,
    digest: str | None = None,
) -> None:
    analysis.coverage_incomplete = True
    safe_path = path if _normal_inventory_path(path) is not None else None
    _add_signal(
        analysis.errors,
        _Signal(safe_path, line, indicator, "warning", digest),
    )


def _safe_record_path(root: Path, relative: str, record: object) -> tuple[Path | None, str | None]:
    if getattr(record, "kind", None) != "file":
        return None, "symlink-entry-not-read"
    if bool(getattr(record, "external_symlink", False)):
        return None, "external-symlink-not-read"
    if not bool(getattr(record, "readable", False)):
        return None, "unreadable-file"
    try:
        resolved_root = root.resolve(strict=False)
    except (OSError, RuntimeError):
        return None, "root-could-not-be-resolved"
    candidate = resolved_root.joinpath(*relative.split("/"))
    cursor = resolved_root
    for component in relative.split("/"):
        cursor = cursor / component
        try:
            if cursor.is_symlink():
                return None, "symlink-entry-not-read"
        except OSError:
            return None, "entry-could-not-be-classified"
    try:
        resolved_candidate = candidate.resolve(strict=False)
        common = os.path.commonpath(
            (
                os.path.normcase(os.fspath(resolved_root)),
                os.path.normcase(os.fspath(resolved_candidate)),
            )
        )
    except (OSError, RuntimeError, ValueError):
        return None, "entry-escaped-repository"
    if common != os.path.normcase(os.fspath(resolved_root)):
        return None, "entry-escaped-repository"
    return candidate, None


def _read_bounded_text(root: Path, relative: str, record: object) -> _ReadText:
    if getattr(record, "kind", None) != "file":
        return _ReadText(relative, None, None, "symlink-entry-not-read")
    if not bool(getattr(record, "readable", False)):
        return _ReadText(relative, None, None, "unreadable-file")
    size = getattr(record, "size", None)
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
        return _ReadText(relative, None, None, "invalid-file-size")
    if size is not None and size > QUALITY_READ_LIMIT:
        return _ReadText(relative, None, None, "file-exceeds-text-limit")
    candidate, boundary_error = _safe_record_path(root, relative, record)
    if candidate is None:
        return _ReadText(relative, None, None, boundary_error or "entry-not-contained")
    try:
        with candidate.open("rb") as handle:
            data = handle.read(QUALITY_READ_LIMIT + 1)
    except (OSError, PermissionError):
        return _ReadText(relative, None, None, "file-could-not-be-read")
    if len(data) > QUALITY_READ_LIMIT:
        return _ReadText(relative, None, None, "file-exceeds-text-limit")
    digest = hashlib.sha256(data).hexdigest()
    if b"\x00" in data:
        return _ReadText(relative, None, digest, "binary-content-skipped", binary=True)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _ReadText(relative, None, digest, "binary-content-skipped", binary=True)
    return _ReadText(relative, text, digest)


def _reference(raw_value: str) -> _Reference:
    raw = raw_value.strip().strip("\"'`<>")
    raw = raw.rstrip(",;)]}")
    if not raw:
        return _Reference(raw, None)
    if re.match(r"^(?:https?|ftp|git|ssh):", raw, re.IGNORECASE):
        return _Reference(raw, None, external=True)
    if raw in {".", "./", ".\\"}:
        return _Reference(raw, ".")
    normalized = raw.replace("\\", "/")
    if normalized.startswith(("~", "$HOME", "${HOME}", "%USERPROFILE%", "%HOMEDRIVE%")):
        return _Reference(raw, None, absolute=True, uncertain=True, system=False)
    if normalized.startswith("/") or normalized.startswith("//") or (
        len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha()
    ):
        return _Reference(raw, normalized, absolute=True, system=_is_system_path(normalized))
    if "${" in normalized or re.search(r"\$[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*%", normalized):
        return _Reference(raw, None, uncertain=True)
    parts: list[str] = []
    had_parent = False
    escaped = False
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            had_parent = True
            if not parts:
                escaped = True
            else:
                parts.pop()
            continue
        parts.append(part)
    return _Reference(
        raw,
        "/".join(parts) if parts else ".",
        escape=escaped,
        parent=had_parent,
    )


def _reference_exists(reference: str, paths: set[str]) -> bool:
    if reference in {"", "."}:
        return True
    if any(character in reference for character in "*?["):
        return any(fnmatch.fnmatchcase(path, reference) for path in paths)
    return reference in paths or any(path.startswith(reference.rstrip("/") + "/") for path in paths)


def _path_token_values(line: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _PATH_TOKEN.finditer(line):
        value = match.group(0).strip()
        value = value.rstrip(".,;:)]}>")
        if value:
            values.append(value)
    return tuple(values)


def _quoted_values(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for match in _QUOTED_VALUE.finditer(value):
        selected = match.group("double") or match.group("single") or match.group("backtick")
        if selected is not None:
            result.append(selected)
    if result:
        return tuple(result)
    token = value.split("#", 1)[0].strip().rstrip(",")
    if token:
        return (token.split()[0],)
    return ()


def _inspect_reference(
    analysis: _Analysis,
    raw: str,
    *,
    path: str,
    line: int | None,
    digest: str | None,
    required: bool,
    source: str,
) -> None:
    reference = _reference(raw)
    if reference.external or reference.normalized is None and not reference.absolute:
        if reference.uncertain:
            _add_signal(
                analysis.path_signals,
                _Signal(path, line, "uncertain-path-reference", "warning", digest, source),
            )
        return
    if reference.absolute:
        if reference.system or _looks_placeholder_path(reference.raw):
            return
        _add_signal(
            analysis.path_signals,
            _Signal(
                path,
                line,
                "absolute-developer-path",
                "error" if required else "warning",
                digest,
                source,
            ),
        )
        return
    if reference.escape:
        _add_signal(
            analysis.path_signals,
            _Signal(
                path,
                line,
                "lexical-parent-escape",
                "error" if required else "warning",
                digest,
                source,
            ),
        )
        return
    if reference.uncertain:
        _add_signal(
            analysis.path_signals,
            _Signal(path, line, "uncertain-path-reference", "warning", digest, source),
        )
        return
    normalized = reference.normalized or "."
    if not _reference_exists(normalized, analysis.file_paths):
        _add_signal(
            analysis.path_signals,
            _Signal(
                path,
                line,
                "missing-local-resource" if required else "uncertain-missing-resource",
                "error" if required else "warning",
                digest,
                source,
            ),
        )
    else:
        _add_signal(
            analysis.path_signals,
            _Signal(path, line, "contained-present-reference", "info", digest, source),
        )


def _scan_portability(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    for line_number, original_line in enumerate(text.splitlines(), start=1):
        if _is_example_line(path, original_line) or _is_regex_example(original_line):
            continue
        if re.search(r"^\s*WORKDIR\b", original_line, re.IGNORECASE):
            continue
        line = _strip_urls(original_line)
        if _is_dockerfile(path):
            docker_match = _DOCKER_INSTRUCTION.match(original_line)
            if docker_match is not None and docker_match.group("instruction").casefold() in {"copy", "add"}:
                # The final COPY/ADD operand is a container destination, not
                # a host path and must not create a host-portability finding.
                line = " ".join(_docker_sources(docker_match.group("body")))
        matches: list[tuple[int, str, str]] = []
        for pattern, category in (
            (_HOME_REFERENCE, "host-home-path"),
            (_WINDOWS_UNC_PATH, "windows-unc-path"),
            (_WINDOWS_DRIVE_PATH, "windows-drive-path"),
            (_UNIX_HOME_PATH, "unix-home-path"),
            (_UNIX_ABSOLUTE_PATH, "unix-absolute-path"),
        ):
            for match in pattern.finditer(line):
                value = match.group(0)
                if _is_system_path(value) or _looks_placeholder_path(value):
                    continue
                matches.append((match.start(), category, value))
        priorities = {
            "host-home-path": 0,
            "unix-home-path": 0,
            "windows-drive-path": 0,
            "windows-unc-path": 0,
            "unix-absolute-path": 1,
        }
        selected_starts: set[int] = set()
        for _start, category, value in sorted(
            matches,
            key=lambda item: (item[0], priorities.get(item[1], 9), item[1], item[2]),
        ):
            if _start in selected_starts:
                continue
            selected_starts.add(_start)
            _add_signal(
                analysis.port_signals,
                _Signal(
                    path,
                    line_number,
                    category,
                    "error" if _clear_command(path, original_line) else "warning",
                    digest,
                ),
            )


def _strip_source_comment(value: str) -> str:
    value = value.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if " //" in value:
        value = value.split(" //", 1)[0].rstrip()
    return value.strip().strip(",;")


def _placeholder_secret(value: str) -> bool:
    candidate = _strip_source_comment(value).strip("\"'").strip()
    if not candidate:
        return True
    lowered = candidate.casefold()
    if lowered in {
        "...",
        "changeme",
        "change-me",
        "dummy",
        "example",
        "false",
        "none",
        "null",
        "password",
        "placeholder",
        "replace-me",
        "replace_me",
        "secret",
        "test",
        "todo",
        "token",
        "true",
        "value",
        "your-value",
        "your_value",
    }:
        return True
    if candidate.startswith(("<", "${", "{{", "$", "%")) or candidate.endswith((">", "}", "}}")):
        return True
    if lowered.startswith(("change-", "example-", "placeholder-", "replace-", "your-", "your_", "enter-", "test-")):
        return True
    if re.search(r"\b(?:os\.(?:getenv|environ)|process\.env|secrets?\.|random\.|uuid\.|getenv\s*\(|env\[)", lowered):
        return True
    return False


def _credential_strength(value: str) -> str | None:
    candidate = _strip_source_comment(value).strip().strip("\"'").strip()
    if _placeholder_secret(candidate):
        return None
    if len(candidate) >= 6:
        return "high"
    return "weak"


def _scan_security(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("#", ";", "//", "<!--", "*")):
            continue
        if _PRIVATE_KEY_MARKER.search(line):
            _add_signal(
                analysis.security_signals,
                _Signal(path, line_number, "private-key-marker", "blocking", digest),
            )
        assignment = _ASSIGNMENT.search(line)
        if assignment is None:
            continue
        if _CREDENTIAL_NAME.search(assignment.group("name")) is None:
            continue
        value = assignment.group("value")
        if _is_example_line(path, line) or _placeholder_secret(value):
            continue
        strength = _credential_strength(value)
        if strength is None:
            continue
        indicator = (
            "high-confidence-credential-assignment"
            if strength == "high"
            else "credential-assignment-indicator"
        )
        _add_signal(
            analysis.security_signals,
            _Signal(
                path,
                line_number,
                indicator,
                "error" if strength == "high" else "warning",
                digest,
            ),
        )


def _docker_sources(body: str) -> tuple[str, ...]:
    text = re.split(r"\s+#", body, maxsplit=1)[0].strip()
    flags: list[str] = []
    while text.startswith("--"):
        try:
            parts = shlex.split(text, posix=True)
        except ValueError:
            return ()
        if not parts:
            return ()
        flags.append(parts[0])
        text = text[len(parts[0]) :].lstrip()
    if any(flag.casefold().startswith("--from=") or flag.casefold() == "--from" for flag in flags):
        return ()
    if text.startswith("["):
        try:
            values = json.loads(text)
        except (json.JSONDecodeError, ValueError, TypeError):
            return ()
        if not isinstance(values, list) or len(values) < 2 or not all(isinstance(item, str) for item in values):
            return ()
        return tuple(values[:-1])
    try:
        parts = tuple(shlex.split(text, posix=True))
    except ValueError:
        return ()
    return parts[:-1] if len(parts) >= 2 else ()


def _scan_build_claims(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _OPTIONAL_CONTAINER.search(line):
            continue
        if _CONTAINER_CLAIM.search(line):
            _add_signal(
                analysis.build_claims,
                _Signal(path, line_number, "container-workflow-claim", "warning", digest),
            )


def _scan_dockerfile(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _DOCKER_INSTRUCTION.match(line)
        if match is None:
            continue
        instruction = match.group("instruction").casefold()
        if "CS-BUILD-001" in analysis.active:
            _add_signal(
                analysis.build_support_paths,
                _Signal(path, line_number, f"docker-{instruction}-metadata", "info", digest),
            )
        if "CS-PATH-001" not in analysis.active or instruction not in {"copy", "add"}:
            continue
        for source in _docker_sources(match.group("body")):
            _inspect_reference(
                analysis,
                source,
                path=path,
                line=line_number,
                digest=digest,
                required=True,
                source="docker-source",
            )


def _scan_compose_paths(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    if "CS-PATH-001" not in analysis.active:
        return
    for line_number, line in enumerate(text.splitlines(), start=1):
        # Bind mounts and compose build contexts have the local side before a
        # colon.  Named volumes are intentionally left as uncertain metadata.
        for match in re.finditer(
            r"(?<![A-Za-z0-9_])(?P<source>(?:\.\.?[\\/]|[A-Za-z]:[\\/]|/|~|\$)[^\s:,]+)\s*:",
            line,
        ):
            source = match.group("source")
            _inspect_reference(
                analysis,
                source,
                path=path,
                line=line_number,
                digest=digest,
                required=True,
                source="compose-source",
            )


def _scan_generic_paths(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    if "CS-PATH-001" not in analysis.active:
        return
    if _is_dockerfile(path):
        return
    pending_path_values = False
    for line_number, original_line in enumerate(text.splitlines(), start=1):
        line_was_pending = pending_path_values
        if _is_example_line(path, original_line) or _is_regex_example(original_line):
            continue
        line = _strip_urls(original_line)
        key_match = _PATH_KEY.search(line)
        command_context = bool(_COMMAND_CONTEXT.search(line)) or bool(
            re.match(r"^\s*\.\.?[\\/]", line)
        )
        values: list[str] = []
        if key_match is not None:
            key_tail = line[key_match.end() :]
            # A package-manager ``scripts`` object contains commands, not
            # local path declarations.  A scalar script/path assignment is
            # still inspected below.
            script_object = "script" in key_match.group(0).casefold() and key_tail.lstrip().startswith("{")
            if not script_object:
                values.extend(_quoted_values(key_tail))
                pending_path_values = key_tail.lstrip().startswith(("[", "{")) and not bool(re.search(r"[\]}]", key_tail))
            else:
                pending_path_values = False
        elif pending_path_values:
            values.extend(_quoted_values(line))
            if re.search(r"[\]}]", line):
                pending_path_values = False
        build_context = re.match(r"^\s*build\s*[:=]\s*(?P<value>.+)$", line, re.IGNORECASE)
        if build_context is not None:
            values.extend(_quoted_values(build_context.group("value")))
        if _is_docs_path(path):
            values.extend(match.group("value") for match in _MARKDOWN_LINK.finditer(line))
        manifest_match = _MANIFEST_DIRECTIVE.match(line) if _basename(path).casefold() == "manifest.in" else None
        if manifest_match is not None:
            values.extend(manifest_match.group("value").split())
        tokens = list(_path_token_values(line))
        if key_match is not None or command_context or manifest_match is not None:
            values.extend(tokens)
        elif any(token.startswith(("../", "..\\", "/", "\\\\")) for token in tokens):
            values.extend(tokens)
        if _is_docs_path(path) and command_context:
            values.extend(tokens)
        seen: set[str] = set()
        for value in values:
            value = value.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            # A path-like key is a required local reference in configuration or
            # packaging metadata.  Documentation and ordinary shell text are
            # treated as uncertain unless they are a clear setup command.
            required = bool(key_match is not None and not _is_docs_path(path))
            required = required or bool(line_was_pending and not _is_docs_path(path))
            required = required or bool(command_context and not _is_docs_path(path))
            required = required or bool(manifest_match is not None)
            if _is_docs_path(path) and _clear_command(path, original_line):
                required = True
            if not _looks_path_like(
                value,
                key_match is not None or command_context or manifest_match is not None or line_was_pending or _is_docs_path(path),
            ):
                continue
            _inspect_reference(
                analysis,
                value,
                path=path,
                line=line_number,
                digest=digest,
                required=required,
                source="bounded-path-reference",
            )


def _looks_path_like(value: str, contextual: bool) -> bool:
    candidate = value.strip().strip("\"'`")
    if not candidate or candidate in {".", "./", "-"}:
        return True
    if re.match(r"^(?:https?|ftp|git|ssh):", candidate, re.IGNORECASE):
        return False
    if "/" in candidate or "\\" in candidate or candidate.startswith((".", "~", "$", "%")):
        return True
    if len(candidate) >= 2 and candidate[1] == ":":
        return True
    if candidate.casefold() in _NON_PATH_BARE_VALUES:
        return False
    return contextual and bool(re.fullmatch(r"[A-Za-z0-9_${}*?.~-]+", candidate))


def _build_config_kind(path: str) -> str | None:
    if _is_dockerfile(path):
        return "dockerfile"
    if _is_compose_file(path):
        return "compose-file"
    return None


def _prepare_analysis(
    root: Path | str,
    inventory: InventoryResult,
    detection: DetectionResult,
    active: frozenset[str],
) -> _Analysis:
    try:
        root_path = Path(root)
    except (TypeError, ValueError, OSError):
        analysis = _Analysis(None, active)
        _mark_incomplete(analysis, "invalid-root")
        return analysis
    analysis = _Analysis(root_path, active)
    try:
        if not root_path.is_dir():
            _mark_incomplete(analysis, "root-not-directory")
    except OSError:
        _mark_incomplete(analysis, "root-not-readable")

    try:
        if bool(getattr(inventory, "incomplete")):
            _mark_incomplete(analysis, "inventory-coverage-partial")
    except (AttributeError, TypeError, OSError, RuntimeError):
        _mark_incomplete(analysis, "inventory-completeness-unavailable")
    try:
        if bool(getattr(detection, "incomplete")):
            _mark_incomplete(analysis, "detection-coverage-partial")
    except (AttributeError, TypeError, OSError, RuntimeError):
        _mark_incomplete(analysis, "detection-completeness-unavailable")

    try:
        raw_records = getattr(inventory, "records")
        iterator = iter(raw_records)
    except (AttributeError, TypeError):
        _mark_incomplete(analysis, "inventory-records-unavailable")
        return analysis

    records: list[object] = []
    for index, record in enumerate(iterator):
        if index >= MAX_RECORDS:
            _mark_incomplete(analysis, "inventory-record-limit")
            break
        records.append(record)
    records.sort(key=_record_key)
    for record in records:
        try:
            relative = _normal_inventory_path(getattr(record, "relative_path"))
            kind = getattr(record, "kind")
        except (AttributeError, TypeError, ValueError):
            _mark_incomplete(analysis, "malformed-inventory-record")
            continue
        if relative is None:
            _mark_incomplete(analysis, "invalid-inventory-path")
            continue
        if kind not in {"file", "symlink"}:
            _mark_incomplete(analysis, "unsupported-inventory-entry", path=relative)
            continue
        if relative in analysis.records:
            _mark_incomplete(analysis, "duplicate-inventory-path", path=relative)
            continue
        size = getattr(record, "size", None)
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
            _mark_incomplete(analysis, "invalid-inventory-size", path=relative)
        readable = getattr(record, "readable", False)
        if not isinstance(readable, bool):
            _mark_incomplete(analysis, "invalid-inventory-readability", path=relative)
        analysis.records[relative] = record
        if kind == "file":
            analysis.file_paths.add(relative)
        else:
            analysis.symlink_paths.add(relative)
            if bool(getattr(record, "external_symlink", False)):
                analysis.external_symlink_paths.add(relative)

    try:
        external_entries = getattr(inventory, "external_symlinks")
        external_iterator = iter(external_entries)
    except (AttributeError, TypeError):
        _mark_incomplete(analysis, "external-symlink-evidence-unavailable")
        external_iterator = iter(())
    for index, item in enumerate(external_iterator):
        if index >= MAX_EVIDENCE:
            _mark_incomplete(analysis, "external-symlink-evidence-limit")
            break
        if not isinstance(item, Mapping):
            _mark_incomplete(analysis, "malformed-external-symlink-evidence")
            continue
        relative = _normal_inventory_path(item.get("path"))
        if relative is None:
            _mark_incomplete(analysis, "invalid-external-symlink-path")
            continue
        analysis.external_symlink_paths.add(relative)

    for relative, record in sorted(analysis.records.items(), key=lambda item: (item[0].casefold(), item[0])):
        if _build_config_kind(relative) is not None and getattr(record, "kind", None) == "file":
            analysis.build_config_paths.append(relative)
        if _is_dockerignore(relative) and getattr(record, "kind", None) == "file":
            analysis.build_support_paths.append(
                _Signal(relative, None, "dockerignore-metadata", "info")  # type: ignore[arg-type]
            )

    candidate_paths: list[str] = []
    for relative, record in sorted(analysis.records.items(), key=lambda item: (item[0].casefold(), item[0])):
        if getattr(record, "kind", None) != "file":
            if relative in analysis.external_symlink_paths and _build_config_kind(relative) is not None:
                _mark_incomplete(analysis, "symlink-entry-not-read", path=relative)
            continue
        relevant = (
            ("CS-PORT-001" in active and _is_port_path(relative))
            or ("CS-SEC-001" in active and _is_security_path(relative))
            or ("CS-BUILD-001" in active and (_is_docs_path(relative) or _build_config_kind(relative) is not None))
            or ("CS-PATH-001" in active and _is_path_path(relative))
        )
        if relevant:
            candidate_paths.append(relative)
    if len(candidate_paths) > MAX_INSPECTED_FILES:
        _mark_incomplete(analysis, "quality-file-limit")
        candidate_paths = candidate_paths[:MAX_INSPECTED_FILES]

    if analysis.root is not None:
        for relative in candidate_paths:
            record = analysis.records[relative]
            result = _read_bounded_text(analysis.root, relative, record)
            analysis.texts[relative] = result
            if result.error is not None:
                # Binary files are intentionally not content-scanned.  A text
                # configuration or Dockerfile that turns out binary still
                # leaves the relevant check incomplete.
                if result.error != "binary-content-skipped" or _is_textual_path(relative):
                    _mark_incomplete(analysis, result.error, path=relative, digest=result.digest)

    for relative, result in sorted(analysis.texts.items(), key=lambda item: (item[0].casefold(), item[0])):
        if result.text is None:
            continue
        text = result.text
        digest = result.digest
        if "CS-PORT-001" in active and _is_port_path(relative):
            _scan_portability(analysis, relative, text, digest)
        if "CS-SEC-001" in active and _is_security_path(relative):
            _scan_security(analysis, relative, text, digest)
        if "CS-BUILD-001" in active:
            if _is_docs_path(relative):
                _scan_build_claims(analysis, relative, text, digest)
            if _is_dockerfile(relative):
                _scan_dockerfile(analysis, relative, text, digest)
        if "CS-PATH-001" in active:
            if _is_dockerfile(relative):
                _scan_dockerfile(analysis, relative, text, digest)
            elif _is_compose_file(relative):
                _scan_compose_paths(analysis, relative, text, digest)
            if _is_path_path(relative):
                _scan_generic_paths(analysis, relative, text, digest)

    if "CS-PATH-001" in active:
        for relative in sorted(analysis.external_symlink_paths, key=lambda value: (value.casefold(), value)):
            _add_signal(
                analysis.path_signals,
                _Signal(relative, None, "external-symlink", "warning"),
            )

    for collection in (
        analysis.errors,
        analysis.port_signals,
        analysis.security_signals,
        analysis.build_claims,
        analysis.build_support_paths,
        analysis.path_signals,
    ):
        collection.sort(key=_signal_key)
    analysis.build_config_paths.sort(key=lambda value: (value.casefold(), value))
    return analysis


def _evidence_for_signal(signal: _Signal, *, kind: str = "file") -> Evidence:
    detail = f"indicator={signal.indicator}; redacted=true; raw_value=omitted"
    return Evidence(
        kind=kind,
        path=signal.path,
        line_start=signal.line,
        line_end=signal.line,
        detail=detail,
        digest=signal.digest,
    )


def _coverage_evidence(analysis: _Analysis) -> tuple[Evidence, ...]:
    signals = analysis.errors[:MAX_EVIDENCE]
    if not signals:
        signals = [_Signal(None, None, "coverage-incomplete", "warning")]
    return tuple(_evidence_for_signal(signal, kind="error") for signal in signals)


def _applicability(*, applicable: bool = True, reason: str, adapter: str = "generic") -> Applicability:
    return Applicability(applicable=applicable, reason=reason, adapter=adapter)


def _policy_skipped(check_id: str) -> Finding:
    reason = "The configured policy excludes this check; no rule logic was run."
    return Finding(
        check_id=check_id,
        severity=_DEFAULT_SEVERITIES[check_id],
        status="skipped",
        title=_TITLES[check_id],
        message=reason,
        evidence=(
            Evidence(
                kind="policy",
                path=None,
                detail="The check ID is present in excluded_checks; evaluation was intentionally skipped.",
            ),
        ),
        remediation=f"Remove {check_id} from excluded_checks when this coverage is required.",
        category=_CATEGORIES[check_id],
        applicability=_applicability(
            applicable=False,
            reason=reason,
            adapter="policy",
        ),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _not_verified(check_id: str, analysis: _Analysis, message: str) -> Finding:
    evidence = _coverage_evidence(analysis)
    return Finding(
        check_id=check_id,
        severity="warning",
        status="not_verified",
        title=_TITLES[check_id],
        message=message,
        evidence=evidence,
        remediation="Resolve partial, unreadable, malformed, symlinked, or oversized bounded evidence and rerun the check.",
        affected_path=evidence[0].path,
        category=_CATEGORIES[check_id],
        applicability=_applicability(
            reason="The bounded inventory indicates that this quality check may apply.",
        ),
        rule_version=RULE_VERSION,
        evidence_strength="unverified",
    )


def _portability_finding(analysis: _Analysis) -> Finding:
    check_id = "CS-PORT-001"
    if analysis.coverage_incomplete:
        return _not_verified(
            check_id,
            analysis,
            "Portability evidence could not be evaluated completely within the bounded inventory.",
        )
    if not analysis.port_signals:
        return Finding(
            check_id=check_id,
            severity="info",
            status="passed",
            title=_TITLES[check_id],
            message="No suspicious developer-specific absolute or host-home path was found in bounded text evidence.",
            evidence=(
                Evidence(
                    kind="absence",
                    path=None,
                    detail="No portability path indicator was detected; values were not copied into evidence.",
                ),
            ),
            remediation=(),
            category=_CATEGORIES[check_id],
            applicability=_applicability(
                reason="Bounded repository text is available for generic portability inspection.",
            ),
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )
    severity = "error" if any(signal.severity == "error" for signal in analysis.port_signals) else "warning"
    ordered_signals = sorted(analysis.port_signals, key=_severity_first)
    evidence = tuple(_evidence_for_signal(signal) for signal in ordered_signals[:MAX_EVIDENCE])
    return Finding(
        check_id=check_id,
        severity=severity,
        status="failed",
        title=_TITLES[check_id],
        message="Bounded text contains a developer-specific absolute or host-home path indicator.",
        evidence=evidence,
        remediation="Replace host-specific paths with repository-relative paths, environment variables, or documented portable defaults.",
        affected_path=evidence[0].path,
        category=_CATEGORIES[check_id],
        applicability=_applicability(
            reason="Bounded text contains a portability path indicator.",
        ),
        rule_version=RULE_VERSION,
        evidence_strength="indicator",
    )


def _security_finding(analysis: _Analysis) -> Finding:
    check_id = "CS-SEC-001"
    if analysis.coverage_incomplete:
        return _not_verified(
            check_id,
            analysis,
            "Security indicators could not be evaluated completely within bounded tracked-looking text evidence.",
        )
    if not analysis.security_signals:
        return Finding(
            check_id=check_id,
            severity="info",
            status="passed",
            title=_TITLES[check_id],
            message="No bounded private-key marker or contextual credential assignment was detected; values were not reported.",
            evidence=(
                Evidence(
                    kind="absence",
                    path=None,
                    detail="No high-confidence security indicator was detected; binary contents and raw values were not reported.",
                ),
            ),
            remediation=(),
            category=_CATEGORIES[check_id],
            applicability=_applicability(
                reason="Bounded tracked-looking text is available for generic security inspection.",
            ),
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )
    if any(signal.severity == "blocking" for signal in analysis.security_signals):
        severity = "blocking"
    elif any(signal.severity == "error" for signal in analysis.security_signals):
        severity = "error"
    else:
        severity = "warning"
    ordered_signals = sorted(analysis.security_signals, key=_severity_first)
    evidence = tuple(_evidence_for_signal(signal) for signal in ordered_signals[:MAX_EVIDENCE])
    return Finding(
        check_id=check_id,
        severity=severity,
        status="failed",
        title=_TITLES[check_id],
        message="Bounded text contains a redacted private-key or contextual credential indicator.",
        evidence=evidence,
        remediation="Remove committed credentials or private keys, rotate affected values, and retain only safe placeholders or environment references.",
        affected_path=evidence[0].path,
        category=_CATEGORIES[check_id],
        applicability=_applicability(
            reason="Bounded tracked-looking text contains a security indicator.",
        ),
        rule_version=RULE_VERSION,
        evidence_strength="indicator",
    )


def _build_finding(analysis: _Analysis) -> Finding:
    check_id = "CS-BUILD-001"
    if analysis.coverage_incomplete:
        return _not_verified(
            check_id,
            analysis,
            "Container build evidence could not be evaluated completely within the bounded inventory.",
        )
    if analysis.build_config_paths:
        evidence: list[Evidence] = [
            Evidence(
                kind="metadata",
                path=path,
                detail="A bounded Dockerfile or compose build configuration was discovered; no build was run.",
            )
            for path in analysis.build_config_paths[:MAX_EVIDENCE]
        ]
        evidence.extend(
            _evidence_for_signal(signal, kind="metadata")
            for signal in analysis.build_support_paths[:MAX_EVIDENCE]
        )
        return Finding(
            check_id=check_id,
            severity="info",
            status="passed",
            title=_TITLES[check_id],
            message="Bounded container workflow claims or repository presence are supported by Docker/compose configuration; no build was run.",
            evidence=tuple(evidence[:MAX_EVIDENCE]),
            remediation=(),
            affected_path=analysis.build_config_paths[0],
            category=_CATEGORIES[check_id],
            applicability=_applicability(
                reason="A bounded Dockerfile or compose configuration was discovered.",
            ),
            rule_version=RULE_VERSION,
            evidence_strength="direct",
        )
    if analysis.build_claims:
        evidence = [
            _evidence_for_signal(signal, kind="file")
            for signal in analysis.build_claims[:MAX_EVIDENCE]
        ]
        evidence.append(
            Evidence(
                kind="absence",
                path=None,
                detail="Bounded documentation clearly requires a container workflow, but no Dockerfile or compose configuration was discovered.",
            )
        )
        return Finding(
            check_id=check_id,
            severity="error",
            status="failed",
            title=_TITLES[check_id],
            message="Bounded documentation clearly requires Docker/container execution but no build configuration is present.",
            evidence=tuple(evidence[:MAX_EVIDENCE]),
            remediation="Add the required Dockerfile or compose configuration and document its bounded, reproducible use.",
            affected_path=analysis.build_claims[0].path,
            category=_CATEGORIES[check_id],
            applicability=_applicability(
                reason="Bounded documentation contains a clear container workflow claim.",
            ),
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )
    reason = "No bounded container workflow claim or Docker/compose build configuration was discovered."
    return Finding(
        check_id=check_id,
        severity="info",
        status="not_applicable",
        title=_TITLES[check_id],
        message=reason,
        evidence=(Evidence(kind="absence", path=None, detail=reason),),
        remediation="Add and document a bounded container configuration when a container workflow is intended.",
        category=_CATEGORIES[check_id],
        applicability=_applicability(applicable=False, reason=reason),
        rule_version=RULE_VERSION,
        evidence_strength="absence",
    )


def _path_finding(analysis: _Analysis) -> Finding:
    check_id = "CS-PATH-001"
    if analysis.coverage_incomplete:
        return _not_verified(
            check_id,
            analysis,
            "Repository-contained path evidence could not be evaluated completely within the bounded inventory.",
        )
    if not analysis.path_signals:
        reason = "No bounded Docker, packaging, configuration, documentation, script, or symlink path evidence was discovered."
        return Finding(
            check_id=check_id,
            severity="info",
            status="not_applicable",
            title=_TITLES[check_id],
            message=reason,
            evidence=(Evidence(kind="absence", path=None, detail=reason),),
            remediation="Add bounded repository-contained path evidence when the project uses local resources.",
            category=_CATEGORIES[check_id],
            applicability=_applicability(applicable=False, reason=reason),
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )
    issues = [signal for signal in analysis.path_signals if signal.indicator != "contained-present-reference"]
    if issues:
        severity = "error" if any(signal.severity == "error" for signal in issues) else "warning"
        ordered_signals = issues + [
            signal
            for signal in analysis.path_signals
            if signal.indicator == "contained-present-reference"
        ]
        evidence = tuple(
            _evidence_for_signal(signal, kind="metadata" if signal.indicator == "external-symlink" else "file")
            for signal in ordered_signals[:MAX_EVIDENCE]
        )
        return Finding(
            check_id=check_id,
            severity=severity,
            status="failed",
            title=_TITLES[check_id],
            message="Bounded path evidence contains an escape, missing local resource, external symlink, or uncertain path indicator.",
            evidence=evidence,
            remediation="Use repository-contained relative paths, include required resources, and remove or contain external symlinks.",
            affected_path=evidence[0].path,
            category=_CATEGORIES[check_id],
            applicability=_applicability(reason="Bounded path-bearing evidence was discovered."),
            rule_version=RULE_VERSION,
            evidence_strength="derived",
        )
    evidence = tuple(_evidence_for_signal(signal) for signal in analysis.path_signals[:MAX_EVIDENCE])
    return Finding(
        check_id=check_id,
        severity="info",
        status="passed",
        title=_TITLES[check_id],
        message="Inspected bounded path references are repository-contained and present in inventory; no target was opened outside the root.",
        evidence=evidence,
        remediation=(),
        affected_path=evidence[0].path if evidence else None,
        category=_CATEGORIES[check_id],
        applicability=_applicability(reason="Bounded path-bearing evidence was discovered."),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def evaluate_quality_checks(
    root: Path | str,
    inventory: InventoryResult,
    detection: DetectionResult,
    *,
    excluded_checks: Iterable[str] = (),
) -> tuple[Finding, ...]:
    """Evaluate the isolated M4 portability/security/build/path check slice.

    Exactly one finding is returned for each quality check in the stable
    catalog order.  Excluded checks remain visible as policy ``skipped``
    findings and do not cause repository files to be read for that check.
    """

    if isinstance(excluded_checks, str):
        excluded = {excluded_checks}
    else:
        try:
            excluded = {str(item) for item in excluded_checks}
        except TypeError:
            excluded = set()
    active = frozenset(check_id for check_id in _CHECK_IDS if check_id not in excluded)
    results: dict[str, Finding] = {
        check_id: _policy_skipped(check_id)
        for check_id in _CHECK_IDS
        if check_id in excluded
    }
    if active:
        try:
            analysis = _prepare_analysis(root, inventory, detection, active)
        except (AttributeError, TypeError, OSError, RuntimeError, ValueError, MemoryError):
            analysis = _Analysis(None, active)
            _mark_incomplete(analysis, "quality-analysis-inputs-unavailable")
        if "CS-PORT-001" in active:
            results["CS-PORT-001"] = _portability_finding(analysis)
        if "CS-SEC-001" in active:
            results["CS-SEC-001"] = _security_finding(analysis)
        if "CS-BUILD-001" in active:
            results["CS-BUILD-001"] = _build_finding(analysis)
        if "CS-PATH-001" in active:
            results["CS-PATH-001"] = _path_finding(analysis)
    return tuple(results[check_id] for check_id in _CHECK_IDS)


__all__ = [
    "MAX_EVIDENCE",
    "MAX_INSPECTED_FILES",
    "QUALITY_READ_LIMIT",
    "READ_LIMIT",
    "RULE_VERSION",
    "evaluate_quality_checks",
]
