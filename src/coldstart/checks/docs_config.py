"""Bounded documentation and configuration checks for the M4 slice.

This module intentionally has no integration with the audit engine.  It consumes
the already-collected inventory and detection objects, reads only selected
regular files from that inventory, and treats every repository byte as
untrusted text.  It never imports repository modules, starts a process, uses a
shell, or contacts a network service.

The three public findings are deliberately conservative:

* ``CS-DOCS-002`` requires both test-bearing evidence and a simple documented
  command that is compatible with that evidence;
* ``CS-CONFIG-001`` looks for a safe configuration template without reading
  live environment files into evidence; and
* ``CS-CONFIG-002`` compares names from high-confidence environment accesses
  with names mentioned by documentation or safe templates.

All report details are bounded categories, command families, or variable names;
raw source lines and configuration values are never copied into findings.
"""

from __future__ import annotations

import hashlib
import os
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..discovery import DetectionResult, FileRecord, InventoryResult
from ..findings import Applicability, Evidence, Finding


RULE_VERSION = "4"
DOCS_CONFIG_READ_LIMIT = 64 * 1024
READ_LIMIT = DOCS_CONFIG_READ_LIMIT
# The inventory itself is bounded, but a caller may provide a very large
# hand-built InventoryResult.  Keep this rule bounded independently as well.
MAX_INSPECTED_FILES = 256
MAX_EVIDENCE = 32


_DOC_SUFFIXES = {".adoc", ".asciidoc", ".markdown", ".md", ".rst", ".txt"}
_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".php",
    ".py",
    ".pyi",
    ".rb",
    ".rs",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".ts",
    ".tsx",
}
_CONFIG_SUFFIXES = {".cfg", ".conf", ".ini", ".json", ".properties", ".toml", ".xml", ".yaml", ".yml"}
_TEST_CONFIG_NAMES = {
    "pytest.ini": "pytest",
    "tox.ini": "tox",
    "noxfile": "nox",
    "noxfile.py": "nox",
}
_MAKE_NAMES = {"makefile", "gnumakefile"}
_CI_BASENAMES = {
    ".gitlab-ci.yml",
    ".gitlab-ci.yaml",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
    "buildkite.yml",
    "buildkite.yaml",
    "circle.yml",
    "ci.yml",
    "ci.yaml",
    "jenkinsfile",
    "test.yml",
    "test.yaml",
    "tests.yml",
    "tests.yaml",
    "travis.yml",
    "travis.yaml",
}
_LIVE_ENV_NAMES = {
    ".env",
    ".envrc",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".env.dev",
    ".env.prod",
}
_CREDENTIAL_FILE_NAMES = {
    ".aws",
    ".netrc",
    "credentials",
    "credentials.py",
    "credentials.ini",
    "credentials.json",
    "secret",
    "secret.py",
    "secret.json",
    "secrets.py",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}

_TEST_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:pytest|unittest|tox|nox|npm\s+test|yarn\s+test|"
    r"pnpm\s+test|just\s+test|cargo\s+test|go\s+test|mvn\s+test|"
    r"gradle\s+test|dotnet\s+test)(?![A-Za-z0-9_-])|"
    r"(?<![A-Za-z0-9_])make\s+tests?(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
