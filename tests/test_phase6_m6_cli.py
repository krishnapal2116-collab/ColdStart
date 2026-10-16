"""CLI integration tests for the explicit M6 verification boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(SRC) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.run(
        [sys.executable, "-m", "coldstart", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def fixture_repository(parent: Path) -> Path:
    repository = parent / "fixture-project"
    (repository / "tests").mkdir(parents=True)
    (repository / ".python-version").write_text("3.12.8\n", encoding="utf-8")
    (repository / "requirements.lock").write_text(
        "# This fixture has no third-party dependencies.\n", encoding="utf-8"
    )
    (repository / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'fixture-project'\n"
        "version = '0.1.0'\n"
        "requires-python = '>=3.12,<3.13'\n"
        "dependencies = []\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        "# Fixture project\n\n"
        "## Prerequisites\n\nUse Python 3.12.8.\n\n"
        "## Install\n\nNo external dependencies are required.\n\n"
        "## Configuration\n\nNo external configuration is required.\n\n"
        "## Run\n\npython -m fixture_project\n\n"
        "## Test\n\npython -m unittest discover -s tests -p 'test_*.py'\n",
        encoding="utf-8",
    )
    (repository / "tests" / "test_fixture.py").write_text(
        "import unittest\n"
        "from pathlib import Path\n\n"
        "class FixtureTests(unittest.TestCase):\n"
        "    def test_authorized_execution_can_be_observed(self):\n"
        "        marker = Path('__pycache__') / 'execution-marker.txt'\n"
        "        marker.parent.mkdir(exist_ok=True)\n"
        "        marker.write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )
    return repository


def load_report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if not result.stdout.strip():
        raise AssertionError(f"expected JSON report; stderr was {result.stderr!r}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise AssertionError("expected a JSON report object")
    return value


class Phase6M6CliTests(unittest.TestCase):
    def test_plan_only_preview_never_starts_a_child_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-cli-plan-") as temporary:
            parent = Path(temporary)
            repository = fixture_repository(parent)
            marker = repository / "__pycache__" / "execution-marker.txt"

            result = run_cli(
                "verify",
                str(repository),
                "--kind",
                "tests",
                "--offline",
                "--plan",
                "--format",
                "json",
            )

            report = load_report(result)

        self.assertEqual(result.returncode, 0, result.stderr)
        verification = report["verification"]
        self.assertIsInstance(verification, dict)
        assert isinstance(verification, dict)
        self.assertEqual(verification["status"], "planned")
        self.assertEqual(verification["executions"], [])
        self.assertFalse(marker.exists())

    def test_missing_authorization_is_denied_without_running_project_tests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-cli-denied-") as temporary:
            parent = Path(temporary)
            repository = fixture_repository(parent)
            marker = repository / "__pycache__" / "execution-marker.txt"

            result = run_cli(
                "verify",
                str(repository),
                "--kind",
                "tests",
                "--format",
                "json",
            )
            report = load_report(result)

        self.assertEqual(result.returncode, 3, result.stderr)
        verification = report["verification"]
        self.assertIsInstance(verification, dict)
        assert isinstance(verification, dict)
        self.assertEqual(verification["status"], "denied")
        self.assertFalse(marker.exists())

    def test_explicit_authorization_returns_an_observed_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-cli-authorized-") as temporary:
            parent = Path(temporary)
            repository = fixture_repository(parent)
            marker = repository / "__pycache__" / "execution-marker.txt"

            result = run_cli(
                "verify",
                str(repository),
                "--kind",
                "tests",
                "--authorize",
                "--format",
                "json",
            )
            report = load_report(result)
            self.assertTrue(marker.exists())

        self.assertEqual(result.returncode, 0, result.stderr)
        verification = report["verification"]
        self.assertIsInstance(verification, dict)
        assert isinstance(verification, dict)
        self.assertEqual(verification["status"], "passed")
        executions = verification["executions"]
        self.assertIsInstance(executions, list)
        assert isinstance(executions, list)
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0]["exit_code"], 0)

    def test_terminal_report_exposes_plan_and_denial_without_control_sequences(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-cli-terminal-") as temporary:
            parent = Path(temporary)
            repository = fixture_repository(parent)
            marker = repository / "__pycache__" / "execution-marker.txt"

            result = run_cli(
                "verify",
                str(repository),
                "--kind",
                "tests",
                "--offline",
            )

        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("Verification plan:", result.stdout)
        self.assertIn("Execution receipt: status=denied", result.stdout)
        self.assertNotIn("\x1b[", result.stdout)

    def test_invalid_verification_limit_is_usage_error_without_a_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-cli-limit-") as temporary:
            parent = Path(temporary)
            repository = fixture_repository(parent)

            result = run_cli(
                "verify",
                str(repository),
                "--kind",
                "tests",
                "--timeout",
                "0",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("positive integer", result.stderr)


if __name__ == "__main__":
    unittest.main()
