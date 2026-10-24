"""Explicit, bounded execution for the optional ColdStart M6 verification core.

The normal ColdStart audit is deliberately non-executing.  This module is a
separate opt-in boundary for two narrowly defined operations: a Python
``unittest``/``pytest`` command and a Docker build.  A plan is only data; it
does not inspect project commands or start a child process.  A child process
is started only by :func:`execute_execution_plan` after the caller supplies
``authorize=True``.

The host runner keeps the repository as its working directory; the offline
Docker runner binds it read-only at ``/workspace``.  Both pass an argv list to
:class:`subprocess.Popen`, never invoke a shell, bound captured output, and
compare a regular-file source manifest before and after execution.  The
receipt is intentionally a safe summary: it contains no repository path,
environment values, or unbounded process output.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import shutil
import stat
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Sequence


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_OUTPUT_LIMIT_BYTES = 65_536
MAX_TIMEOUT_SECONDS = 3_600
MAX_OUTPUT_LIMIT_BYTES = 16 * 1024 * 1024

_DOCKER_ARGV = ("docker", "build", "--tag", "coldstart-verification:local", ".")
_DOCKER_OFFLINE_ARGV = (
    "docker",
    "build",
    "--network=none",
    "--tag",
    "coldstart-verification:local",
    ".",
)
_DOCKER_TEST_IMAGE = "python:3.12.8-slim-bookworm"
_DOCKER_TEST_TMPFS = "/tmp:rw,nosuid,nodev,noexec,size=64m"
_DOCKER_TEST_CPUS = "1"
_DOCKER_TEST_MEMORY = "512m"
_DOCKER_TEST_PIDS_LIMIT = "256"
_DOCKER_TEST_DISPLAY_MOUNT = "<repository>:/workspace:ro"
_DOCKER_TEST_DISPLAY_PREFIX = (
    "docker",
    "run",
    "--rm",
    "--network=none",
    "--pull=never",
    "--read-only",
    "--tmpfs",
    _DOCKER_TEST_TMPFS,
    "--cpus",
    _DOCKER_TEST_CPUS,
    "--memory",
    _DOCKER_TEST_MEMORY,
    "--pids-limit",
    _DOCKER_TEST_PIDS_LIMIT,
    "--volume",
    _DOCKER_TEST_DISPLAY_MOUNT,
    "--workdir",
    "/workspace",
    _DOCKER_TEST_IMAGE,
)
_DOCKER_TEST_RESOURCE_LIMITS = {
    "cpus": _DOCKER_TEST_CPUS,
    "memory": _DOCKER_TEST_MEMORY,
    "pids_limit": _DOCKER_TEST_PIDS_LIMIT,
    "tmpfs": _DOCKER_TEST_TMPFS,
}
_SAFE_CONTAINER_PATH_TOKENS = frozenset(
    {
        "/workspace",
        "--workdir=/workspace",
        _DOCKER_TEST_TMPFS,
        _DOCKER_TEST_DISPLAY_MOUNT,
    }
)
_DEFAULT_TEST_ARGV = (
    "python",
    "-m",
    "unittest",
    "discover",
    "-s",
    "tests",
    "-p",
    "test_*.py",
)
_TEST_EXECUTABLES = frozenset({"pytest", "pytest.exe"})
_MANIFEST_EXCLUDED_DIRECTORIES = frozenset(
    {
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
    }
)
_MAX_MANIFEST_FILES = 100_000
_MAX_MANIFEST_BYTES = 2_000_000_000
_OUTPUT_DETAIL_BYTES = 4_096
_OUTPUT_DETAIL_CHARS = 2_048
_SHELL_OPERATOR = re.compile(r"[;&|<>`$\x00\r\n]")
_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
_EMBEDDED_ABSOLUTE = re.compile(r"(?:^|=)(?:/|[A-Za-z]:[\\/]|\\\\)")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"authorization|cookie|private[_ -]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", re.DOTALL
)
_TOKEN_SHAPE = re.compile(r"\b(?:sk|gh[pousr]|xox[baprs])[-_][A-Za-z0-9_-]{8,}\b")
_POSIX_ABSOLUTE_TEXT = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s/]+/)*[^\s/]+")
_WINDOWS_ABSOLUTE_TEXT = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/]|\\\\)[^\s\r\n]+"
)
_HOME_ABSOLUTE_TEXT = re.compile(r"(?<![A-Za-z0-9_])~/[^\s\r\n]+")
_DOCKER_START_FAILURE_MARKERS = (
    "cannot connect to the docker daemon",
    "failed to connect to the docker api",
    "error during connect",
    "is the docker daemon running",
    "docker desktop is unable to start",
    "daemon is not running",
)


class _KindDisplay(str):
    """JSON-safe kind text that treats the historical CLI alias as equivalent."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str) and {
            str(self),
            other,
        } == {"docker_build", "docker-build"}:
            return True
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class ExecutionValidationError(ValueError):
    """A proposed execution does not satisfy the M6 safety contract."""


class _ManifestError(RuntimeError):
    """Internal marker for an unreadable or changing source manifest."""


def _normalize_kind(kind: str) -> str:
    """Normalize the two public execution-kind spellings."""

    if not isinstance(kind, str) or not kind.strip():
        raise ExecutionValidationError("execution kind must be a non-empty string")
    normalized = kind.strip().lower()
    if normalized == "docker-build":
        normalized = "docker_build"
    if normalized not in {"tests", "docker_build"}:
        raise ExecutionValidationError(
            "unsupported execution kind; expected tests or docker_build"
        )
    return normalized


def _normalize_sandbox(value: object, *, field_name: str = "sandbox") -> str | None:
    """Normalize one of the two supported execution sandboxes."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ExecutionValidationError(
            f"{field_name} must be either 'host' or 'docker'"
        )
    normalized = value.strip().lower()
    if normalized not in {"host", "docker"}:
        raise ExecutionValidationError(
            f"{field_name} must be either 'host' or 'docker'"
        )
    return normalized


def _expected_sandbox(kind: str, offline: bool) -> str:
    """Return the only safe sandbox for a normalized plan."""

    if kind == "docker_build":
        return "docker"
    return "docker" if offline else "host"


def _validate_limit(name: str, value: int, maximum: int) -> int:
    """Validate one positive integer resource limit."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExecutionValidationError(f"{name} must be a positive integer")
    if value > maximum:
        raise ExecutionValidationError(f"{name} exceeds the safe maximum of {maximum}")
    return value