_SHELL_OPERATOR = re.compile(r"(?:&&|\|\||[|;]|(?<![A-Za-z0-9_])&(?=\s|$)|(?:^|\s)(?:>>|>|<)(?=\s|[^=]))")
_COMMAND_START = re.compile(
    r"^(?:[$>]|PS\s*[>]?)\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:[^\s'\"]+|'[^']*'|\"[^\"]*\")\s+)*"
    r"(?:@?(?:python(?:3(?:\.\d+)?)?|py(?:\s+-\d+(?:\.\d+)?)?|pytest|tox|nox|make\s+tests?|"
    r"npm\s+test|yarn\s+test|pnpm\s+test|just\s+test|cargo\s+test|go\s+test|"
    r"mvn\s+test|gradle\s+test|dotnet\s+test|"
    r"(?:uv|poetry|pdm)\s+run\s+(?:pytest|tox|nox)|hatch\s+run\s+test))\b",
    re.IGNORECASE,
)
_DOC_COMMAND_REFERENCE = re.compile(
    r"(?:(?:python(?:3(?:\.\d+)?)?|py(?:\s+-\d+(?:\.\d+)?)?)\s+-m\s+(?:pytest|unittest)|"
    r"(?:uv|poetry|pdm)\s+run\s+(?:pytest|tox|nox)|hatch\s+run\s+test|"
    r"(?<![A-Za-z0-9_-])(?:pytest|tox|nox|make\s+tests?|npm\s+test|yarn\s+test|pnpm\s+test|"
    r"just\s+test|cargo\s+test|go\s+test|mvn\s+test|gradle\s+test|dotnet\s+test)(?![A-Za-z0-9_-]))",
    re.IGNORECASE,
)
_DOC_COMMAND_CONTEXT = re.compile(
    r"\b(?:run(?:s|ning)?|test(?:s|ing)?|command|execute|invoke|verify|check|workflow|ci)\b",
    re.IGNORECASE,
)
_YAML_COMMAND_PREFIX = re.compile(
    r"^\s*(?:[-*]\s*)?(?:run|script|command|cmd)\s*:\s*", re.IGNORECASE
)
_YAML_LIST_PREFIX = re.compile(r"^\s*[-*]\s+")
_ENV_ASSIGNMENT = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*=(?:[^\s'\"]+|'[^']*'|\"[^\"]*\")\s+)+"
)
_ENV_TOKEN = re.compile(r"\bos\s*\.\s*(?:environ|getenv)\b", re.IGNORECASE)
_ENV_BRACKET = re.compile(
    r"\bos\s*\.\s*environ\s*\[\s*(?:(?P<quote>['\"])(?P<name>[A-Za-z_][A-Za-z0-9_]*) (?P=quote)|(?P<dynamic>[^\]\n]{1,160}))\s*\]",
    re.IGNORECASE | re.VERBOSE,
)
_ENV_CALL_LITERAL = re.compile(
    r"\bos\s*\.\s*(?P<kind>getenv|environ\s*\.\s*get)\s*\(\s*"
    r"(?P<quote>['\"])(?P<name>[A-Za-z_][A-Za-z0-9_]*) (?P=quote)"
    r"(?P<rest>[^)\n]{0,240})\)",
    re.IGNORECASE | re.VERBOSE,
)
_BRACED_VARIABLE = re.compile(r"\$\{(?P<body>[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?)\}")
_EXPORTED_VARIABLE = re.compile(r"\bexport\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")
_DOCUMENTED_VARIABLE = re.compile(r"(?<![A-Za-z0-9_])(?P<name>[A-Z][A-Z0-9_]{2,})(?![A-Za-z0-9_])")
_CONFIG_DOC_REFERENCE = re.compile(
    r"(?:\bconfig(?:uration|ure|ured|uring)?\b|\benvironment\s+variables?\b|"
    r"\benv(?:ironment)?\s+vars?\b|\bsettings?\b|\bsecrets?\b|\bcredentials?\b|"
    r"\.env(?:\.[A-Za-z0-9_.-]+)?\b|\b(?:config|settings?)[A-Za-z0-9_.-]*\.(?:json|toml|xml|yaml|yml|ini|cfg)\b|"
    r"\b(?:set|export|define)\s+[A-Z][A-Z0-9_]*\b|"
    r"\b[A-Z][A-Z0-9_]{2,}\s*=)",
    re.IGNORECASE,
)
_CONFIG_FILE_REFERENCE = re.compile(
    r"\.env(?:\.[A-Za-z0-9_.-]+)?\b|"
    r"\b(?:config|settings?|application)[A-Za-z0-9_.-]*\.(?:cfg|conf|ini|json|properties|toml|xml|yaml|yml)\b",
    re.IGNORECASE,
)
_NO_CONFIGURATION = re.compile(
    r"\bno\s+(?:(?:external|runtime|additional)\s+)?configuration\s+(?:is\s+)?required\b|"
    r"\bwithout\s+(?:any\s+)?configuration\b",
    re.IGNORECASE,
)
_PYPROJECT_TEST_SECTION = re.compile(
    r"^\s*\[(?:tool\.(?:pytest|tox|nox|coverage)(?:\.|\])|"
    r"tool\.(?:hatch|pdm|poetry)[^\]]*\btest(?:s|ing)?\b[^\]]*\])",
    re.IGNORECASE,
)
_PYPROJECT_CONFIG_SECTION = re.compile(
    r"^\s*\[.*(?:config|settings?|env(?:ironment)?|dotenv|secrets?).*\]\s*$",
    re.IGNORECASE,
)
_PYPROJECT_CONFIG_KEY = re.compile(
    r"^\s*[A-Za-z0-9_.-]*(?:config|settings?|env(?:ironment)?|dotenv|secrets?)[A-Za-z0-9_.-]*\s*=",
    re.IGNORECASE,
)
_MAKE_TARGET = re.compile(
    r"^\s*(?P<target>[A-Za-z0-9_.-]*(?:test|tests|check)[A-Za-z0-9_.-]*)\s*:\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_CI_TEST_JOB = re.compile(
    r"^\s*(?:test|tests|testing|unit[-_ ]?tests?)\s*:\s*(?:#.*)?$",
    re.IGNORECASE,
)


# These are common host/tooling variables.  They are useful context, but do
# not represent project configuration a new developer must supply.
_IGNORED_VARIABLES = {
    "ALL_PROXY",
    "API",
    "APPDATA",
    "CI",
    "COLORTERM",
    "COMSPEC",
    "CONFIG",
    "CONFIGURATION",
    "CONDA_DEFAULT_ENV",
    "CONDA_PREFIX",
    "DEBUG",
    "DESKTOP_SESSION",
    "DISPLAY",
    "ENVIRONMENT",
    "GITHUB_ACTION",
    "GITHUB_ACTIONS",
    "GITHUB_REF",
    "GITHUB_SHA",
    "GITHUB_WORKFLOW",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "HOSTNAME",
    "HTTP",
    "HTTP_PROXY",
    "HTTPS",
    "HTTPS_PROXY",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOCALAPPDATA",
    "LOGNAME",
    "LOG_LEVEL",
    "NO_PROXY",
    "OLDPWD",
    "OS",
    "PATH",
    "PATHEXT",
    "PIP_DISABLE_PIP_VERSION_CHECK",
    "PIP_INDEX_URL",
    "PIP_TRUSTED_HOST",
    "PWD",
    "PYTEST_CURRENT_TEST",
    "PYTHONHOME",
    "PYTHONPATH",
    "README",
    "RUNNER_OS",
    "SHELL",
    "SHLVL",
    "SECRETS",
    "SECRET",
    "SETTINGS",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TEST",
    "TESTS",
    "TMP",
    "TMPDIR",
    "USER",
    "USERNAME",
    "VARIABLE",
    "VARIABLES",
    "VIRTUAL_ENV",
    "WINDIR",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "YAML",
    "JSON",
    "TOML",
    "URL",
}
_IGNORED_VARIABLE_PREFIXES = (
    "CONDA_",
    "GITHUB_",
    "LC_",
    "PIP_",
    "PYTEST_",
    "RUNNER_",
    "VSCODE_",
    "XDG_",
)


@dataclass(frozen=True)
class _ReadText:
    path: str | None
    text: str | None
    digest: str | None
    error: str | None = None


@dataclass(frozen=True)
class _Signal:
    path: str | None
    line: int | None
    kind: str
    detail: str
    digest: str | None = None


@dataclass(frozen=True)
class _Command:
    path: str
    line: int
    family: str
    display: str
    digest: str | None = None


@dataclass(frozen=True)
class _VariableUse:
    name: str
    path: str
    line: int
    source: str
    required: bool
    digest: str | None = None


@dataclass(frozen=True)
class _Template:
    path: str
    safe: bool
    variables: tuple[str, ...]
    line_by_variable: tuple[tuple[str, int], ...]
    digest: str | None = None


@dataclass
class _Analysis:
    errors: list[_Signal] = field(default_factory=list)
    test_signals: list[_Signal] = field(default_factory=list)
    test_families: set[str] = field(default_factory=set)
    make_targets: set[str] = field(default_factory=set)
    make_recipe_families: set[str] = field(default_factory=set)
    commands: list[_Command] = field(default_factory=list)
    shell_commands: list[_Signal] = field(default_factory=list)
    config_signals: list[_Signal] = field(default_factory=list)
    dynamic_signals: list[_Signal] = field(default_factory=list)
    required_variables: dict[str, list[_VariableUse]] = field(default_factory=dict)
    documented_variables: dict[str, list[_VariableUse]] = field(default_factory=dict)
    templates: list[_Template] = field(default_factory=list)
    test_bearing: bool = False
    inspection_limited: bool = False
    coverage_incomplete: bool = False


def _normal_relative_path(value: object) -> str | None:
    """Normalize an inventory path without allowing traversal or absolutes."""

    if not isinstance(value, str):
        return None
    raw = value.replace("\\", "/")
    if not raw or raw.startswith("/"):
        return None
    if len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha():
        return None
    if any(":" in part for part in raw.split("/") if part not in {"", "."}):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in raw):
        return None
    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def _record_sort_key(record: FileRecord) -> tuple[str, str, str, int, str]:
    value = record.relative_path if isinstance(record.relative_path, str) else ""
    kind = str(getattr(record, "kind", ""))
    readable = 0 if bool(getattr(record, "readable", False)) else 1
    size = repr(getattr(record, "size", None))
    return value.casefold(), value, kind, readable, size


def _safe_record_path(root: Path, record: FileRecord) -> tuple[Path | None, str | None]:
    """Resolve one inventory record while rejecting every symlink component."""

    relative = _normal_relative_path(getattr(record, "relative_path", None))
    if relative is None:
        return None, "invalid absolute, traversal, or control-character inventory path"
    if getattr(record, "kind", None) != "file":
        return None, "inventory record is not a regular file"
    if bool(getattr(record, "external_symlink", False)):
        return None, "symlinked inventory entry was not read"
    if not bool(getattr(record, "readable", False)):
        return None, "inventory record is unreadable"
    size = getattr(record, "size", None)
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
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


def _read_bounded_text(root: Path, record: FileRecord) -> _ReadText:
    """Read one discovered regular file with a hard byte limit."""

    relative = _normal_relative_path(getattr(record, "relative_path", None))
    if relative is None:
        return _ReadText(None, None, None, "inventory path was rejected")
    if getattr(record, "kind", None) != "file":
        return _ReadText(relative, None, None, "inventory record is not a regular file")
    if bool(getattr(record, "external_symlink", False)):
        return _ReadText(relative, None, None, "symlinked inventory entry was not read")
    if not bool(getattr(record, "readable", False)):
        return _ReadText(relative, None, None, "inventory record is unreadable")
    size = getattr(record, "size", None)
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
        return _ReadText(relative, None, None, "inventory record has an invalid size")
    if size is not None and size > DOCS_CONFIG_READ_LIMIT:
        return _ReadText(relative, None, None, "file exceeds the bounded text limit")

    candidate, error = _safe_record_path(root, record)
    if candidate is None:
        return _ReadText(relative, None, None, error or "file path is not contained")
    try:
        with candidate.open("rb") as handle:
            data = handle.read(DOCS_CONFIG_READ_LIMIT + 1)
    except (OSError, PermissionError):
        return _ReadText(relative, None, None, "file could not be read")
    if len(data) > DOCS_CONFIG_READ_LIMIT:
        return _ReadText(relative, None, None, "file exceeds the bounded text limit")
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _ReadText(relative, None, digest, "file is not valid UTF-8 text")
    return _ReadText(relative, text, digest)


def _parts(path: str) -> tuple[str, ...]:
    return tuple(item.casefold() for item in path.split("/"))


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _is_documentation_path(path: str) -> bool:
    basename = _basename(path).casefold()
    suffix = Path(basename).suffix.casefold()
    return basename.startswith("readme") or (
        any(item in {"docs", "documentation"} for item in _parts(path))
        and suffix in _DOC_SUFFIXES
    )


def _is_source_path(path: str) -> bool:
    return Path(_basename(path)).suffix.casefold() in _SOURCE_SUFFIXES


def _test_config_family(path: str) -> str | None:
    return _TEST_CONFIG_NAMES.get(_basename(path).casefold())


def _is_makefile(path: str) -> bool:
    return _basename(path).casefold() in _MAKE_NAMES


def _is_ci_path(path: str) -> bool:
    parts = _parts(path)
    basename = _basename(path).casefold()
    if basename in _CI_BASENAMES:
        return True
    if any(
        parts[index : index + 2] == (".github", "workflows")
        for index in range(max(0, len(parts) - 2))
    ) and parts[-1].endswith((".yml", ".yaml")):
        return True
    if len(parts) >= 2 and parts[-2:] == (".circleci", "config.yml"):
        return True
    if len(parts) >= 2 and parts[-2:] == (".circleci", "config.yaml"):
        return True
    if ".buildkite" in parts and basename.endswith((".yml", ".yaml")):
        return True
    return False


def _is_test_file(path: str) -> bool:
    basename = _basename(path).casefold()
    parts = _parts(path)
    if not basename.endswith(".py"):
        return False
    if basename.startswith("test_") and any(item in {"tests", "test"} for item in parts[:-1]):
        return True
    return basename.endswith("_test.py")


def _is_live_environment_file(path: str) -> bool:
    basename = _basename(path).casefold()
    return basename in _LIVE_ENV_NAMES or (
        basename.startswith(".env.") and not _is_safe_template_path(path)
    )


def _is_safe_template_path(path: str) -> bool:
    basename = _basename(path).casefold()
    suffix = Path(basename).suffix.casefold()
    stem = Path(basename).stem.casefold()
    if basename in {".env.example", ".env.sample", ".env.template"}:
        return True
    if basename.startswith(".env.") and any(
        token in basename for token in (".example", ".sample", ".template")
    ):
        return True
    if suffix not in _CONFIG_SUFFIXES and not (
        suffix == ".env"
        and re.search(r"(?:^|[._-])(?:example|sample|template)(?:$|[._-])", stem)
    ) and not (
        suffix == ".py"
        and (
            re.search(r"(?:config|settings?|application)", stem)
            or any(item in {"examples", "example", "config", "templates", "template"} for item in _parts(path)[:-1])
        )
    ):
        return False
    if any(item in {"examples", "example", "templates", "template"} for item in _parts(path)[:-1]):
        return True
    return bool(
        re.search(r"(?:^|[._-])(config|settings?|application|local|development|test)[._-](?:example|sample|template)$", stem)
        or re.search(r"^(?:example|sample|template)[._-](?:config|settings?|application)$", stem)
        or re.search(r"(?:^|[._-])(?:example|sample|template)(?:$|[._-])", stem)
    )


def _configuration_filename(path: str) -> str | None:
    basename = _basename(path).casefold()
    if _is_safe_template_path(path):
        return "safe-template"
    if _is_live_environment_file(path):
        return "live-environment-file"
    if basename in _CREDENTIAL_FILE_NAMES:
        return "credential-shaped-file"
    if basename in {
        "config.py",
        "config.cfg",
        "config.conf",
        "config.ini",
        "config.json",
        "config.toml",
        "config.yaml",
        "config.yml",
        "settings.py",
        "settings.cfg",
        "settings.ini",
        "settings.json",
        "settings.toml",
        "settings.yaml",
        "settings.yml",
        "application.yml",
        "application.yaml",
        "application.json",
        "application.properties",
        "local.ini",
        "local.json",
        "local.toml",
        "local.yaml",
        "local.yml",
        "development.json",
        "development.toml",
        "development.yaml",
        "development.yml",
        "production.json",
        "production.toml",
        "production.yaml",
        "production.yml",
    }:
        return "configuration-file"
    parts = _parts(path)
    if any(item in {"config", "configuration", "settings"} for item in parts[:-1]):
        if Path(basename).suffix.casefold() in _CONFIG_SUFFIXES:
            return "configuration-directory-file"
    return None


def _is_ignored_variable(name: str) -> bool:
    normalized = name.upper()
    return normalized in _IGNORED_VARIABLES or normalized.startswith(_IGNORED_VARIABLE_PREFIXES)


def _signal_key(signal: _Signal) -> tuple[str, str, int, str, str]:
    path = signal.path or ""
    return path.casefold(), path, signal.line or 0, signal.kind, signal.detail


def _command_key(command: _Command) -> tuple[str, str, int, str, str]:
    return command.path.casefold(), command.path, command.line, command.family, command.display


def _add_signal(items: list[_Signal], signal: _Signal) -> None:
    if signal not in items:
        items.append(signal)


def _add_command(items: list[_Command], command: _Command) -> None:
    if command not in items:
        items.append(command)


def _error(analysis: _Analysis, path: str | None, category: str) -> None:
    _add_signal(
        analysis.errors,
        _Signal(
            path=path,
            line=None,
            kind="error",
            detail=f"Bounded evidence was not verified: {category}.",
        ),
    )


def _test_signal(
    analysis: _Analysis,
    path: str | None,
    line: int | None,
    kind: str,
    detail: str,
    digest: str | None = None,
    *,
    family: str | None = None,
) -> None:
    analysis.test_bearing = True
    _add_signal(analysis.test_signals, _Signal(path, line, kind, detail, digest))
    if family:
        analysis.test_families.add(family)


def _config_signal(
    analysis: _Analysis,
    path: str | None,
    line: int | None,
    detail: str,
    digest: str | None = None,
    *,
    kind: str = "file",
) -> None:
    _add_signal(analysis.config_signals, _Signal(path, line, kind, detail, digest))


def _normal_variable_name(value: str) -> str:
    # Keep untrusted identifier text bounded before it can enter evidence.
    return value.strip().upper()[:128]


def _add_variable(
    analysis: _Analysis,
    use: _VariableUse,
    *,
    documented: bool = False,
) -> None:
    name = _normal_variable_name(use.name)
    if not name or _is_ignored_variable(name):
        return
    normalized = _VariableUse(name, use.path, use.line, use.source, use.required, use.digest)
    target = analysis.documented_variables if documented else analysis.required_variables
    entries = target.setdefault(name, [])
    if normalized not in entries:
        entries.append(normalized)


def _line_number_for(text: str, pattern: re.Pattern[str]) -> int | None:
    for number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return number
    return None


def _looks_like_simple_command(text: str) -> bool:
    return bool(
        re.match(
            r"^(?:@)?(?:python(?:3(?:\.\d+)?)?|pytest|tox|nox|make\s+test|"
            r"(?:uv|poetry|pdm)\s+run\s+(?:pytest|tox|nox)|hatch\s+run\s+test)\b",
            text.strip(),
            re.IGNORECASE,
        )
    )


def _strip_shell_comment(text: str) -> str:
    # A comment marker after whitespace is not part of a supported command.
    match = re.search(r"\s+#", text)
    return text[: match.start()].rstrip() if match else text


def _parse_simple_command(fragment: str) -> tuple[str, str] | None:
    """Return a command family/display, or ``None`` for unsafe/unknown text."""

    text = fragment.strip()
    text = re.sub(r"^(?:[$>]|PS\s*[>]?)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^@+", "", text).strip()
    text = _strip_shell_comment(text)
    if not text or _SHELL_OPERATOR.search(text):
        return None
    # Environment prefixes are accepted as documentation context, but their
    # values are discarded before the command family is recorded.
    while True:
        prefix = _ENV_ASSIGNMENT.match(text)
        if prefix is None:
            break
        text = text[prefix.end() :].lstrip()
    patterns = (
        (r"(?:python(?:3(?:\.\d+)?)?|py(?:\s+-\d+(?:\.\d+)?)?)\s+-m\s+pytest(?:\s+.*)?$", "pytest", "python -m pytest"),
        (r"(?:python(?:3(?:\.\d+)?)?|py(?:\s+-\d+(?:\.\d+)?)?)\s+-m\s+unittest(?:\s+.*)?$", "unittest", "python -m unittest"),
        (r"pytest(?:\.exe)?(?:\s+.*)?$", "pytest", "pytest"),
        (r"tox(?:\.exe)?(?:\s+.*)?$", "tox", "tox"),
        (r"nox(?:\.exe)?(?:\s+.*)?$", "nox", "nox"),
        (r"make\s+tests?(?:\s+.*)?$", "make", "make test"),
        (r"npm\s+test(?:\s+.*)?$", "npm", "npm test"),
        (r"yarn\s+test(?:\s+.*)?$", "yarn", "yarn test"),
        (r"pnpm\s+test(?:\s+.*)?$", "pnpm", "pnpm test"),
        (r"just\s+test(?:\s+.*)?$", "just", "just test"),
        (r"cargo\s+test(?:\s+.*)?$", "cargo", "cargo test"),
        (r"go\s+test(?:\s+.*)?$", "go", "go test"),
        (r"mvn\s+test(?:\s+.*)?$", "maven", "mvn test"),
        (r"gradle\s+test(?:\s+.*)?$", "gradle", "gradle test"),
        (r"dotnet\s+test(?:\s+.*)?$", "dotnet", "dotnet test"),
        (r"(?:uv|poetry|pdm)\s+run\s+pytest(?:\s+.*)?$", "pytest", "pytest"),
        (r"(?:uv|poetry|pdm)\s+run\s+(?:tox|nox)(?:\s+.*)?$", "tox", "tox"),
        (r"hatch\s+run\s+test(?:\s+.*)?$", "pytest", "test"),
    )
    for pattern, family, display in patterns:
        if re.fullmatch(pattern, text, re.IGNORECASE):
            return family, display
    return None


def _shell_signal(
    analysis: _Analysis,
    path: str,
    line: int,
    digest: str | None,
    *,
    family: str | None = None,
) -> None:
    family_detail = f" test_family={family}." if family else ""
    _add_signal(
        analysis.shell_commands,
        _Signal(
            path=path,
            line=line,
            kind="command",
            detail=(
                "A bounded test-like command contains unsupported shell composition; "
                f"it was not treated as an executable candidate.{family_detail}"
            ),
            digest=digest,
        ),
    )


def _test_family_in_shell_command(fragment: str) -> str | None:
    lowered = fragment.casefold()
    if re.search(r"\b(?:python(?:\d+(?:\.\d+)?)?\s+-m\s+)?unittest\b", lowered):
        return "unittest"
    if re.search(r"\bpytest\b", lowered):
        return "pytest"
    if re.search(r"\b(?:tox|nox)\b", lowered):
        return "tox"
    return None


def _command_fragments(path: str, text: str, source_kind: str) -> tuple[tuple[int, str], ...]:
    fragments: list[tuple[int, str]] = []
    in_fence = False
    fence_marker = ""
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if source_kind == "docs":
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if in_fence and marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                elif not in_fence:
                    in_fence = True
                    fence_marker = marker
                continue
            inline = re.findall(r"`([^`\n]{1,512})`", line)
            if inline:
                if not (_SHELL_OPERATOR.search(line) and _TEST_TOKEN.search(line)):
                    fragments.extend((line_number, item) for item in inline)
                else:
                    fragments.append((line_number, " ".join(inline)))
            elif in_fence and stripped:
                fragments.append((line_number, stripped))
            else:
                command_line = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", stripped)
                if _SHELL_OPERATOR.search(command_line) and _TEST_TOKEN.search(command_line):
                    fragments.append((line_number, command_line))
                elif _COMMAND_START.match(command_line):
                    fragments.append((line_number, command_line))
            continue

        candidate = line
        if source_kind == "ci":
            candidate = _YAML_COMMAND_PREFIX.sub("", candidate, count=1)
            candidate = _YAML_LIST_PREFIX.sub("", candidate, count=1)
        elif source_kind == "make":
            if ";" in candidate:
                candidate = candidate.split(";", 1)[1]
            elif not line[:1].isspace():
                continue
        candidate = candidate.strip()
        if candidate:
            fragments.append((line_number, candidate))
    return tuple(fragments)


def _extract_line_commands(
    analysis: _Analysis,
    path: str,
    text: str,
    source_kind: str,
    digest: str | None,
) -> None:
    for line_number, fragment in _command_fragments(path, text, source_kind):
        if _SHELL_OPERATOR.search(fragment) and _TEST_TOKEN.search(fragment):
            _shell_signal(
                analysis,
                path,
                line_number,
                digest,
                family=_test_family_in_shell_command(fragment),
            )
            if source_kind != "docs":
                _test_signal(
                    analysis,
                    path,
                    line_number,
                    "command",
                    "A bounded build/CI workflow contains a test-like shell composition; it was not executed.",
                    digest,
                )
            continue
        parsed = _parse_simple_command(fragment)
        if parsed is None:
            continue
        family, display = parsed
        _add_command(analysis.commands, _Command(path, line_number, family, display, digest))
        # A README/docs command is only a candidate; it cannot by itself prove
        # that the repository is test-bearing.  Makefile and CI commands are
        # workflow evidence in their own right.
        if source_kind != "docs":
            _test_signal(
                analysis,
                path,
                line_number,
                "command",
                "A bounded build/CI workflow contains a simple test command; ColdStart did not execute it.",
                digest,
                family=family,
            )
            if source_kind == "make":
                analysis.make_recipe_families.add(family)

    # Keep evidence for a chain in documentation that was not in a code
    # fragment.  It is intentionally not promoted to a command candidate.
    if source_kind == "docs":
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _SHELL_OPERATOR.search(line) and _TEST_TOKEN.search(line):
                _shell_signal(analysis, path, line_number, digest)
                continue
            if not _DOC_COMMAND_CONTEXT.search(line):
                continue
            for match in _DOC_COMMAND_REFERENCE.finditer(line):
                parsed = _parse_simple_command(match.group(0))
                if parsed is None:
                    continue
                family, display = parsed
                _add_command(analysis.commands, _Command(path, line_number, family, display, digest))


def _extract_make_targets(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _MAKE_TARGET.match(line)
        if match is None:
            continue
        target = match.group("target").casefold()
        if target.startswith(".phony"):
            continue
        analysis.make_targets.add(target)
        target_is_test = "test" in target
        if target_is_test:
            _test_signal(
                analysis,
                path,
                line_number,
                "command",
                "A Makefile declares a test-bearing target; the target was not executed.",
                digest,
                family="make" if target in {"test", "tests"} else None,
            )
        if target in {"test", "tests"}:
            _add_command(analysis.commands, _Command(path, line_number, "make", "make test", digest))
        rest = match.group("rest").strip()
        if rest:
            parsed = _parse_simple_command(rest)
            if parsed is not None:
                family, display = parsed
                _add_command(analysis.commands, _Command(path, line_number, family, display, digest))
                analysis.make_recipe_families.add(family)
                if not target_is_test:
                    _test_signal(
                        analysis,
                        path,
                        line_number,
                        "command",
                        "A Makefile check target contains a simple test command; the target was not executed.",
                        digest,
                        family=family,
                    )


def _extract_ci_test_jobs(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _CI_TEST_JOB.match(line):
            _test_signal(
                analysis,
                path,
                line_number,
                "metadata",
                "A bounded CI file declares a test-bearing job; no workflow was executed.",
                digest,
            )


def _scan_environment_accesses(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _CONFIG_FILE_REFERENCE.search(line) and not _NO_CONFIGURATION.search(line):
            _config_signal(
                analysis,
                path,
                line_number,
                "A bounded text file references a configuration filename; values were not read.",
                digest,
            )
        covered_spans: list[tuple[int, int]] = []
        for match in _ENV_BRACKET.finditer(line):
            covered_spans.append(match.span())
            name = match.group("name")
            if name is None:
                _add_signal(
                    analysis.dynamic_signals,
                    _Signal(
                        path,
                        line_number,
                        "error",
                        "A bounded source file uses dynamic environment-variable construction; the variable name was not inferred.",
                        digest,
                    ),
                )
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    "A bounded source file references environment configuration dynamically; values were not read.",
                    digest,
                )
                continue
            normalized = _normal_variable_name(name)
            _add_variable(
                analysis,
                _VariableUse(normalized, path, line_number, "os.environ", True, digest),
            )
            if not _is_ignored_variable(normalized):
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    f"A bounded source file references environment variable name '{normalized}'; values were not read.",
                    digest,
                )

        for match in _ENV_CALL_LITERAL.finditer(line):
            covered_spans.append(match.span())
            name = _normal_variable_name(match.group("name"))
            rest = match.group("rest").strip()
            if rest and (
                not rest.startswith(",")
                or re.search(r"\bos\s*\.|[+{}]", rest) is not None
            ):
                _add_signal(
                    analysis.dynamic_signals,
                    _Signal(
                        path,
                        line_number,
                        "error",
                        "A bounded source file constructs an environment-variable name dynamically; the variable name was not inferred.",
                        digest,
                    ),
                )
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    "A bounded source file references environment configuration dynamically; values were not read.",
                    digest,
                )
                continue
            required = not rest.startswith(",")
            if required:
                _add_variable(
                    analysis,
                    _VariableUse(name, path, line_number, match.group("kind"), required, digest),
                )
            if not _is_ignored_variable(name):
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    f"A bounded source file references environment variable name '{name}'; values were not read.",
                    digest,
                )

        for token in _ENV_TOKEN.finditer(line):
            if not any(start <= token.start() < end for start, end in covered_spans):
                _add_signal(
                    analysis.dynamic_signals,
                    _Signal(
                        path,
                        line_number,
                        "error",
                        "A bounded source file uses dynamic environment-variable access; the variable name was not inferred.",
                        digest,
                    ),
                )
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    "A bounded source file references environment configuration dynamically; values were not read.",
                    digest,
                )

        for match in _BRACED_VARIABLE.finditer(line):
            body = match.group("body")
            if ":-" in body:
                name = body.split(":-", 1)[0]
                required = False
            else:
                name = body
                required = True
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                _add_signal(
                    analysis.dynamic_signals,
                    _Signal(
                        path,
                        line_number,
                        "error",
                        "A bounded shell-style environment reference was dynamic; the variable name was not inferred.",
                        digest,
                    ),
                )
                continue
            normalized = _normal_variable_name(name)
            if required:
                _add_variable(
                    analysis,
                    _VariableUse(normalized, path, line_number, "shell expansion", True, digest),
                )
            if not _is_ignored_variable(normalized):
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    f"A bounded text file references environment variable name '{normalized}'; values were not read.",
                    digest,
                )

        for match in _EXPORTED_VARIABLE.finditer(line):
            name = _normal_variable_name(match.group("name"))
            _add_variable(
                analysis,
                _VariableUse(name, path, line_number, "export", True, digest),
            )
            if not _is_ignored_variable(name):
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    f"A bounded text file exports environment variable name '{name}'; values were not read.",
                    digest,
                )


