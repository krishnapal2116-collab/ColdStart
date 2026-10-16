"""P0/demo acceptance tests for the committed Python example repositories."""

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
EXAMPLES = ROOT / "examples"


def run_audit(repository: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(SRC) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "coldstart",
            "audit",
            str(repository),
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def load_report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if not result.stdout.strip():
        raise AssertionError(f"expected JSON report; stderr was {result.stderr!r}")
    report = json.loads(result.stdout)
    if not isinstance(report, dict):
        raise AssertionError("expected a JSON report object")
    return report


def finding_statuses(report: dict[str, object]) -> dict[str, str]:
    raw_findings = report.get("findings")
    if not isinstance(raw_findings, list):
        raise AssertionError("report findings must be a list")
    statuses: dict[str, str] = {}
    for finding in raw_findings:
        if not isinstance(finding, dict):
            raise AssertionError("report findings must contain objects")
        check_id = finding.get("check_id")
        status = finding.get("status")
        if not isinstance(check_id, str) or not isinstance(status, str):
            raise AssertionError("finding check_id and status must be strings")
        statuses[check_id] = status
    return statuses


def fixture_manifest(repository: Path) -> dict[str, bytes | None]:
    manifest: dict[str, bytes | None] = {}
    for path in sorted(repository.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(repository).as_posix()
        if path.is_file():
            manifest[f"file:{relative}"] = path.read_bytes()
        elif path.is_dir():
            manifest[f"directory:{relative}"] = None
    return manifest


class Phase6M6ExampleTests(unittest.TestCase):
    def test_clean_python_fixture_is_static_pass_without_mutation(self) -> None:
        repository = EXAMPLES / "clean-python"
        before = fixture_manifest(repository)

        with tempfile.TemporaryDirectory(prefix="coldstart-m6-clean-"):
            result = run_audit(repository)
            report = load_report(result)

        statuses = finding_statuses(report)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("failed", statuses.values())
        self.assertNotIn("error", statuses.values())
        self.assertEqual(
            statuses["CS-RUNTIME-001"],
            "passed",
        )
        self.assertEqual(statuses["CS-DEPS-001"], "passed")
        self.assertEqual(statuses["CS-DEPS-002"], "not_applicable")
        self.assertEqual(before, fixture_manifest(repository))
        self.assertFalse((repository / "clean-python-execution.marker").exists())

    def test_defective_python_fixture_reports_expected_findings_without_execution(self) -> None:
        repository = EXAMPLES / "defective-python"
        before = fixture_manifest(repository)

        with tempfile.TemporaryDirectory(prefix="coldstart-m6-defective-"):
            result = run_audit(repository)
            report = load_report(result)

        statuses = finding_statuses(report)
        expected_failures = {
            "CS-DEPS-002": "failed",
            "CS-RUNTIME-001": "failed",
            "CS-DOCS-001": "failed",
            "CS-DOCS-002": "failed",
            "CS-CONFIG-001": "failed",
            "CS-CONFIG-002": "failed",
            "CS-PORT-001": "failed",
            "CS-BUILD-001": "failed",
        }

        self.assertEqual(result.returncode, 1, result.stderr)
        for check_id, expected_status in expected_failures.items():
            self.assertEqual(statuses.get(check_id), expected_status, check_id)
        self.assertEqual(before, fixture_manifest(repository))
        self.assertFalse(
            (repository / "defective-python-execution.marker").exists()
        )


if __name__ == "__main__":
    unittest.main()