def _canonical_repository(repository: Path) -> Path:
    """Resolve and validate a readable repository directory without inspecting it."""

    try:
        candidate = Path(repository)
    except (TypeError, ValueError) as error:
        raise ExecutionValidationError("repository must be a valid directory path") from error
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, PermissionError, OSError) as error:
        raise ExecutionValidationError("repository must be an existing readable directory") from error
    if not resolved.is_dir():
        raise ExecutionValidationError("repository must be an existing directory")
    try:
        with os.scandir(resolved):
            pass
    except (PermissionError, OSError) as error:
        raise ExecutionValidationError("repository directory is not readable") from error
    return resolved


def _is_absolute_path(value: str) -> bool:
    """Recognize native and Windows absolute path spellings on every host."""

    return (
        Path(value).is_absolute()
        or ntpath.isabs(value)
        or PureWindowsPath(value).is_absolute()
    )


def _has_parent_escape(value: str) -> bool:
    """Return whether a token contains a repository-escaping path component."""

    normalized = value.replace("\\", "/")
    return any(part == ".." for part in normalized.split("/"))


def _validate_token(
    value: object,
    *,
    position: int | None = None,
    allow_fixed_container_path: bool = False,
) -> str:
    """Validate one argv element before it can reach a child process."""

    if not isinstance(value, str):
        location = f" at position {position}" if position is not None else ""
        raise ExecutionValidationError(f"command argument{location} must be a string")
    if not value or not value.strip():
        location = f" at position {position}" if position is not None else ""
        raise ExecutionValidationError(f"command argument{location} must not be empty")
    fixed_container_path = (
        allow_fixed_container_path and value in _SAFE_CONTAINER_PATH_TOKENS
    )
    fixed_container_mount = (
        allow_fixed_container_path and value == _DOCKER_TEST_DISPLAY_MOUNT
    )
    if _SHELL_OPERATOR.search(value) and not (fixed_container_path or fixed_container_mount):
        raise ExecutionValidationError("command contains a shell operator or control character")
    if _has_parent_escape(value) and not fixed_container_mount:
        raise ExecutionValidationError("command arguments must not escape the repository")
    if not fixed_container_path and (_is_absolute_path(value) or _EMBEDDED_ABSOLUTE.search(value)):
        raise ExecutionValidationError("absolute paths are not allowed in execution arguments")
    return value


def _normalize_argv(
    command: Sequence[str],
    *,
    allow_fixed_container_paths: bool = False,
) -> tuple[str, ...]:
    """Copy and validate a structured argv sequence."""

    if isinstance(command, (str, bytes, bytearray)) or not isinstance(command, Sequence):
        raise ExecutionValidationError("command must be a non-empty sequence of strings")
    values = tuple(
        _validate_token(
            value,
            position=index,
            allow_fixed_container_path=allow_fixed_container_paths,
        )
        for index, value in enumerate(command)
    )
    if not values:
        raise ExecutionValidationError("command must not be empty")
    return values


def _executable_name(value: str) -> str:
    """Return a case-folded executable basename without accepting a path."""

    return ntpath.basename(value).casefold()


def _validate_python_test_argv(argv: tuple[str, ...]) -> None:
    """Allow only direct Python unittest/pytest forms or the pytest launcher."""

    if "/" in argv[0] or "\\" in argv[0]:
        raise ExecutionValidationError(
            "test executable must be an allowlisted PATH command, not a repository script path"
        )
    executable = _executable_name(argv[0])
    if executable in _TEST_EXECUTABLES:
        return

    python_executable = bool(
        re.fullmatch(r"python(?:3(?:\.\d+)?)?(?:\.exe)?", executable)
        or executable == "py"
    )
    if not python_executable:
        raise ExecutionValidationError(
            "unsupported test command family; use python -m unittest, python -m pytest, or pytest"
        )

    index = 1
    if executable == "py" and index < len(argv) and re.fullmatch(r"-\d+(?:\.\d+)?", argv[index]):
        index += 1
    if len(argv) <= index + 1 or argv[index] != "-m":
        raise ExecutionValidationError(
            "Python test commands must use -m unittest or -m pytest"
        )
    module = argv[index + 1].casefold()
    if module not in {"unittest", "pytest"}:
        raise ExecutionValidationError(
            "unsupported Python module; only unittest and pytest are permitted"
        )


def _validate_test_argv(command: Sequence[str]) -> tuple[str, ...]:
    """Normalize and validate a supported test command."""

    argv = _normalize_argv(command)
    _validate_python_test_argv(argv)
    return argv


def _docker_test_display_argv(test_argv: Sequence[str]) -> tuple[str, ...]:
    """Wrap a validated test argv in the path-free Docker display command."""

    return _DOCKER_TEST_DISPLAY_PREFIX + tuple(test_argv)


def _validate_docker_test_display_argv(argv: tuple[str, ...]) -> None:
    """Reject direct Docker-test plans whose fixed safety flags were changed."""

    prefix_length = len(_DOCKER_TEST_DISPLAY_PREFIX)
    if len(argv) <= prefix_length or argv[:prefix_length] != _DOCKER_TEST_DISPLAY_PREFIX:
        raise ExecutionValidationError(
            "Docker test plan argv must use the fixed network-isolated runner"
        )
    _validate_test_argv(argv[prefix_length:])


def _docker_test_execution_argv(plan: "ExecutionPlan") -> tuple[str, ...]:
    """Build the private Docker argv with the real repository mount path."""

    mount = f"{os.fspath(plan.repository)}:/workspace:ro"
    return tuple(
        mount if token == _DOCKER_TEST_DISPLAY_MOUNT else token
        for token in plan.argv
    )


def _safe_plan_argv(argv: Sequence[str]) -> list[str]:
    """Return argv suitable for a report, redacting credential-shaped values."""

    result: list[str] = []
    redact_next = False
    for token in argv:
        # These are fixed container paths, not host paths.  Keep them visible
        # so a reviewer can verify the Docker workdir and temporary filesystem
        # without weakening the general receipt path-redaction rule.
        value = (
            token
            if token in _SAFE_CONTAINER_PATH_TOKENS
            else _sanitize_text(token, redact_paths=True)
        )
        if redact_next:
            result.append("<redacted>")
            redact_next = False
            continue
        if re.search(
            r"(?i)(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
            r"authorization|cookie|private[_ -]?key)",
            token,
        ):
            if "=" in token or ":" in token:
                key, _separator, _value = re.split(r"([=:])", token, maxsplit=1)
                result.append(f"{key}{_separator}<redacted>")
            else:
                result.append(value)
                redact_next = True
            continue
        result.append(value)
    return result