def _scan_documentation(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    lines = text.splitlines()
    document_declares_no_configuration = any(_NO_CONFIGURATION.search(line) for line in lines)
    explicit_config_reference = re.compile(
        r"\.env(?:\.[A-Za-z0-9_.-]+)?\b|\benvironment\s+variables?\b|"
        r"\b(?:set|export|define)\s+[A-Z][A-Z0-9_]*\b|"
        r"\b(?:config|settings?)[A-Za-z0-9_.-]*\.(?:json|toml|xml|yaml|yml|ini|cfg)\b",
        re.IGNORECASE,
    )
    for line_number, line in enumerate(lines, start=1):
        generic_reference = bool(_CONFIG_DOC_REFERENCE.search(line))
        explicit_reference = bool(explicit_config_reference.search(line))
        config_context = bool(
            re.search(r"\b(?:config(?:uration)?|environment\s+variables?|settings?|secrets?|credentials?)\b", line, re.IGNORECASE)
        )
        file_or_environment_reference = bool(
            re.search(
                r"\.env(?:\.[A-Za-z0-9_.-]+)?\b|\benvironment\s+variables?\b|"
                r"\b(?:config|settings?)[A-Za-z0-9_.-]*\.(?:json|toml|xml|yaml|yml|ini|cfg)\b",
                line,
                re.IGNORECASE,
            )
        )
        line_variable_names = {
            _normal_variable_name(match.group("name"))
            for match in _DOCUMENTED_VARIABLE.finditer(line)
        }
        ignored_only_reference = bool(line_variable_names) and not any(
            not _is_ignored_variable(name) for name in line_variable_names
        )
        system_environment_list = bool(
            re.search(r"\benvironment\s+variables?\s*[:=]", line, re.IGNORECASE)
        ) and ignored_only_reference
        line_is_config = (
            generic_reference
            and not _NO_CONFIGURATION.search(line)
            and (not document_declares_no_configuration or explicit_reference)
            and not (ignored_only_reference and not config_context and not file_or_environment_reference)
            and not system_environment_list
        )
        if line_is_config:
            _config_signal(
                analysis,
                path,
                line_number,
                "Bounded documentation contains a configuration reference; values were not read.",
                digest,
            )
        for match in _DOCUMENTED_VARIABLE.finditer(line):
            name = _normal_variable_name(match.group("name"))
            if _is_ignored_variable(name):
                continue
            configuration_line = line_is_config
            if configuration_line:
                _add_variable(
                    analysis,
                    _VariableUse(name, path, line_number, "documentation reference", True, digest),
                )
            _add_variable(
                analysis,
                _VariableUse(name, path, line_number, "documentation", False, digest),
                documented=True,
            )
            if line_is_config:
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    f"Bounded documentation names configuration variable '{name}'; values were not read.",
                    digest,
                )
    _scan_environment_accesses(analysis, path, text, digest)


