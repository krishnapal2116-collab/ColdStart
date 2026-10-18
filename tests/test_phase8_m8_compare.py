"""Acceptance tests for deterministic offline report comparison."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
EXAMPLE_PATH = ROOT / "docs" / "contracts" / "report-v1.example.json"
EXAMPLE_REPORT = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


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


def finding(
    check_id: str,
    *,
    severity: str = "info",
    status: str = "passed",
    message: str = "stable message",
) -> dict[str, object]:
    value = copy.deepcopy(EXAMPLE_REPORT["findings"][0])
    value.update(
        {
            "check_id": check_id,
            "severity": severity,
            "status": status,
            "title": f"Title for {check_id}",
            "message": message,
            "evidence": [
                {
                    "kind": "file",
                    "path": "README.md",
                    "line_start": 1,
                    "line_end": 1,
                    "detail": "stable evidence",
                    "digest": None,
                }
            ],
            "remediation": [],
            "affected_path": "README.md",
            "category": "project",
            "applicability": {
                "applicable": True,
                "reason": "The fixture is a project.",
                "adapter": "generic",
            },
            "rule_version": "1",
            "evidence_strength": "direct",
        }
    )
    return value


def report(
    findings: list[dict[str, object]],
    *,
    fingerprint: str = "a" * 64,
) -> dict[str, object]:
    value = copy.deepcopy(EXAMPLE_REPORT)
    value["findings"] = findings
    value["repository"]["audit_fingerprint"] = fingerprint
    return value


class Phase8M8CompareTests(unittest.TestCase):
    def write_pair(
        self,
        current: dict[str, object],
        baseline: dict[str, object],
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary_directory = tempfile.TemporaryDirectory(prefix="coldstart-m8-compare-")
        root = Path(temporary_directory.name)
        current_path = root / "current.json"
        baseline_path = root / "baseline.json"
        current_path.write_text(json.dumps(current), encoding="utf-8")
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        return temporary_directory, current_path, baseline_path

    def test_identical_reports_are_unchanged(self) -> None:
        value = report([finding("CS-PROJECT-001")])
        temporary_directory, current_path, baseline_path = self.write_pair(value, value)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path), "--format", "json")
        document = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(document["fingerprint"]["comparison"], "unchanged")
        self.assertEqual(document["summary"], {"added": 0, "resolved": 0, "unchanged": 1, "changed": 0})

    def test_all_change_categories_and_worsened_direction_are_reported(self) -> None:
        baseline = report(
            [
                finding("CS-UNCHANGED-001"),
                finding("CS-CHANGED-001", severity="warning", status="passed"),
                finding("CS-RESOLVED-001"),
            ]
        )
        current = report(
            [
                finding("CS-CHANGED-001", severity="error", status="failed"),
                finding("CS-UNCHANGED-001"),
                finding("CS-ADDED-001", severity="warning", status="not_verified"),
            ]
        )
        temporary_directory, current_path, baseline_path = self.write_pair(current, baseline)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path), "--format", "json")
        document = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(document["summary"], {"added": 1, "resolved": 1, "unchanged": 1, "changed": 1})
        self.assertEqual(document["changes"]["added"][0]["check_id"], "CS-ADDED-001")
        self.assertEqual(document["changes"]["resolved"][0]["check_id"], "CS-RESOLVED-001")
        self.assertEqual(document["changes"]["changed"][0]["direction"], "worsened")
        self.assertEqual(
            document["changes"]["changed"][0]["changed_fields"],
            ["severity", "status"],
        )

    def test_fingerprint_can_change_when_findings_are_unchanged(self) -> None:
        baseline = report([finding("CS-PROJECT-001")], fingerprint="a" * 64)
        current = report([finding("CS-PROJECT-001")], fingerprint="b" * 64)
        temporary_directory, current_path, baseline_path = self.write_pair(current, baseline)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path), "--format", "json")
        document = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(document["fingerprint"]["comparison"], "changed")
        self.assertEqual(document["summary"]["unchanged"], 1)
        self.assertEqual(document["summary"]["changed"], 0)

    def test_comparison_does_not_echo_full_finding_evidence(self) -> None:
        sensitive_message = "SECRET-VALUE-" + ("x" * 5000)
        current = report(
            [finding("CS-ADDED-001", message=sensitive_message)],
        )
        baseline = report([])
        temporary_directory, current_path, baseline_path = self.write_pair(current, baseline)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path), "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("SECRET-VALUE-", result.stdout)
        self.assertNotIn("x" * 1000, result.stdout)

    def test_finding_order_does_not_change_json_result(self) -> None:
        baseline = report([finding("CS-B-001"), finding("CS-A-001")])
        current = report([finding("CS-A-001"), finding("CS-B-001")])
        temporary_directory, current_path, baseline_path = self.write_pair(current, baseline)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path), "--format", "json")
        document = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(document["summary"]["unchanged"], 2)
        self.assertEqual([item["check_id"] for item in document["changes"]["unchanged"]], ["CS-A-001", "CS-B-001"])

    def test_improved_direction_is_reported(self) -> None:
        baseline = report([finding("CS-CHANGED-001", severity="error", status="failed")])
        current = report([finding("CS-CHANGED-001", severity="info", status="passed")])
        temporary_directory, current_path, baseline_path = self.write_pair(current, baseline)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path), "--format", "json")
        document = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(document["changes"]["changed"][0]["direction"], "improved")

    def test_terminal_output_exposes_categories_and_fingerprints(self) -> None:
        value = report([finding("CS-PROJECT-001")])
        temporary_directory, current_path, baseline_path = self.write_pair(value, value)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ColdStart report comparison", result.stdout)
        self.assertIn("Current fingerprint:", result.stdout)
        self.assertIn("Summary: added=0 resolved=0 unchanged=1 changed=0", result.stdout)
        self.assertIn("Exit code: 0", result.stdout)

    def test_output_file_contains_the_selected_format(self) -> None:
        value = report([finding("CS-PROJECT-001")])
        temporary_directory, current_path, baseline_path = self.write_pair(value, value)
        self.addCleanup(temporary_directory.cleanup)
        output_path = Path(temporary_directory.name) / "comparison.json"

        result = run_cli(
            "compare",
            str(current_path),
            str(baseline_path),
            "--format",
            "json",
            "--output",
            str(output_path),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["unchanged"], 1)

    def test_incompatible_reports_fail_without_comparison_json(self) -> None:
        current = report([finding("CS-PROJECT-001")])
        baseline = report([finding("CS-PROJECT-001")])
        baseline["tool"]["catalog_version"] = "p0-incompatible"
        temporary_directory, current_path, baseline_path = self.write_pair(current, baseline)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path), "--format", "json")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("incompatible", result.stderr)

    def test_duplicate_check_ids_fail_closed(self) -> None:
        value = report([finding("CS-PROJECT-001"), finding("CS-PROJECT-001")])
        temporary_directory, current_path, baseline_path = self.write_pair(value, value)
        self.addCleanup(temporary_directory.cleanup)

        result = run_cli("compare", str(current_path), str(baseline_path))

        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate check ID", result.stderr)

    def test_malformed_report_does_not_leak_the_input_path(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory(prefix="coldstart-m8-malformed-")
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        current_path = root / "current.json"
        baseline_path = root / "baseline.json"
        current_path.write_text("not json", encoding="utf-8")
        baseline_path.write_text("not json", encoding="utf-8")

        result = run_cli("compare", str(current_path), str(baseline_path))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("current report is not valid UTF-8 JSON", result.stderr)
        self.assertNotIn(str(root), result.stderr)
        self.assertNotIn("\x1b", result.stderr)

    def test_compare_does_not_call_the_audit_pipeline(self) -> None:
        value = report([finding("CS-PROJECT-001")])
        temporary_directory, current_path, baseline_path = self.write_pair(value, value)
        self.addCleanup(temporary_directory.cleanup)
        from coldstart import cli

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "run_audit", side_effect=AssertionError("audit called")),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(
                ["compare", str(current_path), str(baseline_path), "--format", "json"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"comparison_schema_version":"1.0"', stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_comparison_contract_artifacts_have_expected_shape(self) -> None:
        schema = json.loads(
            (ROOT / "docs" / "contracts" / "comparison-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        example = json.loads(
            (ROOT / "docs" / "contracts" / "comparison-v1.example.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(schema["$id"], "urn:coldstart:comparison:1.0")
        self.assertEqual(example["comparison_schema_version"], "1.0")
        self.assertEqual(example["invocation"]["command"], "compare")
        self.assertEqual(
            set(example["changes"]),
            {"added", "resolved", "unchanged", "changed"},
        )

    def test_help_lists_compare_command(self) -> None:
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("compare", result.stdout)


if __name__ == "__main__":
    unittest.main()