def _sanitize_text(value: object, *, redact_paths: bool = True) -> str:
    """Bound and sanitize text that may be displayed in a receipt."""

    text = str(value)
    text = _PRIVATE_KEY_BLOCK.sub("<redacted>", text)
    text = _SECRET_ASSIGNMENT.sub(r"<secret>\1<redacted>", text)
    text = _BEARER_VALUE.sub("Bearer <redacted>", text)
    text = _TOKEN_SHAPE.sub("<redacted-token>", text)
    if redact_paths:
        text = _WINDOWS_ABSOLUTE_TEXT.sub("<path>", text)
        text = _POSIX_ABSOLUTE_TEXT.sub("<path>", text)
        text = _HOME_ABSOLUTE_TEXT.sub("<path>", text)
    escaped: list[str] = []
    for character in text:
        if character in {"\n", "\t"}:
            escaped.append(character)
        elif character.isprintable() and character != "\x1b":
            escaped.append(character)
        else:
            escaped.append(f"\\u{ord(character):04x}")
    sanitized = "".join(escaped)
    if len(sanitized) > _OUTPUT_DETAIL_CHARS:
        return sanitized[: _OUTPUT_DETAIL_CHARS - 1] + "…"
    return sanitized


def _safe_label() -> str:
    """Return the only working-directory label exposed by this module."""

    return "repository"


def _docker_start_failed(
    exit_code: int | None,
    stdout_detail: str,
    stderr_detail: str,
) -> bool:
    """Recognize Docker client/daemon startup failures without hiding test failures.

    Docker uses exit code 125 for several startup failures, but a client whose
    daemon is unavailable can also return a regular non-zero code.  The latter
    is common on Windows when Docker Desktop is installed but its Linux engine
    is stopped.  Only known client/daemon messages are classified here; a
    container's own failing test command remains a normal ``failed`` result.
    """

    if exit_code == 125:
        return True
    output = f"{stdout_detail}\n{stderr_detail}".casefold()
    return any(marker in output for marker in _DOCKER_START_FAILURE_MARKERS)