def _template_variables(text: str) -> tuple[tuple[str, int], ...]:
    variables: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith(('#', ';', '//')):
            continue
        assignment = re.match(
            r"^\s*(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:)\s*",
            line,
        )
        if assignment is not None:
            name = _normal_variable_name(assignment.group("name"))
            if not _is_ignored_variable(name):
                variables.setdefault(name, line_number)
            continue
        for match in re.finditer(r"[\"'](?P<name>[A-Za-z_][A-Za-z0-9_]{2,})[\"']\s*:", line):
            name = _normal_variable_name(match.group("name"))
            if not _is_ignored_variable(name):
                variables.setdefault(name, line_number)
    return tuple(sorted(variables.items(), key=lambda item: (item[0].casefold(), item[0], item[1])))


def _placeholder_value(value: str) -> bool:
    candidate = value.strip().strip(",").strip().strip("'\"").strip()
    if not candidate:
        return True
    lowered = candidate.casefold()
    if lowered in {
        "...",
        "changeme",
        "change-me",
        "dummy",
        "example",
        "none",
        "null",
        "placeholder",
        "replace-me",
        "replace_me",
        "todo",
        "your-value",
        "your_value",
    }:
        return True
    if candidate.startswith(("<", "${", "{{")) or candidate.endswith((">", "}", "}}")):
        return True
    if lowered.startswith(("change-", "example-", "placeholder-", "replace-", "your-", "your_", "enter-")):
        return True
    return False


