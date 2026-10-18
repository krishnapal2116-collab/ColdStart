"""Acceptance tests for the offline P1 rule-explanation command."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from coldstart.catalog import CATALOG_CHECK_IDS
from coldstart.explanation import all_explanations, explanation_for


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REQUIRED_SECTIONS = (
    "ColdStart rule explanation",
    "Check:",
    "Default severity:",
    "Category:",
    "Adapters:",
    "Applicability:",
    "Purpose:",
    "Algorithm:",
    "Evidence:",
    "Limitations:",
    "Remediation:",
    "Test references:",
)


def run_cli(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(SRC) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.run(
        [sys.executable, "-m", "coldstart", *arguments],
        cwd=cwd or ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class Phase7M7ExplainTests(unittest.TestCase):
    def test_every_registered_check_has_complete_explanation_metadata(self) -> None:
        explanations = all_explanations()

        self.assertEqual(len(explanations), len(CATALOG_CHECK_IDS))
        self.assertEqual(
            tuple(item.check_id for item in explanations),
            CATALOG_CHECK_IDS,
        )
        for explanation in explanations:
            for field in (
                explanation.purpose,
                explanation.applicability,
                explanation.algorithm,
                explanation.evidence,
                explanation.limitations,
                explanation.remediation,
            ):
                self.assertTrue(field.strip(), explanation.check_id)
            self.assertGreater(len(explanation.test_references), 0)

    def test_each_registered_check_is_available_through_the_cli(self) -> None:
        for check_id in CATALOG_CHECK_IDS:
            result = run_cli("explain", check_id)

            self.assertEqual(result.returncode, 0, f"{check_id}: {result.stderr}")
            self.assertIn(f"Check: {check_id} --", result.stdout)
            self.assertEqual(result.stderr, "")

    def test_explanation_output_contains_all_contract_sections(self) -> None:
        result = run_cli("explain", "CS-DEPS-001")

        self.assertEqual(result.returncode, 0, result.stderr)
        for section in REQUIRED_SECTIONS:
            self.assertIn(section, result.stdout)
        self.assertIn("Dependency declaration discovery", result.stdout)
        self.assertIn("tests/test_phase3_m3_dependencies.py", result.stdout)

    def test_unknown_check_id_is_a_usage_error_without_stdout(self) -> None:
        result = run_cli("explain", "CS-NOT-REAL-999")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown check ID", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_explain_does_not_require_a_repository(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m7-explain-") as directory:
            result = run_cli(
                "explain",
                "CS-RUNTIME-001",
                cwd=Path(directory),
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Runtime version declaration", result.stdout)

    def test_repeated_explanations_are_byte_for_byte_deterministic(self) -> None:
        first = run_cli("explain", "CS-PATH-001")
        second = run_cli("explain", "CS-PATH-001")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, second.stderr)

    def test_explain_does_not_call_the_audit_pipeline(self) -> None:
        from coldstart import cli

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "run_audit", side_effect=AssertionError("audit called")),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(["explain", "CS-SEC-001"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Potential secret exposure indicator", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_help_lists_explain_command(self) -> None:
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("explain", result.stdout)

    def test_unknown_check_lookup_is_not_silently_coerced(self) -> None:
        with self.assertRaises(ValueError):
            explanation_for("cs-deps-001")


if __name__ == "__main__":
    unittest.main()