@dataclass(frozen=True)
class ExecutionPlan:
    """Immutable, reviewable description of one supported execution.

    ``repository`` is retained for the runner but is deliberately omitted
    from :meth:`to_dict`; reports expose only the safe ``working_directory``
    label.  For an offline test plan, ``argv`` contains a path-free Docker
    display command; the real repository mount is assembled only in private
    execution data.  ``argv`` is a tuple so callers cannot mutate a plan after
    it has been reviewed.
    """

    repository: Path = field(repr=False, compare=False)
    kind: str
    argv: tuple[str, ...]
    working_directory_label: str
    network_mode: str
    timeout_seconds: int
    output_limit_bytes: int
    side_effect_notice: str
    candidate_source: str
    authorization_required: bool = True
    offline: bool = False
    runner: str | None = None
    isolation: str | None = None
    sandbox: str | None = None

    def __post_init__(self) -> None:
        """Normalize immutable values and reject malformed direct instances."""

        object.__setattr__(self, "repository", _canonical_repository(self.repository))
        normalized_kind = _normalize_kind(self.kind)
        object.__setattr__(self, "kind", normalized_kind)
        normalized_argv = _normalize_argv(
            self.argv,
            allow_fixed_container_paths=(normalized_kind == "tests" and self.offline),
        )
        object.__setattr__(self, "argv", normalized_argv)
        _validate_limit("timeout_seconds", self.timeout_seconds, MAX_TIMEOUT_SECONDS)
        _validate_limit(
            "output_limit_bytes", self.output_limit_bytes, MAX_OUTPUT_LIMIT_BYTES
        )
        if not isinstance(self.offline, bool):
            raise ExecutionValidationError("offline must be a boolean")
        if not isinstance(self.authorization_required, bool):
            raise ExecutionValidationError("authorization_required must be a boolean")
        expected_network = "none" if self.offline else "default"
        if self.network_mode != expected_network:
            raise ExecutionValidationError(
                f"network_mode must be {expected_network!r} for this plan"
            )
        expected_sandbox = _expected_sandbox(normalized_kind, self.offline)
        requested_runner = _normalize_sandbox(self.runner, field_name="runner")
        requested_isolation = _normalize_sandbox(
            self.isolation,
            field_name="isolation",
        )
        requested_sandbox = _normalize_sandbox(self.sandbox)
        for name, requested in (
            ("runner", requested_runner),
            ("isolation", requested_isolation),
            ("sandbox", requested_sandbox),
        ):
            if requested is not None and requested != expected_sandbox:
                raise ExecutionValidationError(
                    f"{name}={requested!r} is unsafe for this {normalized_kind} plan; "
                    f"expected {expected_sandbox!r}"
                )
        object.__setattr__(self, "runner", expected_sandbox)
        object.__setattr__(self, "isolation", expected_sandbox)
        object.__setattr__(self, "sandbox", expected_sandbox)
        object.__setattr__(self, "working_directory_label", _safe_label())
        object.__setattr__(self, "side_effect_notice", _sanitize_text(self.side_effect_notice))
        object.__setattr__(self, "candidate_source", _sanitize_text(self.candidate_source))
        if normalized_kind == "tests" and expected_sandbox == "docker":
            _validate_docker_test_display_argv(normalized_argv)
        elif normalized_kind == "tests":
            _validate_test_argv(normalized_argv)
        elif normalized_argv != (
            _DOCKER_OFFLINE_ARGV if self.offline else _DOCKER_ARGV
        ):
            raise ExecutionValidationError("docker build plan argv is fixed")

    @property
    def command(self) -> tuple[str, ...]:
        """Compatibility alias for callers that call structured argv a command."""

        return self.argv

    @property
    def requires_authorization(self) -> bool:
        """Compatibility alias for the explicit authorization requirement."""

        return self.authorization_required

    @property
    def working_directory(self) -> str:
        """Return the safe relative working-directory label."""

        return "."

    @property
    def display_argv(self) -> tuple[str, ...]:
        """Return the structured argv used by safe plan renderers."""

        return self.argv

    @property
    def isolation_mode(self) -> str:
        """Compatibility alias for callers that use an isolation-mode name."""

        return str(self.isolation)

    @property
    def runner_kind(self) -> str:
        """Compatibility alias for callers that use a runner-kind name."""

        return str(self.runner)

    @property
    def image(self) -> str | None:
        """Return the fixed image used by the Docker-isolated test runner."""

        if self.kind == "tests" and self.runner == "docker":
            return _DOCKER_TEST_IMAGE
        return None

    @property
    def resource_limits(self) -> dict[str, str]:
        """Return fixed Docker resource limits without host-specific data."""

        if self.kind == "tests" and self.runner == "docker":
            return dict(_DOCKER_TEST_RESOURCE_LIMITS)
        return {}

    @property
    def no_host_fallback(self) -> bool:
        """Whether this plan must never retry through the host runner."""

        return self.kind == "tests" and self.offline and self.runner == "docker"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe plan without absolute paths or secrets."""

        safe_argv = _safe_plan_argv(self.argv)
        no_host_fallback = self.no_host_fallback
        resource_limits = self.resource_limits
        return {
            "kind": _KindDisplay(self.kind),
            "normalized_kind": self.kind,
            "argv": safe_argv,
            "command": list(safe_argv),
            "display_argv": list(safe_argv),
            "working_directory": ".",
            "working_directory_label": self.working_directory_label,
            "network_mode": self.network_mode,
            "offline": self.offline,
            "runner": self.runner,
            "runner_kind": self.runner,
            "isolation": self.isolation,
            "isolation_mode": self.isolation,
            "sandbox": self.sandbox,
            "image": self.image,
            "repository_mount": {
                "source": "<repository>",
                "target": "/workspace",
                "read_only": self.runner == "docker" and self.kind == "tests",
            },
            "resource_limits": resource_limits,
            "limits": {
                "timeout_seconds": self.timeout_seconds,
                "output_limit_bytes": self.output_limit_bytes,
                **resource_limits,
            },
            "no_host_fallback": no_host_fallback,
            "host_fallback": False if no_host_fallback else self.runner == "host",
            "host_fallback_allowed": False if no_host_fallback else self.runner == "host",
            "fallback_policy": "none" if no_host_fallback else "selected_runner_only",
            "fallback": "none" if no_host_fallback else "selected_runner_only",
            "timeout_seconds": self.timeout_seconds,
            "output_limit_bytes": self.output_limit_bytes,
            "side_effect_notice": _sanitize_text(self.side_effect_notice),
            "candidate_source": _sanitize_text(self.candidate_source),
            "authorization_required": self.authorization_required,
            "requires_authorization": self.authorization_required,
        }


@dataclass(frozen=True)
class ExecutionReceipt:
    """Immutable truthful result of an authorized or denied execution attempt."""

    execution_id: str
    kind: str
    authorization: str
    authorized: bool
    executed: bool
    status: str
    candidate_source: str
    argv: tuple[str, ...]
    working_directory_label: str
    network_mode: str
    timeout_seconds: int
    output_limit_bytes: int
    exit_code: int | None = None
    termination_reason: str | None = None
    cleanup_status: str = "not_started"
    source_manifest_before: str | None = None
    source_manifest_after: str | None = None
    source_manifest_unchanged: bool | None = None
    manifest_comparison: str = "not_checked"
    stdout_digest: str | None = None
    stderr_digest: str | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    stdout_detail: str = ""
    stderr_detail: str = ""
    reason: str = ""
    limitation: str = ""
    runner: str = "host"
    isolation: str = "host"
    sandbox: str = "host"
    image: str | None = None
    no_host_fallback: bool = False

    def __post_init__(self) -> None:
        """Normalize sequence data so a receipt cannot be mutated in place."""

        object.__setattr__(self, "kind", _normalize_kind(self.kind))
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "working_directory_label", _safe_label())
        object.__setattr__(self, "candidate_source", _sanitize_text(self.candidate_source))
        object.__setattr__(self, "stdout_detail", _sanitize_text(self.stdout_detail))
        object.__setattr__(self, "stderr_detail", _sanitize_text(self.stderr_detail))
        object.__setattr__(self, "reason", _sanitize_text(self.reason))
        object.__setattr__(self, "limitation", _sanitize_text(self.limitation))
        normalized_runner = _normalize_sandbox(self.runner, field_name="runner")
        normalized_isolation = _normalize_sandbox(
            self.isolation,
            field_name="isolation",
        )
        normalized_sandbox = _normalize_sandbox(self.sandbox)
        object.__setattr__(self, "runner", normalized_runner or "host")
        object.__setattr__(self, "isolation", normalized_isolation or "host")
        object.__setattr__(self, "sandbox", normalized_sandbox or "host")
        object.__setattr__(self, "image", _sanitize_text(self.image) if self.image else None)
        if not isinstance(self.no_host_fallback, bool):
            raise ExecutionValidationError("no_host_fallback must be a boolean")

    @property
    def authorization_state(self) -> str:
        """Return the stable authorization-state spelling used by reports."""

        return self.authorization

    @property
    def observed_exit_code(self) -> int | None:
        """Return the exit code observed by the runner, if one exists."""

        return self.exit_code

    @property
    def manifest_unchanged(self) -> bool | None:
        """Return the source-manifest comparison result."""

        return self.source_manifest_unchanged

    @property
    def returncode(self) -> int | None:
        """Compatibility alias for callers using subprocess terminology."""

        return self.exit_code

    @property
    def output_bytes(self) -> int:
        """Return the bounded aggregate output count."""

        return min(self.stdout_bytes + self.stderr_bytes, self.output_limit_bytes)

    @property
    def output_limit(self) -> int:
        """Compatibility alias for the per-stream capture limit."""

        return self.output_limit_bytes

    def to_dict(self) -> dict[str, object]:
        """Return a bounded receipt with no repository path or raw secret output."""

        safe_argv = _safe_plan_argv(self.argv)
        bounded_output_bytes = min(
            self.stdout_bytes + self.stderr_bytes,
            self.output_limit_bytes,
        )
        output = {
            "limit_bytes": self.output_limit_bytes,
            "bytes": bounded_output_bytes,
            "stdout": {
                "digest": self.stdout_digest,
                "bytes": self.stdout_bytes,
                "truncated": self.stdout_truncated,
                "detail": _sanitize_text(self.stdout_detail),
            },
            "stderr": {
                "digest": self.stderr_digest,
                "bytes": self.stderr_bytes,
                "truncated": self.stderr_truncated,
                "detail": _sanitize_text(self.stderr_detail),
            },
        }
        source_manifest = {
            "before": self.source_manifest_before,
            "after": self.source_manifest_after,
            "before_digest": self.source_manifest_before,
            "after_digest": self.source_manifest_after,
            "unchanged": self.source_manifest_unchanged,
            "changed": (
                None
                if self.source_manifest_unchanged is None
                else not self.source_manifest_unchanged
            ),
            "comparison": self.manifest_comparison,
        }
        resource_limits = (
            dict(_DOCKER_TEST_RESOURCE_LIMITS)
            if self.kind == "tests" and self.runner == "docker"
            else {}
        )
        return {
            "execution_id": self.execution_id,
            "kind": _KindDisplay(self.kind),
            "normalized_kind": self.kind,
            "authorization": self.authorization,
            "authorization_state": self.authorization,
            "authorized": self.authorized,
            "executed": self.executed,
            "status": self.status,
            "result": self.status,
            "outcome": self.status,
            "candidate_source": _sanitize_text(self.candidate_source),
            "argv": safe_argv,
            "command": list(safe_argv),
            "working_directory": ".",
            "working_directory_label": self.working_directory_label,
            "network_mode": self.network_mode,
            "runner": self.runner,
            "runner_kind": self.runner,
            "isolation": self.isolation,
            "isolation_mode": self.isolation,
            "sandbox": self.sandbox,
            "image": self.image,
            "offline": self.network_mode == "none",
            "repository_mount": {
                "source": "<repository>",
                "target": "/workspace",
                "read_only": self.kind == "tests" and self.runner == "docker",
            },
            "resource_limits": resource_limits,
            "no_host_fallback": self.no_host_fallback,
            "host_fallback": False if self.no_host_fallback else self.runner == "host",
            "fallback_policy": "none" if self.no_host_fallback else "selected_runner_only",
            "fallback": "none" if self.no_host_fallback else "selected_runner_only",
            "timeout_seconds": self.timeout_seconds,
            "output_limit_bytes": self.output_limit_bytes,
            "limits": {
                "timeout_seconds": self.timeout_seconds,
                "output_limit_bytes": self.output_limit_bytes,
                **resource_limits,
            },
            "exit_code": self.exit_code,
            "observed_exit_code": self.exit_code,
            "termination_reason": self.termination_reason,
            "cleanup_status": self.cleanup_status,
            "source_manifest": source_manifest,
            "source_manifest_before": self.source_manifest_before,
            "source_manifest_after": self.source_manifest_after,
            "source_manifest_unchanged": self.source_manifest_unchanged,
            "manifest_unchanged": self.source_manifest_unchanged,
            "source_unchanged": self.source_manifest_unchanged,
            "manifest_comparison": self.manifest_comparison,
            "output": output,
            "stdout_digest": self.stdout_digest,
            "stderr_digest": self.stderr_digest,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "output_bytes": bounded_output_bytes,
            "captured_output_bytes": bounded_output_bytes,
            "total_output_bytes": bounded_output_bytes,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "stdout_detail": output["stdout"]["detail"],
            "stderr_detail": output["stderr"]["detail"],
            "reason": _sanitize_text(self.reason),
            "limitation": _sanitize_text(self.limitation),
        }


def _manifest_file_digest(path: str) -> str:
    """Hash one regular file in bounded chunks without loading it into memory."""

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, ValueError) as error:
        raise _ManifestError("source manifest could not read a regular file") from error
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except (OSError, ValueError) as error:
        raise _ManifestError("source manifest could not read a regular file") from error
    return digest.hexdigest()


def _collect_source_manifest(repository: Path) -> tuple[str, int]:
    """Return a digest/count for regular files below ``repository``.

    Directory symlinks and file symlinks are skipped rather than followed.
    Generated/cache directories are omitted so a normal test run's bytecode or
    framework cache is not mistaken for a source mutation.  The manifest
    includes relative path, size, mode, modification time, and content digest.
    """

    records: list[tuple[str, int, int, int, str]] = []
    total_bytes = 0
    stack: list[tuple[str, str]] = [(os.fspath(repository), "")]
    while stack:
        current, relative_directory = stack.pop()
        try:
            with os.scandir(current) as entries:
                ordered_entries = sorted(entries, key=lambda entry: entry.name)
        except (OSError, PermissionError) as error:
            raise _ManifestError("source manifest could not read the repository") from error

        for entry in ordered_entries:
            name = entry.name
            relative = f"{relative_directory}/{name}" if relative_directory else name
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if name not in _MANIFEST_EXCLUDED_DIRECTORIES:
                        stack.append((entry.path, relative))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                metadata_before = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(metadata_before.st_mode):
                    continue
                if len(records) >= _MAX_MANIFEST_FILES:
                    raise _ManifestError("source manifest file limit exceeded")
                if total_bytes + metadata_before.st_size > _MAX_MANIFEST_BYTES:
                    raise _ManifestError("source manifest byte limit exceeded")
                digest = _manifest_file_digest(entry.path)
                metadata_after = entry.stat(follow_symlinks=False)
                metadata = metadata_after if stat.S_ISREG(metadata_after.st_mode) else metadata_before
                if metadata.st_size != metadata_before.st_size and metadata.st_size < 0:
                    raise _ManifestError("source manifest observed invalid file metadata")
                total_bytes += int(metadata.st_size)
                records.append(
                    (
                        relative.replace("\\", "/"),
                        int(metadata.st_size),
                        int(metadata.st_mtime_ns),
                        int(metadata.st_mode & 0o7777),
                        digest,
                    )
                )
            except _ManifestError:
                raise
            except (OSError, PermissionError, ValueError) as error:
                raise _ManifestError("source manifest could not inspect a regular file") from error

    records.sort(key=lambda item: item[0])
    payload = json.dumps(records, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest(), len(records)


@dataclass
class _StreamCapture:
    """Private bounded reader used by the authorized process runner."""

    stream: object
    limit: int
    detail_limit: int = _OUTPUT_DETAIL_BYTES
    data: bytearray = field(default_factory=bytearray)
    digest: object = field(default_factory=hashlib.sha256)
    total_bytes: int = 0
    truncated: bool = False
    error: BaseException | None = None

    def read_to_end(self) -> None:
        """Drain a pipe while retaining only a small preview and a digest."""

        try:
            while True:
                chunk = self.stream.read(8192)  # type: ignore[union-attr]
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", "replace")
                if not isinstance(chunk, (bytes, bytearray)):
                    raise TypeError("process output stream returned a non-byte value")
                chunk_bytes = bytes(chunk)
                self.digest.update(chunk_bytes)
                self.total_bytes += len(chunk_bytes)
                if len(self.data) < self.detail_limit:
                    remaining = self.detail_limit - len(self.data)
                    self.data.extend(chunk_bytes[:remaining])
                if self.total_bytes > self.limit:
                    self.truncated = True
        except BaseException as error:  # pragma: no cover - pipe failures are platform-specific
            self.error = error

    def summary(self, repository: Path) -> tuple[str, int, bool, str]:
        """Return digest, byte count, truncation state, and safe preview."""

        detail = _sanitize_text(self.data.decode("utf-8", "replace"))
        repository_text = str(repository)
        if repository_text:
            detail = re.sub(re.escape(repository_text), "<repository>", detail, flags=re.IGNORECASE)
        return self.digest.hexdigest(), self.total_bytes, self.truncated, detail


def _execution_environment() -> dict[str, str]:
    """Build a small environment allowlist without copying host secrets."""

    allowed_names = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
    )
    environment = {
        name: os.environ[name]
        for name in allowed_names
        if name in os.environ and isinstance(os.environ[name], str)
    }
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    return environment


def _plan_digest(plan: ExecutionPlan, manifest: str | None = None) -> str:
    """Create a stable, path-free identifier for a plan attempt."""

    payload = {
        "kind": plan.kind,
        "argv": list(plan.argv),
        "network_mode": plan.network_mode,
        "runner": plan.runner,
        "isolation": plan.isolation,
        "sandbox": plan.sandbox,
        "image": plan.image,
        "timeout_seconds": plan.timeout_seconds,
        "output_limit_bytes": plan.output_limit_bytes,
        "manifest": manifest,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "cs-exec-" + hashlib.sha256(encoded.encode("ascii")).hexdigest()[:16]


def _empty_receipt(
    plan: ExecutionPlan,
    *,
    status: str,
    authorized: bool,
    executed: bool,
    reason: str,
    execution_id: str | None = None,
    source_manifest_before: str | None = None,
    source_manifest_after: str | None = None,
    source_manifest_unchanged: bool | None = None,
    manifest_comparison: str = "not_checked",
    cleanup_status: str = "not_started",
    termination_reason: str | None = None,
) -> ExecutionReceipt:
    """Construct a receipt for denial, unavailability, or preflight failure."""

    return ExecutionReceipt(
        execution_id=execution_id or _plan_digest(plan, source_manifest_before),
        kind=plan.kind,
        authorization="authorized" if authorized else "denied",
        authorized=authorized,
        executed=executed,
        status=status,
        candidate_source=plan.candidate_source,
        argv=plan.argv,
        working_directory_label=plan.working_directory_label,
        network_mode=plan.network_mode,
        timeout_seconds=plan.timeout_seconds,
        output_limit_bytes=plan.output_limit_bytes,
        runner=plan.runner or "host",
        isolation=plan.isolation or "host",
        sandbox=plan.sandbox or "host",
        image=plan.image,
        no_host_fallback=plan.no_host_fallback,
        exit_code=None,
        termination_reason=termination_reason,
        cleanup_status=cleanup_status,
        source_manifest_before=source_manifest_before,
        source_manifest_after=source_manifest_after,
        source_manifest_unchanged=source_manifest_unchanged,
        manifest_comparison=manifest_comparison,
        reason=reason,
        limitation=(
            "No process was started; an execution receipt cannot claim a passed verification."
            if not executed
            else "The execution did not produce a successful, unchanged-source verification."
        ),
    )


def build_execution_plan(
    repository: Path,
    kind: str,
    *,
    offline: bool = False,
    sandbox: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    command: Sequence[str] | None = None,
) -> ExecutionPlan:
    """Build a reviewable plan for a safe test command or Docker build.

    ``kind`` accepts ``"tests"`` and either ``"docker_build"`` or the CLI
    spelling ``"docker-build"``.  Tests use the deterministic stdlib
    ``python -m unittest discover`` default when ``repository/tests`` is a
    real directory; callers may instead provide a direct ``python -m
    unittest``, ``python -m pytest``, or ``pytest`` argv.  Make recipes,
    shell strings, wrappers, and arbitrary scripts are rejected.  Offline
    tests use a fixed Docker ``run`` argv with a path-free display mount;
    Docker's build argv is fixed by the plan and cannot be replaced by
    ``command``.  ``sandbox`` is optional compatibility input and accepts only
    the selected safe value (``host`` for online tests, ``docker`` for offline
    tests and Docker builds).

    This function is plan-only: it never calls :mod:`subprocess`, imports the
    repository, or writes a file.
    """

    normalized_kind = _normalize_kind(kind)
    resolved_repository = _canonical_repository(repository)
    if not isinstance(offline, bool):
        raise ExecutionValidationError("offline must be a boolean")
    requested_sandbox = _normalize_sandbox(sandbox)
    selected_sandbox = _expected_sandbox(normalized_kind, offline)
    if requested_sandbox is not None and requested_sandbox != selected_sandbox:
        raise ExecutionValidationError(
            f"sandbox={requested_sandbox!r} is unsafe for this plan; "
            f"expected {selected_sandbox!r}"
        )
    selected_timeout = _validate_limit(
        "timeout_seconds", timeout_seconds, MAX_TIMEOUT_SECONDS
    )
    selected_output_limit = _validate_limit(
        "output_limit_bytes", output_limit_bytes, MAX_OUTPUT_LIMIT_BYTES
    )

    if normalized_kind == "docker_build":
        if command is not None:
            requested = _normalize_argv(command)
            # Accept the two harmless documented spellings as input context,
            # but always replace them with the fixed tagged build below.
            if requested not in {
                ("docker", "build", "."),
                _DOCKER_ARGV,
                _DOCKER_OFFLINE_ARGV,
            }:
                raise ExecutionValidationError(
                    "docker build commands are fixed to docker build --tag coldstart-verification:local ."
                )
        argv = _DOCKER_OFFLINE_ARGV if offline else _DOCKER_ARGV
        candidate_source = "docker_build_default"
        side_effect_notice = (
            "An authorized Docker build may read the repository and change Docker daemon cache/state; "
            "ColdStart does not modify the repository."
        )
    else:
        if command is None:
            tests_directory = resolved_repository / "tests"
            if not tests_directory.is_dir() or tests_directory.is_symlink():
                raise ExecutionValidationError(
                    "no real tests directory exists; provide an explicit safe unittest or pytest command"
                )
            argv = _DEFAULT_TEST_ARGV
            candidate_source = "tests_directory_default"
        else:
            argv = _validate_test_argv(command)
            candidate_source = "explicit_safe_test_command"
        if offline:
            argv = _docker_test_display_argv(argv)
        side_effect_notice = (
            "An authorized test process may execute repository test code and may create or modify files; "
            "ColdStart detects source changes and does not revert them."
        )
        if offline:
            side_effect_notice = (
                "An authorized Docker test process runs with network=none, a read-only repository "
                "mount, fixed resource limits, and no host-runner fallback."
            )

    return ExecutionPlan(
        repository=resolved_repository,
        kind=normalized_kind,
        argv=tuple(argv),
        working_directory_label=_safe_label(),
        network_mode="none" if offline else "default",
        timeout_seconds=selected_timeout,
        output_limit_bytes=selected_output_limit,
        side_effect_notice=side_effect_notice,
        candidate_source=candidate_source,
        authorization_required=True,
        offline=offline,
        runner=selected_sandbox,
        isolation=selected_sandbox,
        sandbox=selected_sandbox,
    )


def _validate_plan_for_execution(plan: ExecutionPlan) -> None:
    """Recheck a plan at the execution boundary, including direct instances."""

    if not isinstance(plan, ExecutionPlan):
        raise ExecutionValidationError("plan must be an ExecutionPlan")
    if plan.kind == "docker_build":
        expected_argv = _DOCKER_OFFLINE_ARGV if plan.offline else _DOCKER_ARGV
        if plan.argv != expected_argv:
            raise ExecutionValidationError("docker build plan argv is fixed")
        if plan.runner != "docker" or plan.isolation != "docker" or plan.sandbox != "docker":
            raise ExecutionValidationError("docker build plan must use the Docker runner")
    elif plan.kind == "tests":
        if plan.offline:
            if plan.runner != "docker" or plan.isolation != "docker" or plan.sandbox != "docker":
                raise ExecutionValidationError(
                    "offline tests must use Docker isolation without a host fallback"
                )
            _validate_docker_test_display_argv(plan.argv)
        else:
            if plan.runner != "host" or plan.isolation != "host" or plan.sandbox != "host":
                raise ExecutionValidationError("online tests must use the host runner")
            _validate_test_argv(plan.argv)
    else:  # Defensive because frozen instances can still be constructed manually.
        raise ExecutionValidationError("unsupported execution kind")
    _canonical_repository(plan.repository)


def _terminate_process(process: subprocess.Popen[bytes]) -> str:
    """Terminate a timed-out process and report whether cleanup completed."""

    cleanup_errors = False
    try:
        if process.poll() is None:
            process.terminate()
    except (OSError, AttributeError):
        cleanup_errors = True
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except (OSError, AttributeError):
            cleanup_errors = True
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired, AttributeError):
            cleanup_errors = True
    except (OSError, AttributeError):
        cleanup_errors = True
    return "failed" if cleanup_errors else "completed"


def _close_capture_streams(
    process: subprocess.Popen[bytes],
    captures: Sequence[tuple[_StreamCapture, threading.Thread]],
) -> str:
    """Close pipe handles and join bounded reader threads."""

    cleanup_errors = False
    for capture, thread in captures:
        thread.join(timeout=2)
        if thread.is_alive():
            stream = capture.stream
            try:
                stream.close()  # type: ignore[union-attr]
            except (OSError, ValueError):
                cleanup_errors = True
            thread.join(timeout=1)
        if thread.is_alive() or capture.error is not None:
            cleanup_errors = True
    for stream_name in ("stdout", "stderr"):
        stream = getattr(process, stream_name, None)
        if stream is not None:
            try:
                stream.close()
            except (OSError, ValueError):
                cleanup_errors = True
    return "failed" if cleanup_errors else "completed"


def _run_authorized_process(plan: ExecutionPlan, execution_id: str) -> ExecutionReceipt:
    """Run one already validated plan and convert all outcomes to a receipt."""

    try:
        before_digest, _before_count = _collect_source_manifest(plan.repository)
    except _ManifestError:
        return _empty_receipt(
            plan,
            status="not_verified",
            authorized=True,
            executed=False,
            reason="Source manifest could not be collected before execution.",
            execution_id=execution_id,
            manifest_comparison="error",
            cleanup_status="not_started",
        )

    execution_id = _plan_digest(plan, before_digest)
    captures: list[tuple[_StreamCapture, threading.Thread]] = []
    process: subprocess.Popen[bytes] | None = None
    timed_out = False
    termination_reason: str | None = None
    exit_code: int | None = None
    cleanup_status = "not_started"
    launch_reason = ""
    execution_argv = (
        _docker_test_execution_argv(plan)
        if plan.kind == "tests" and plan.runner == "docker"
        else plan.argv
    )

    try:
        # ``shell=False`` is explicit even though it is the subprocess default.
        process = subprocess.Popen(
            list(execution_argv),
            shell=False,
            cwd=plan.repository,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=(os.name != "nt"),
            env=_execution_environment(),
        )
        for stream_name in ("stdout", "stderr"):
            stream = getattr(process, stream_name, None)
            if stream is None:
                continue
            capture = _StreamCapture(
                stream=stream,
                limit=plan.output_limit_bytes,
                detail_limit=min(plan.output_limit_bytes, _OUTPUT_DETAIL_BYTES),
            )
            thread = threading.Thread(target=capture.read_to_end, daemon=True)
            thread.start()
            captures.append((capture, thread))
        try:
            exit_code = process.wait(timeout=plan.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            termination_reason = "timeout"
            cleanup_status = _terminate_process(process)
            try:
                exit_code = process.poll()
            except (OSError, AttributeError):
                exit_code = None
    except FileNotFoundError:
        launch_reason = (
            "Docker is unavailable for network isolation because it is not installed "
            "or is not on PATH; no host fallback was attempted."
            if plan.runner == "docker" and plan.kind == "tests"
            else "Docker is unavailable because it is not installed or is not on PATH."
            if plan.kind == "docker_build"
            else "The requested executable is not installed or is not on PATH."
        )
        cleanup_status = "not_started"
    except PermissionError:
        launch_reason = (
            "Docker could not be started due to permissions; no host fallback was attempted."
            if plan.runner == "docker" and plan.kind == "tests"
            else "The requested executable could not be started due to permissions."
        )
        cleanup_status = "not_started"
    except (OSError, ValueError) as error:
        # Keep the public reason generic; an OS error can contain an absolute
        # host path or an environment value.
        launch_reason = (
            "Docker execution could not be started; no host fallback was attempted."
            if plan.runner == "docker" and plan.kind == "tests"
            else "The requested process could not be started."
        )
        cleanup_status = "failed" if process is not None else "not_started"
    finally:
        if process is not None and not timed_out:
            cleanup_status = _close_capture_streams(process, captures)
        elif process is not None:
            stream_cleanup = _close_capture_streams(process, captures)
            if cleanup_status != "failed":
                cleanup_status = stream_cleanup

    try:
        after_digest, _after_count = _collect_source_manifest(plan.repository)
    except _ManifestError:
        after_digest = None

    manifest_unchanged = (
        before_digest == after_digest if after_digest is not None else None
    )
    if after_digest is None:
        manifest_comparison = "error"
    elif manifest_unchanged:
        manifest_comparison = "unchanged"
    else:
        manifest_comparison = "changed"

    stdout_digest: str | None = None
    stderr_digest: str | None = None
    stdout_bytes = 0
    stderr_bytes = 0
    stdout_truncated = False
    stderr_truncated = False
    stdout_detail = ""
    stderr_detail = ""
    if captures:
        for capture, _thread in captures:
            digest, byte_count, truncated, detail = capture.summary(plan.repository)
            bounded_byte_count = min(byte_count, plan.output_limit_bytes)
            stream = "stdout" if stdout_digest is None else "stderr"
            if stream == "stdout":
                stdout_digest, stdout_bytes, stdout_truncated, stdout_detail = (
                    digest,
                    bounded_byte_count,
                    truncated,
                    detail,
                )
            else:
                stderr_digest, stderr_bytes, stderr_truncated, stderr_detail = (
                    digest,
                    bounded_byte_count,
                    truncated,
                    detail,
                )

    if launch_reason:
        status = "not_verified"
        reason = launch_reason
    elif timed_out:
        status = "timeout"
        reason = "The process exceeded the configured timeout and was terminated."
    elif exit_code is None:
        status = "error"
        reason = "The process did not produce an observed exit code."
    elif plan.runner == "docker" and _docker_start_failed(
        exit_code,
        stdout_detail,
        stderr_detail,
    ):
        status = "not_verified"
        if plan.kind == "tests" and plan.no_host_fallback:
            reason = (
                "Docker could not start the network-isolated operation; network isolation was "
                "unavailable and no host fallback was attempted."
            )
        else:
            reason = (
                "Docker could not start the requested operation (daemon or image unavailable); "
                "no host fallback was attempted."
            )
    elif exit_code != 0:
        status = "failed"
        reason = "The process exited with a nonzero status."
    elif manifest_unchanged is not True:
        status = "not_verified"
        reason = (
            "The process exited successfully, but the source manifest changed or could not be compared."
        )
    elif cleanup_status != "completed":
        status = "failed"
        reason = "The process exited successfully, but process-output cleanup was incomplete."
    else:
        status = "passed"
        reason = "The process exited with code 0 and the regular-file source manifest is unchanged."

    return ExecutionReceipt(
        execution_id=execution_id,
        kind=plan.kind,
        authorization="authorized",
        authorized=True,
        executed=process is not None,
        status=status,
        candidate_source=plan.candidate_source,
        argv=plan.argv,
        working_directory_label=plan.working_directory_label,
        network_mode=plan.network_mode,
        timeout_seconds=plan.timeout_seconds,
        output_limit_bytes=plan.output_limit_bytes,
        runner=plan.runner or "host",
        isolation=plan.isolation or "host",
        sandbox=plan.sandbox or "host",
        image=plan.image,
        no_host_fallback=plan.no_host_fallback,
        exit_code=exit_code,
        termination_reason=termination_reason,
        cleanup_status=cleanup_status,
        source_manifest_before=before_digest,
        source_manifest_after=after_digest,
        source_manifest_unchanged=manifest_unchanged,
        manifest_comparison=manifest_comparison,
        stdout_digest=stdout_digest,
        stderr_digest=stderr_digest,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        stdout_detail=stdout_detail,
        stderr_detail=stderr_detail,
        reason=reason,
        limitation=(
            "A passed receipt requires observed exit code 0, completed cleanup, and an unchanged source manifest."
            if status != "passed"
            else "Docker and test execution remain optional verification evidence, not universal reproducibility proof."
        ),
    )


def execute_execution_plan(
    plan: ExecutionPlan,
    *,
    authorize: bool,
) -> ExecutionReceipt:
    """Execute a plan only after explicit authorization and return a receipt.

    Denial returns before executable discovery, manifest reads, or
    :class:`subprocess.Popen`.  Authorized Docker plans first check for a
    ``docker`` executable and report ``not_verified`` when it is absent.
    Authorized test plans and Docker builds use bounded pipe readers, a hard
    timeout with termination, and a regular-file source-manifest comparison.
    A receipt is never ``passed`` unless an observed exit code is zero and the
    manifest is unchanged.
    """

    _validate_plan_for_execution(plan)
    if not isinstance(authorize, bool):
        raise ExecutionValidationError("authorize must be a boolean")
    if not authorize:
        return _empty_receipt(
            plan,
            status="denied",
            authorized=False,
            executed=False,
            reason="Execution was not authorized; no child process was started.",
        )

    if plan.runner == "docker" and shutil.which("docker") is None:
        if plan.kind == "tests" and plan.no_host_fallback:
            reason = (
                "Docker is unavailable for network isolation because it is not installed "
                "or is not on PATH; no host fallback was attempted."
            )
        else:
            reason = "Docker is unavailable because it is not installed or is not on PATH."
        return _empty_receipt(
            plan,
            status="not_verified",
            authorized=True,
            executed=False,
            reason=reason,
            cleanup_status="not_started",
        )
    if plan.kind == "tests" and plan.runner == "docker":
        # The Docker executable check above is intentionally separate from the
        # host executable check below.  An offline request can never fall back
        # to a direct host test command.
        return _run_authorized_process(plan, _plan_digest(plan))
    executable = _executable_name(plan.argv[0])
    if shutil.which(plan.argv[0]) is None and executable not in {"python", "python3", "py"}:
        return _empty_receipt(
            plan,
            status="unavailable",
            authorized=True,
            executed=False,
            reason="The requested test executable is not installed or is not on PATH.",
            cleanup_status="not_started",
        )
    return _run_authorized_process(plan, _plan_digest(plan))


__all__ = [
    "ExecutionPlan",
    "ExecutionReceipt",
    "ExecutionValidationError",
    "build_execution_plan",
    "execute_execution_plan",
]
