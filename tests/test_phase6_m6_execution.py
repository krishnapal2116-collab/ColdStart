"""Focused M6 tests for the authorized execution boundary."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from coldstart.execution import (  # noqa: E402
    ExecutionPlan,
    ExecutionReceipt,
    build_execution_plan,
    execute_execution_plan,
)


def _serialized(value: object) -> object:
    """Use the public serializer when present, with a dataclass fallback."""

    if isinstance(value, Mapping):
        return {str(key): _serialized(item) for key, item in value.items()}
    for method_name in ("to_dict", "as_dict", "serialize", "to_json", "as_json"):
        method = getattr(value, method_name, None)
        if callable(method):
            result = method()
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    return result
            return _serialized(result)
    if isinstance(value, (list, tuple)):
        return [_serialized(item) for item in value]
    try:
        attributes = vars(value)
    except TypeError:
        return value
    return {str(key): _serialized(item) for key, item in attributes.items()}


def _json(value: object) -> str:
    return json.dumps(_serialized(value), sort_keys=True, default=str)


def _field(value: object, *names: str) -> object:
    serialized = _serialized(value)
    if isinstance(serialized, Mapping):
        for name in names:
            if name in serialized:
                return serialized[name]
    for name in names:
        try:
            return getattr(value, name)
        except AttributeError:
            continue
    return None


def _manifest(repository: Path) -> dict[str, tuple[object, ...]]:
    """Capture source entries without following links or including host paths."""

    result: dict[str, tuple[object, ...]] = {}
    for path in sorted(repository.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(repository).as_posix()
        if "__pycache__" in Path(relative).parts:
            continue
        if path.is_symlink():
            result[relative] = ("symlink", path.readlink().as_posix())
        elif path.is_dir():
            result[relative] = ("directory",)
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
    return result


def _write_unittest_fixture(
    repository: Path,
    *,
    sleep_seconds: float = 0.0,
    marker: Path | None = None,
    pid_file: Path | None = None,
) -> Path:
    tests = repository / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    if marker is None:
        marker = repository / (
            "timeout-marker.txt" if sleep_seconds else "execution-marker.txt"
        )
    delay = f"time.sleep({sleep_seconds!r})\n" if sleep_seconds else ""
    pid_write = ""
    if pid_file is not None:
        pid_write = (
            f"Path({str(pid_file)!r}).write_text(str(os.getpid()), "
            "encoding='utf-8')\n"
        )
    test_source = (
        "import os\n"
        "import time\n"
        "import unittest\n"
        "from pathlib import Path\n\n"
        "class FixtureTests(unittest.TestCase):\n"
        "    def test_fixture_execution(self):\n"
        f"        {pid_write}"
        f"        {delay}"
        f"        Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
    )
    (tests / "test_fixture.py").write_text(test_source, encoding="utf-8")
    return marker


def _python_unittest_command() -> tuple[str, ...]:
    """The documented shell-free Python command accepted by the API."""

    return (
        "python",
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_*.py",
    )


def _temporary_path_spellings(repository: Path) -> set[str]:
    text = str(repository)
    return {text, repository.as_posix(), text.replace("\\", "/")}


def _process_is_running(pid: int) -> bool:
    """Use the portable signal-zero probe for a short-lived fixture process."""

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


class Phase6M6ExecutionTests(unittest.TestCase):
    def test_plan_uses_structured_argv_safe_display_and_normalized_docker_build(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-plan-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            (repository / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

            plan = build_execution_plan(repository, "docker-build", offline=True)

            self.assertIsInstance(plan, ExecutionPlan)
            normalized_kind = str(_field(plan, "kind", "operation"))
            self.assertEqual(normalized_kind.casefold().replace("_", "-"), "docker-build")
            argv = _field(plan, "argv", "command")
            self.assertIsInstance(argv, (tuple, list))
            self.assertTrue(argv)
            assert isinstance(argv, (tuple, list))
            self.assertTrue(all(isinstance(argument, str) for argument in argv))
            self.assertEqual(tuple(argv[:2]), ("docker", "build"))
            self.assertIn(".", argv)

            authorization = _field(
                plan,
                "authorization_required",
                "requires_authorization",
                "requires_approval",
            )
            self.assertIn(authorization, (True, "required", "explicit"))

            display = _field(
                plan,
                "display_argv",
                "display_command",
                "safe_display",
                "display",
                "command_display",
                "display_data",
                "safe_command",
                "safe_argv",
                "working_directory",
                "working_directory_label",
            )
            self.assertIsNotNone(display)
            display_text = _json(display)
            self.assertIn(".", display_text)
            self.assertIn("docker", _json(plan).casefold())
            self.assertNotIn("&&", _json(plan))
            for spelling in _temporary_path_spellings(repository):
                self.assertNotIn(spelling, _json(plan))

    def test_unauthorized_execution_is_denied_without_running_fixture(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-denied-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            marker = Path(temporary) / "execution-marker.txt"
            _write_unittest_fixture(repository, marker=marker)
            before = _manifest(repository)
            plan = build_execution_plan(
                repository,
                "tests",
                offline=True,
                command=_python_unittest_command(),
            )

            receipt = execute_execution_plan(plan, authorize=False)

            self.assertIsInstance(receipt, ExecutionReceipt)
            status = _field(receipt, "status", "outcome", "result")
            self.assertEqual(status, "denied")
            self.assertFalse(marker.exists())
            self.assertEqual(before, _manifest(repository))

    def test_authorized_unittest_passes_with_bounded_receipt_and_unchanged_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-pass-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            marker = Path(temporary) / "execution-marker.txt"
            _write_unittest_fixture(repository, marker=marker)
            before = _manifest(repository)
            plan = build_execution_plan(
                repository,
                "tests",
                offline=False,
                timeout_seconds=10,
                output_limit_bytes=1024,
                command=_python_unittest_command(),
            )

            receipt = execute_execution_plan(plan, authorize=True)

            self.assertIsInstance(receipt, ExecutionReceipt)
            self.assertEqual(_field(receipt, "status", "outcome", "result"), "passed")
            self.assertEqual(
                _field(
                    receipt,
                    "observed_exit_code",
                    "exit_code",
                    "returncode",
                    "observed_exit",
                    "exit_status",
                ),
                0,
            )
            output_limit = _field(
                receipt,
                "output_limit_bytes",
                "output_limit",
            )
            output_bytes = _field(
                receipt,
                "output_bytes",
                "captured_output_bytes",
                "total_output_bytes",
            )
            output = _field(receipt, "output", "output_metadata", "output_limits")
            if isinstance(output, Mapping):
                output_limit = output_limit or output.get("limit_bytes", output.get("limit"))
                output_bytes = output_bytes or output.get("bytes", output.get("captured_bytes"))
                if output_bytes is None:
                    stream_bytes = [
                        stream.get("bytes")
                        for stream in (output.get("stdout"), output.get("stderr"))
                        if isinstance(stream, Mapping) and stream.get("bytes") is not None
                    ]
                    if stream_bytes:
                        output_bytes = sum(int(byte_count) for byte_count in stream_bytes)
            self.assertIsNotNone(output_limit)
            self.assertIsNotNone(output_bytes)
            assert output_limit is not None
            assert output_bytes is not None
            self.assertEqual(int(output_limit), 1024)
            self.assertLessEqual(int(output_bytes), int(output_limit))

            unchanged = _field(
                receipt,
                "source_manifest_unchanged",
                "manifest_unchanged",
                "source_unchanged",
            )
            if unchanged is None:
                manifest = _field(
                    receipt,
                    "source_manifest",
                    "source_manifest_comparison",
                    "manifest",
                )
                if isinstance(manifest, Mapping):
                    unchanged = manifest.get("unchanged", manifest.get("changed") is False)
                elif manifest is not None:
                    unchanged = str(manifest).casefold() in {"unchanged", "same"}
            self.assertTrue(unchanged)
            self.assertEqual(before, _manifest(repository))
            self.assertTrue(marker.exists())

    def test_offline_test_request_is_not_verified_without_network_isolation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-offline-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            marker = Path(temporary) / "offline-marker.txt"
            _write_unittest_fixture(repository, marker=marker)
            plan = build_execution_plan(
                repository,
                "tests",
                offline=True,
                command=_python_unittest_command(),
            )

            receipt = execute_execution_plan(plan, authorize=True)

        self.assertEqual(receipt.status, "not_verified")
        self.assertIn("network isolation", receipt.reason)
        self.assertFalse(marker.exists())

    def test_shell_operators_and_unsupported_commands_are_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-reject-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            marker = repository / "rejected-marker.txt"

            with self.assertRaises(ValueError):
                build_execution_plan(
                    repository,
                    "tests",
                    command=(
                        "python",
                        "-m",
                        "unittest",
                        "&&",
                        "touch",
                        marker.name,
                    ),
                )
            self.assertFalse(marker.exists())

            with self.assertRaises(ValueError):
                build_execution_plan(
                    repository,
                    "tests",
                    command=("coldstart-unsupported-command", marker.name),
                )
            self.assertFalse(marker.exists())

    def test_timeout_is_incomplete_and_leaves_no_late_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-timeout-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            marker = Path(temporary) / "timeout-marker.txt"
            pid_file = Path(temporary) / "timeout.pid"
            _write_unittest_fixture(
                repository,
                sleep_seconds=2.0,
                marker=marker,
                pid_file=pid_file,
            )
            before = _manifest(repository)
            plan = build_execution_plan(
                repository,
                "tests",
                offline=False,
                timeout_seconds=1,
                output_limit_bytes=1024,
                command=_python_unittest_command(),
            )

            receipt = execute_execution_plan(plan, authorize=True)
            time.sleep(2.5)

            status = str(_field(receipt, "status", "outcome", "result")).casefold()
            reason = str(
                _field(
                    receipt,
                    "termination_reason",
                    "reason",
                    "termination",
                    "error",
                )
            ).casefold()
            self.assertIn(status, {"timeout", "timed_out", "incomplete"})
            self.assertTrue("timeout" in status or "timeout" in reason)
            self.assertFalse(marker.exists())
            self.assertEqual(before, _manifest(repository))
            self.assertTrue(pid_file.exists())
            self.assertFalse(_process_is_running(int(pid_file.read_text(encoding="utf-8"))))

            cleanup = _field(receipt, "cleanup_status", "cleanup")
            if cleanup is not None:
                self.assertNotIn("running", _json(cleanup).casefold())
                self.assertNotIn("leaked", _json(cleanup).casefold())

    def test_missing_docker_is_unavailable_without_host_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-docker-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            (repository / "Dockerfile").write_text(
                "FROM scratch\nRUN touch host-fallback-marker.txt\n",
                encoding="utf-8",
            )
            marker = repository / "host-fallback-marker.txt"
            empty_path = repository / "empty-bin"
            empty_path.mkdir()
            original_path = os.environ.get("PATH")
            os.environ["PATH"] = str(empty_path)
            try:
                plan = build_execution_plan(
                    repository,
                    "docker-build",
                    offline=True,
                )
                receipt = execute_execution_plan(plan, authorize=True)
            finally:
                if original_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = original_path

            serialized = _json(receipt).casefold()
            status = str(_field(receipt, "status", "outcome", "result")).casefold()
            self.assertIn(status, {"not_verified", "unavailable"})
            self.assertTrue(
                "unavailable" in serialized
                or "not available" in serialized
                or "not installed" in serialized
            )
            self.assertFalse(marker.exists())
            self.assertNotIn("host-fallback", serialized)

    def test_receipt_serialization_does_not_expose_temporary_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-receipt-") as temporary:
            repository = Path(temporary) / "fixture"
            repository.mkdir()
            _write_unittest_fixture(repository, marker=Path(temporary) / "execution-marker.txt")
            plan = build_execution_plan(
                repository,
                "tests",
                offline=True,
                command=_python_unittest_command(),
            )
            receipt = execute_execution_plan(plan, authorize=True)
            serialized = _json(receipt)

            self.assertIsInstance(receipt, ExecutionReceipt)
            for spelling in _temporary_path_spellings(repository):
                self.assertNotIn(spelling, serialized)
            self.assertNotIn(str(repository.parent), serialized)


if __name__ == "__main__":
    unittest.main()