def _template_is_safe(text: str) -> bool:
    """Reject obvious credential-shaped values without retaining any value."""

    if "-----begin " in text.casefold() or re.search(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}", text):
        return False
    for line in text.splitlines():
        if line.lstrip().startswith(('#', ';', '//')):
            continue
        match = re.match(
            r"^\s*(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*(?:=|:)\s*(?P<value>.*?)(?:\s*,)?\s*$",
            line,
        )
        if match is not None:
            name = match.group("name").casefold()
            value = match.group("value").strip()
            if not _placeholder_value(value):
                secret_name = re.search(r"(?:secret|token|password|passwd|api[-_]?key|private|credential)", name)
                if secret_name:
                    return False
                if re.search(r"^[A-Za-z0-9_-]{24,}$", value.strip("'\"")):
                    return False
        for mapping_match in re.finditer(
            r"[\"']?(?P<mapping_name>[A-Za-z_][A-Za-z0-9_-]*)[\"']?\s*:\s*(?P<mapping_value>[^,}\n]+)",
            line,
        ):
            mapping_name = mapping_match.group("mapping_name").casefold()
            mapping_value = mapping_match.group("mapping_value").strip()
            if _placeholder_value(mapping_value):
                continue
            if re.search(r"(?:secret|token|password|passwd|api[-_]?key|private|credential)", mapping_name):
                return False
            if re.search(r"^[A-Za-z0-9_-]{24,}$", mapping_value.strip("'\"")):
                return False
    return True


def _process_template(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    variables_with_lines = _template_variables(text)
    safe = _template_is_safe(text)
    template = _Template(
        path=path,
        safe=safe,
        variables=tuple(name for name, _line in variables_with_lines),
        line_by_variable=variables_with_lines,
        digest=digest,
    )
    if template not in analysis.templates:
        analysis.templates.append(template)
    if safe:
        _config_signal(
            analysis,
            path,
            None,
            "A safe configuration template was discovered; template values were not reported.",
            digest,
        )
        for name, line in variables_with_lines:
            _add_variable(
                analysis,
                _VariableUse(name, path, line, "safe template", False, digest),
                documented=True,
            )
    else:
        _config_signal(
            analysis,
            path,
            None,
            "A candidate configuration template was rejected as credential-shaped; values were not reported.",
            digest,
        )


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _toml_get(document: Mapping[str, object], *keys: str) -> object | None:
    current: object = document
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _process_pyproject(analysis: _Analysis, path: str, text: str, digest: str | None) -> None:
    try:
        document = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, TypeError, ValueError, MemoryError):
        _error(analysis, path, "pyproject.toml is malformed")
        # Regex section markers retain conservative test/config applicability
        # while the malformed file remains not_verified.
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _PYPROJECT_TEST_SECTION.match(line):
                _test_signal(
                    analysis,
                    path,
                    line_number,
                    "metadata",
                    "Bounded pyproject text contains a test configuration section; parsing was incomplete.",
                    digest,
                )
            if _PYPROJECT_CONFIG_SECTION.match(line):
                _config_signal(
                    analysis,
                    path,
                    line_number,
                    "Bounded pyproject text contains a configuration section; parsing was incomplete.",
                    digest,
                    kind="metadata",
                )
        return
    if not isinstance(document, Mapping):
        _error(analysis, path, "pyproject.toml did not contain a TOML table")
        return

    tool = _mapping(document.get("tool"))
    project = _mapping(document.get("project"))
    optional = _mapping(project.get("optional-dependencies")) if project else None
    if optional:
        for group_name, values in sorted(optional.items(), key=lambda item: str(item[0]).casefold()):
            if not isinstance(group_name, str):
                continue
            group_key = group_name.casefold()
            string_values = _string_values(values)
            test_group = group_key in {"test", "tests", "testing"}
            test_group = test_group or (
                group_key in {"dev", "development"}
                and any(
                    token in value.casefold()
                    for value in string_values
                    for token in ("pytest", "tox", "nox", "unittest")
                )
            )
            if not test_group:
                continue
            line = _line_number_for(text, re.compile(rf"^\s*\[project\.optional-dependencies\]\s*$", re.IGNORECASE))
            _test_signal(
                analysis,
                path,
                line,
                "metadata",
                "Bounded pyproject metadata declares a test/development dependency group; values were not executed.",
                digest,
            )
            for value in string_values:
                lowered = value.casefold()
                for family, token in (("pytest", "pytest"), ("tox", "tox"), ("nox", "nox"), ("unittest", "unittest")):
                    if token in lowered:
                        analysis.test_families.add(family)

    dependency_groups = _mapping(document.get("dependency-groups"))
    if dependency_groups:
        for group_name, values in sorted(dependency_groups.items(), key=lambda item: str(item[0]).casefold()):
            if not isinstance(group_name, str):
                continue
            group_key = group_name.casefold()
            string_values = _string_values(values)
            test_group = group_key in {"test", "tests", "testing"}
            test_group = test_group or (
                group_key in {"dev", "development"}
                and any(
                    token in value.casefold()
                    for value in string_values
                    for token in ("pytest", "tox", "nox", "unittest")
                )
            )
            if not test_group:
                continue
            _test_signal(
                analysis,
                path,
                _line_number_for(text, re.compile(r"^\s*\[dependency-groups\]\s*$", re.IGNORECASE)),
                "metadata",
                "Bounded pyproject metadata declares a test/development dependency group; values were not executed.",
                digest,
            )
            for value in string_values:
                lowered = value.casefold()
                for family, token in (("pytest", "pytest"), ("tox", "tox"), ("nox", "nox"), ("unittest", "unittest")):
                    if token in lowered:
                        analysis.test_families.add(family)

    if tool:
        for family in ("pytest", "tox", "nox", "coverage"):
            if family in tool:
                line = _line_number_for(text, re.compile(rf"^\s*\[tool\.{family}(?:\.|\])", re.IGNORECASE))
                _test_signal(
                    analysis,
                    path,
                    line,
                    "metadata",
                    f"Bounded pyproject metadata contains {family} test configuration; values were not executed.",
                    digest,
                    family=family if family != "coverage" else None,
                )

        for manager in ("pdm", "poetry"):
            manager_table = _mapping(tool.get(manager))
            scripts = _mapping(manager_table.get("scripts")) if manager_table else None
            if scripts:
                _process_script_mapping(analysis, path, text, digest, scripts)
            if manager_table:
                _process_manager_test_dependencies(analysis, path, text, digest, manager, manager_table)

        hatch = _mapping(tool.get("hatch"))
        envs = _mapping(hatch.get("envs")) if hatch else None
        if envs:
            for env_name, env_value in sorted(envs.items(), key=lambda item: str(item[0]).casefold()):
                if not isinstance(env_name, str) or "test" not in env_name.casefold():
                    continue
                env_table = _mapping(env_value)
                scripts = _mapping(env_table.get("scripts")) if env_table else None
                if scripts:
                    _process_script_mapping(analysis, path, text, digest, scripts, include_all=True)
                else:
                    _test_signal(
                        analysis,
                        path,
                        _line_number_for(text, re.compile(r"^\s*\[tool\.hatch\.envs\..*test.*\]", re.IGNORECASE)),
                        "metadata",
                        "Bounded pyproject metadata declares a test environment; values were not executed.",
                        digest,
                    )

    scripts = _mapping(project.get("scripts")) if project else None
    if scripts:
        _process_script_mapping(analysis, path, text, digest, scripts)

    for line_number, line in enumerate(text.splitlines(), start=1):
        if _PYPROJECT_CONFIG_SECTION.match(line):
            _config_signal(
                analysis,
                path,
                line_number,
                "Bounded pyproject metadata contains a configuration section; values were not reported.",
                digest,
                kind="metadata",
            )
        elif _PYPROJECT_CONFIG_KEY.search(line):
            # Only lines within a parsed pyproject are considered here; this
            # avoids treating arbitrary package metadata as runtime config.
            _config_signal(
                analysis,
                path,
                line_number,
                "Bounded pyproject metadata references configuration; values were not reported.",
                digest,
                kind="metadata",
            )

    _scan_environment_accesses(analysis, path, text, digest)


def _process_script_mapping(
    analysis: _Analysis,
    path: str,
    text: str,
    digest: str | None,
    scripts: Mapping[str, object],
    *,
    include_all: bool = False,
) -> None:
    for script_name, value in sorted(scripts.items(), key=lambda item: str(item[0]).casefold()):
        if not isinstance(script_name, str) or (
            not include_all and "test" not in script_name.casefold()
        ):
            continue
        _test_signal(
            analysis,
            path,
            _line_number_for(text, re.compile(rf"^\s*{re.escape(script_name)}\s*=", re.IGNORECASE)),
            "metadata",
            "Bounded pyproject metadata declares a test script; the script was not executed.",
            digest,
        )
        for candidate_text in _string_values(value):
            parsed = _parse_simple_command(candidate_text)
            if parsed is None:
                if _SHELL_OPERATOR.search(candidate_text) and _TEST_TOKEN.search(candidate_text):
                    line = _line_number_for(text, re.compile(rf"^\s*{re.escape(script_name)}\s*=", re.IGNORECASE)) or 1
                    _shell_signal(analysis, path, line, digest)
                continue
            family, display = parsed
            line = _line_number_for(text, re.compile(rf"^\s*{re.escape(script_name)}\s*=", re.IGNORECASE)) or 1
            _add_command(analysis.commands, _Command(path, line, family, display, digest))
            analysis.test_families.add(family)


def _process_manager_test_dependencies(
    analysis: _Analysis,
    path: str,
    text: str,
    digest: str | None,
    manager: str,
    manager_table: Mapping[str, object],
) -> None:
    """Recognize only explicit test/dev dependency groups in known managers."""

    groups: Mapping[str, object] | None = None
    if manager == "poetry":
        groups = _mapping(manager_table.get("group"))
    elif manager == "pdm":
        groups = _mapping(manager_table.get("dev-dependencies"))
    if not groups:
        return
    for group_name, group_value in sorted(groups.items(), key=lambda item: str(item[0]).casefold()):
        if not isinstance(group_name, str):
            continue
        group_key = group_name.casefold()
        dependency_values: list[str] = []
        group_table = _mapping(group_value)
        if manager == "poetry" and group_table:
            dependency_table = _mapping(group_table.get("dependencies"))
            if dependency_table:
                dependency_values.extend(str(key) for key in dependency_table)
        else:
            dependency_values.extend(_string_values(group_value))
            if group_table:
                dependency_values.extend(str(key) for key in group_table)
        is_test_group = group_key in {"test", "tests", "testing"}
        is_test_group = is_test_group or (
            group_key in {"dev", "development"}
            and any(token in value.casefold() for value in dependency_values for token in ("pytest", "tox", "nox", "unittest"))
        )
        if not is_test_group:
            continue
        _test_signal(
            analysis,
            path,
            _line_number_for(text, re.compile(rf"^\s*\[tool\.{manager}.*{re.escape(group_name)}.*\]", re.IGNORECASE)),
            "metadata",
            "Bounded pyproject metadata declares a test/development dependency group; values were not executed.",
            digest,
        )
        for value in dependency_values:
            lowered = value.casefold()
            for family, token in (("pytest", "pytest"), ("tox", "tox"), ("nox", "nox"), ("unittest", "unittest")):
                if token in lowered:
                    analysis.test_families.add(family)


def _prepare_analysis(root: Path, inventory: InventoryResult, detection: DetectionResult) -> _Analysis:
    analysis = _Analysis()
    try:
        records_value = inventory.records
        records = list(records_value)
    except (AttributeError, TypeError):
        analysis.coverage_incomplete = True
        _error(analysis, None, "inventory records were unavailable")
        return analysis

    try:
        if not root.is_dir():
            analysis.coverage_incomplete = True
            _error(analysis, None, "repository root was not a readable directory")
    except OSError:
        analysis.coverage_incomplete = True
        _error(analysis, None, "repository root could not be inspected")

    try:
        if bool(inventory.incomplete):
            analysis.coverage_incomplete = True
            _error(analysis, None, "inventory coverage is partial or contains unreadable entries")
    except (AttributeError, TypeError):
        analysis.coverage_incomplete = True
        _error(analysis, None, "inventory completeness was unavailable")
    try:
        if bool(detection.incomplete):
            analysis.coverage_incomplete = True
            _error(analysis, None, "project detection metadata or inventory coverage is incomplete")
    except (AttributeError, TypeError):
        analysis.coverage_incomplete = True
        _error(analysis, None, "project detection completeness was unavailable")

    candidate_records: list[tuple[str, FileRecord]] = []
    seen_paths: set[str] = set()
    for record in sorted(records, key=_record_sort_key):
        relative = _normal_relative_path(getattr(record, "relative_path", None))
        kind = getattr(record, "kind", None)
        if relative is None:
            analysis.coverage_incomplete = True
            _error(analysis, None, "inventory contained an absolute, traversal, or malformed path")
            continue
        if kind not in {"file", "symlink"}:
            analysis.coverage_incomplete = True
            _error(analysis, relative, "inventory contained an unsupported entry kind")
            continue
        if relative in seen_paths:
            continue
        seen_paths.add(relative)
        sensitive_filename = _configuration_filename(relative) in {
            "live-environment-file",
            "credential-shaped-file",
        }
        error_path = None if sensitive_filename else relative
        if not bool(getattr(record, "readable", False)):
            analysis.coverage_incomplete = True
            _error(analysis, error_path, "inventory record was unreadable")
        size = getattr(record, "size", None)
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
            analysis.coverage_incomplete = True
            _error(analysis, error_path, "inventory record had an invalid size")

        basename = _basename(relative).casefold()
        relevant = (
            _is_test_file(relative)
            or _test_config_family(relative) is not None
            or basename == "pyproject.toml"
            or _is_makefile(relative)
            or _is_ci_path(relative)
            or _is_documentation_path(relative)
            or _is_source_path(relative)
            or _is_safe_template_path(relative)
            or _configuration_filename(relative) is not None
        )
        if relevant:
            _, boundary_error = _safe_record_path(root, record)
            if boundary_error is not None:
                analysis.coverage_incomplete = True
                _error(analysis, error_path, boundary_error)
            candidate_records.append((relative, record))

    candidate_records.sort(key=lambda item: (item[0].casefold(), item[0]))
    if len(candidate_records) > MAX_INSPECTED_FILES:
        analysis.inspection_limited = True
        analysis.coverage_incomplete = True
        _error(analysis, None, "the bounded documentation/configuration file limit was reached")
        candidate_records = candidate_records[:MAX_INSPECTED_FILES]

    cache: dict[str, _ReadText] = {}

    def read_record(relative: str, record: FileRecord) -> _ReadText:
        if relative not in cache:
            result = _read_bounded_text(root, record)
            cache[relative] = result
            if result.error is not None:
                analysis.coverage_incomplete = True
                _error(analysis, relative, result.error)
        return cache[relative]

    for relative, record in candidate_records:
        basename = _basename(relative).casefold()
        test_file = _is_test_file(relative)
        test_family = _test_config_family(relative)
        template_path = _is_safe_template_path(relative)
        configuration_kind = _configuration_filename(relative)

        if test_file:
            _test_signal(
                analysis,
                relative,
                None,
                "file",
                "A bounded inventory entry matches a test-file naming convention; the file was not executed.",
                family=None,
            )
        if test_family:
            _test_signal(
                analysis,
                relative,
                None,
                "metadata",
                f"A bounded inventory entry is a {test_family} test configuration file; it was not executed.",
                family=test_family if test_family != "coverage" else None,
            )
        if basename == "pyproject.toml" and not template_path:
            result = read_record(relative, record)
            if result.error is None:
                _process_pyproject(analysis, relative, result.text or "", result.digest)
        elif _is_documentation_path(relative):
            result = read_record(relative, record)
            if result.error is None:
                _scan_documentation(analysis, relative, result.text or "", result.digest)
                _extract_line_commands(analysis, relative, result.text or "", "docs", result.digest)
        elif _is_makefile(relative):
            result = read_record(relative, record)
            if result.error is None:
                _extract_make_targets(analysis, relative, result.text or "", result.digest)
                _scan_environment_accesses(analysis, relative, result.text or "", result.digest)
                _extract_line_commands(analysis, relative, result.text or "", "make", result.digest)
        elif _is_ci_path(relative):
            result = read_record(relative, record)
            if result.error is None:
                _extract_ci_test_jobs(analysis, relative, result.text or "", result.digest)
                _scan_environment_accesses(analysis, relative, result.text or "", result.digest)
                _extract_line_commands(analysis, relative, result.text or "", "ci", result.digest)
        elif template_path:
            result = read_record(relative, record)
            if result.error is None:
                _process_template(analysis, relative, result.text or "", result.digest)
        elif _is_source_path(relative):
            result = read_record(relative, record)
            if result.error is None:
                _scan_environment_accesses(analysis, relative, result.text or "", result.digest)
        elif test_family:
            # Test configuration files are evidence even when their contents
            # are unavailable; readable content is not needed for applicability.
            if _is_source_path(relative):
                result = read_record(relative, record)
                if result.error is None:
                    _scan_environment_accesses(analysis, relative, result.text or "", result.digest)

        if configuration_kind and configuration_kind != "safe-template":
            if configuration_kind == "live-environment-file":
                # Do not read or report the live file path/content.
                _config_signal(
                    analysis,
                    None,
                    None,
                    "A live environment configuration file was detected; its contents were not read or reported.",
                )
            elif configuration_kind == "credential-shaped-file":
                _config_signal(
                    analysis,
                    None,
                    None,
                    "A credential-shaped configuration file was detected; its contents were not read or reported.",
                )
            else:
                _config_signal(
                    analysis,
                    relative,
                    None,
                    "A bounded inventory entry has a conventional configuration filename; values were not read into evidence.",
                )

        # A symlink can still be an inventory indicator, but it is never read.
        if (
            getattr(record, "kind", None) == "symlink"
            or bool(getattr(record, "external_symlink", False))
        ) and (
            test_file
            or test_family
            or template_path
            or _is_documentation_path(relative)
            or _is_source_path(relative)
            or configuration_kind is not None
        ):
            analysis.coverage_incomplete = True
            _error(analysis, relative if not _is_live_environment_file(relative) else None, "symlinked inventory entry was not read")

    # De-duplicate and stabilize every collection before rule evaluation.
    analysis.errors.sort(key=_signal_key)
    analysis.test_signals.sort(key=_signal_key)
    analysis.config_signals.sort(key=_signal_key)
    analysis.dynamic_signals.sort(key=_signal_key)
    analysis.shell_commands.sort(key=_signal_key)
    analysis.commands.sort(key=_command_key)
    analysis.templates.sort(key=lambda item: (item.path.casefold(), item.path))
    for mapping in (analysis.required_variables, analysis.documented_variables):
        for name in mapping:
            mapping[name].sort(key=lambda item: (item.path.casefold(), item.path, item.line, item.source))
    return analysis


def _evidence(signal: _Signal) -> Evidence:
    return Evidence(
        kind=signal.kind,
        path=signal.path,
        line_start=signal.line,
        line_end=signal.line,
        detail=signal.detail,
        digest=signal.digest,
    )


def _error_evidence(analysis: _Analysis) -> tuple[Evidence, ...]:
    signals = list(analysis.errors)
    for signal in analysis.dynamic_signals:
        if signal not in signals:
            signals.append(signal)
    signals.sort(key=_signal_key)
    if not signals:
        signals = [_Signal(None, None, "error", "Bounded evidence was incomplete.")]
    return tuple(_evidence(item) for item in signals[:MAX_EVIDENCE])


def _policy_skipped(check_id: str, title: str, category: str, severity: str) -> Finding:
    reason = "The configured policy excludes this check; no rule logic was run."
    return Finding(
        check_id=check_id,
        severity=severity,
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
        remediation=f"Remove {check_id} from excluded_checks when this coverage is required.",
        category=category,
        applicability=Applicability(applicable=False, reason=reason, adapter="policy"),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _not_applicable(
    check_id: str,
    title: str,
    category: str,
    reason: str,
) -> Finding:
    return Finding(
        check_id=check_id,
        severity="info",
        status="not_applicable",
        title=title,
        message=reason,
        evidence=(Evidence(kind="absence", path=None, detail=reason),),
        remediation="Add the corresponding bounded evidence when this workflow is intended to be reproducible.",
        category=category,
        applicability=Applicability(applicable=False, reason=reason, adapter="generic"),
        rule_version=RULE_VERSION,
        evidence_strength="absence",
    )


def _not_verified(
    check_id: str,
    title: str,
    category: str,
    analysis: _Analysis,
    reason: str,
) -> Finding:
    evidence = _error_evidence(analysis)
    return Finding(
        check_id=check_id,
        severity="warning",
        status="not_verified",
        title=title,
        message=reason,
        evidence=evidence,
        remediation="Resolve unreadable, malformed, dynamic, oversized, or partial bounded evidence and rerun the check.",
        affected_path=evidence[0].path,
        category=category,
        applicability=Applicability(applicable=True, reason="The bounded evidence indicates this check may apply.", adapter="generic"),
        rule_version=RULE_VERSION,
        evidence_strength="unverified",
    )


def _test_command_finding(analysis: _Analysis) -> Finding:
    check_id = "CS-DOCS-002"
    title = "Test command documentation"
    category = "documentation"
    if analysis.coverage_incomplete:
        return _not_verified(
            check_id,
            title,
            category,
            analysis,
            "Test-command documentation could not be evaluated completely within the bounded inventory.",
        )
    if not analysis.test_bearing:
        reason = "No bounded test-bearing files, test configuration, Makefile target, or CI test workflow was discovered."
        return _not_applicable(check_id, title, category, reason)

    commands = analysis.commands
    evidence: list[Evidence] = [_evidence(item) for item in analysis.test_signals[:MAX_EVIDENCE]]
    evidence.extend(
        Evidence(
            kind="command",
            path=item.path,
            line_start=item.line,
            line_end=item.line,
            detail=f"A bounded source documents the simple test command family '{item.display}'; ColdStart did not execute it.",
            digest=item.digest,
        )
        for item in commands[:MAX_EVIDENCE]
    )
    evidence.extend(_evidence(item) for item in analysis.shell_commands[:MAX_EVIDENCE])

    if not commands:
        if any("test_family=unittest" in item.detail for item in analysis.shell_commands):
            evidence.append(
                Evidence(
                    kind="absence",
                    path=None,
                    detail="The documented unittest workflow uses unsupported shell composition and cannot be verified as one portable command.",
                )
            )
            return Finding(
                check_id=check_id,
                severity="warning",
                status="not_verified",
                title=title,
                message="The documented unittest workflow contains unsupported shell composition, so its test command was not verified.",
                evidence=tuple(evidence[:MAX_EVIDENCE]),
                remediation="Document the unittest command without shell chaining or other unsupported composition.",
                affected_path=analysis.shell_commands[0].path,
                category=category,
                applicability=Applicability(applicable=True, reason="Test files or test workflow metadata indicate a test-bearing repository.", adapter="generic"),
                rule_version=RULE_VERSION,
                evidence_strength="unverified",
            )
        evidence.append(
            Evidence(
                kind="absence",
                path=None,
                detail="No usable single test command candidate was found in bounded README/docs, Makefile, pyproject, or CI evidence.",
            )
        )
        return Finding(
            check_id=check_id,
            severity="error",
            status="failed",
            title=title,
            message="The repository contains test-bearing evidence but no usable documented single test command.",
            evidence=tuple(evidence[:MAX_EVIDENCE]),
            remediation="Document one simple portable test command and declare its test dependency/configuration.",
            affected_path=analysis.test_signals[0].path if analysis.test_signals else None,
            category=category,
            applicability=Applicability(applicable=True, reason="Test files or test workflow metadata indicate a test-bearing repository.", adapter="generic"),
            rule_version=RULE_VERSION,
            evidence_strength="absence",
        )

    candidate_families = {item.family for item in commands}
    strong_families = {item for item in analysis.test_families if item in {"pytest", "unittest", "tox", "nox"}}
    contradiction = False
    if len(candidate_families) > 1:
        non_make_candidates = candidate_families - {"make"}
        make_wraps_one_recipe = (
            "make" in candidate_families
            and len(non_make_candidates) == 1
            and non_make_candidates.issubset(analysis.make_recipe_families)
        )
        if not make_wraps_one_recipe:
            contradiction = True
    if strong_families:
        non_make_candidates = {item for item in candidate_families if item != "make"}
        if non_make_candidates and not non_make_candidates.issubset(strong_families):
            contradiction = True
        if "make" in candidate_families and "make" not in analysis.test_families:
            contradiction = True
    if "make" in candidate_families and not analysis.make_targets.intersection({"test", "tests"}):
        contradiction = True
    if analysis.make_targets and analysis.make_recipe_families and "make" not in candidate_families:
        # A documented direct command is acceptable when it matches the
        # Makefile recipe; a different recipe is a visible contradiction.
        if not candidate_families.intersection(analysis.make_recipe_families):
            contradiction = True
    if contradiction:
        evidence.append(
            Evidence(
                kind="error",
                path=commands[0].path,
                line_start=commands[0].line,
                line_end=commands[0].line,
                detail="The bounded command family conflicts with discovered test configuration or another workflow command; no command was executed.",
                digest=commands[0].digest,
            )
        )
        return Finding(
            check_id=check_id,
            severity="warning",
            status="failed",
            title=title,
            message="The documented test command conflicts with bounded test configuration or another documented workflow command.",
            evidence=tuple(evidence[:MAX_EVIDENCE]),
            remediation="Document one portable test command and align it with the discovered test configuration and workflow.",
            affected_path=commands[0].path,
            category=category,
            applicability=Applicability(applicable=True, reason="Test files or test workflow metadata indicate a test-bearing repository.", adapter="generic"),
            rule_version=RULE_VERSION,
            evidence_strength="derived",
        )

    return Finding(
        check_id=check_id,
        severity="info",
        status="passed",
        title=title,
        message="Bounded test-bearing evidence agrees with a clear documented single test command; the command was not executed.",
        evidence=tuple(evidence[:MAX_EVIDENCE]),
        remediation=(),
        affected_path=commands[0].path,
        category=category,
        applicability=Applicability(applicable=True, reason="Test files or test workflow metadata indicate a test-bearing repository.", adapter="generic"),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def _template_evidence(template: _Template) -> Evidence:
    detail = (
        "A safe configuration template was discovered; template values were not reported."
        if template.safe
        else "A candidate configuration template was rejected as credential-shaped; values were not reported."
    )
    return Evidence(kind="file", path=template.path, detail=detail, digest=template.digest)


def _config_example_finding(analysis: _Analysis) -> Finding:
    check_id = "CS-CONFIG-001"
    title = "Configuration example discovery"
    category = "configuration"
    if analysis.coverage_incomplete or analysis.dynamic_signals:
        return _not_verified(
            check_id,
            title,
            category,
            analysis,
            "Configuration examples could not be evaluated completely because bounded evidence was partial, unreadable, or dynamically constructed.",
        )
    if not analysis.config_signals:
        reason = "No bounded documentation, source, metadata, environment-file, or configuration-file indicator was discovered."
        return _not_applicable(check_id, title, category, reason)

    safe_templates = [item for item in analysis.templates if item.safe]
    all_template_variables = {name for item in safe_templates for name in item.variables}
    required_names = set(analysis.required_variables)
    missing_names = sorted(required_names - all_template_variables)
    evidence: list[Evidence] = [
        _evidence(item) for item in analysis.config_signals[:MAX_EVIDENCE]
    ]
    evidence.extend(_template_evidence(item) for item in analysis.templates[:MAX_EVIDENCE])
    if safe_templates and not missing_names:
        return Finding(
            check_id=check_id,
            severity="info",
            status="passed",
            title=title,
            message="A safe bounded configuration template is present for the discovered configuration workflow; template values were not reported.",
            evidence=tuple(evidence[:MAX_EVIDENCE]),
            remediation=(),
            affected_path=safe_templates[0].path,
            category=category,
            applicability=Applicability(applicable=True, reason="Bounded documentation/source or configuration filenames indicate a configuration workflow.", adapter="generic"),
            rule_version=RULE_VERSION,
            evidence_strength="direct",
        )

    if missing_names:
        for name in missing_names[:MAX_EVIDENCE]:
            source = analysis.required_variables[name][0]
            evidence.append(
                Evidence(
                    kind="file",
                    path=source.path,
                    line_start=source.line,
                    line_end=source.line,
                    detail=f"Configuration variable name '{name}' has no matching safe template entry; values were not read.",
                    digest=source.digest,
                )
            )
    evidence.append(
        Evidence(
            kind="absence",
            path=None,
            detail="No safe configuration template covers the discovered configuration references; live values were not read or reported.",
        )
    )
    return Finding(
        check_id=check_id,
        severity="warning",
        status="failed",
        title=title,
        message="Configuration is referenced by bounded evidence but no safe example covers the required configuration.",
        evidence=tuple(evidence[:MAX_EVIDENCE]),
        remediation="Add a sanitized .env.example, .env.sample, or example configuration file containing placeholders only.",
        affected_path=analysis.config_signals[0].path,
        category=category,
        applicability=Applicability(applicable=True, reason="Bounded documentation/source or configuration filenames indicate a configuration workflow.", adapter="generic"),
        rule_version=RULE_VERSION,
        evidence_strength="absence",
    )


def _variable_evidence(use: _VariableUse, *, documented: bool) -> Evidence:
    if documented:
        detail = f"Environment variable name '{use.name}' is documented in bounded text or a safe template; values were not reported."
    else:
        detail = f"Environment variable name '{use.name}' is accessed by a bounded static pattern; values were not read."
    return Evidence(
        kind="file",
        path=use.path,
        line_start=use.line,
        line_end=use.line,
        detail=detail,
        digest=use.digest,
    )


def _environment_documentation_finding(analysis: _Analysis) -> Finding:
    check_id = "CS-CONFIG-002"
    title = "Environment-variable documentation"
    category = "configuration"
    if analysis.coverage_incomplete or analysis.dynamic_signals:
        return _not_verified(
            check_id,
            title,
            category,
            analysis,
            "Environment-variable documentation could not be evaluated completely because bounded evidence is partial or dynamically constructed.",
        )
    required_names = tuple(sorted(analysis.required_variables, key=lambda value: (value.casefold(), value)))
    if not required_names:
        reason = "No high-confidence required-looking environment-variable access was discovered in bounded evidence."
        return _not_applicable(check_id, title, category, reason)

    documented_names = set(analysis.documented_variables)
    undocumented = tuple(name for name in required_names if name not in documented_names)
    evidence: list[Evidence] = []
    for name in required_names:
        evidence.extend(_variable_evidence(item, documented=False) for item in analysis.required_variables[name][:4])
        if name in documented_names:
            evidence.extend(_variable_evidence(item, documented=True) for item in analysis.documented_variables[name][:4])
        else:
            evidence.append(
                Evidence(
                    kind="absence",
                    path=None,
                    detail=f"No bounded documentation or safe template mentions environment variable name '{name}'.",
                )
            )
    if undocumented:
        return Finding(
            check_id=check_id,
            severity="warning",
            status="failed",
            title=title,
            message="One or more high-confidence environment-variable names are not documented by bounded text or a safe template.",
            evidence=tuple(evidence[:MAX_EVIDENCE]),
            remediation="Document each variable's purpose, required/optional status, and safe placeholder without committing its value.",
            affected_path=analysis.required_variables[undocumented[0]][0].path,
            category=category,
            applicability=Applicability(applicable=True, reason="Bounded source or shell evidence contains required-looking environment-variable access.", adapter="generic"),
            rule_version=RULE_VERSION,
            evidence_strength="derived",
        )
    return Finding(
        check_id=check_id,
        severity="info",
        status="passed",
        title=title,
        message="All high-confidence environment-variable names are documented by bounded text or a safe template; values were not reported.",
        evidence=tuple(evidence[:MAX_EVIDENCE]),
        remediation=(),
        affected_path=analysis.required_variables[required_names[0]][0].path,
        category=category,
        applicability=Applicability(applicable=True, reason="Bounded source or shell evidence contains required-looking environment-variable access.", adapter="generic"),
        rule_version=RULE_VERSION,
        evidence_strength="direct",
    )


def evaluate_docs_and_config_checks(
    root: Path | str,
    inventory: InventoryResult,
    detection: DetectionResult,
    *,
    excluded_checks: Iterable[str] = (),
) -> tuple[Finding, ...]:
    """Evaluate the isolated M4 documentation/configuration check slice.

    The returned tuple always contains exactly one finding for each public M4
    check, in check-ID order.  Exclusions are visible ``skipped`` findings
    with policy evidence and do not expose repository content.
    """

    if isinstance(excluded_checks, str):
        excluded = {excluded_checks}
    else:
        excluded = {str(item) for item in excluded_checks}
    check_ids = ("CS-DOCS-002", "CS-CONFIG-001", "CS-CONFIG-002")
    titles = {
        "CS-DOCS-002": ("Test command documentation", "documentation", "error"),
        "CS-CONFIG-001": ("Configuration example discovery", "configuration", "warning"),
        "CS-CONFIG-002": ("Environment-variable documentation", "configuration", "warning"),
    }

    results: dict[str, Finding] = {}
    for check_id in check_ids:
        if check_id in excluded:
            title, category, severity = titles[check_id]
            results[check_id] = _policy_skipped(check_id, title, category, severity)

    if len(results) < len(check_ids):
        try:
            analysis = _prepare_analysis(Path(root), inventory, detection)
        except (AttributeError, TypeError, OSError, RuntimeError, ValueError):
            analysis = _Analysis(coverage_incomplete=True)
            _error(analysis, None, "documentation/configuration inputs could not be inspected")
        if "CS-DOCS-002" not in results:
            results["CS-DOCS-002"] = _test_command_finding(analysis)
        if "CS-CONFIG-001" not in results:
            results["CS-CONFIG-001"] = _config_example_finding(analysis)
        if "CS-CONFIG-002" not in results:
            results["CS-CONFIG-002"] = _environment_documentation_finding(analysis)

    return tuple(results[check_id] for check_id in check_ids)


__all__ = [
    "DOCS_CONFIG_READ_LIMIT",
    "MAX_INSPECTED_FILES",
    "READ_LIMIT",
    "RULE_VERSION",
    "evaluate_docs_and_config_checks",
]
