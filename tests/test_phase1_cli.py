from __future__ import annotations

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


class Phase1CliTests(unittest.TestCase):
    def test_help_is_available_without_a_repository(self) -> None:
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)
        self.assertIn("audit", result.stdout)
        self.assertIn("version", result.stdout)

    def test_version_reports_frozen_metadata(self) -> None:
        result = run_cli("version")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ColdStart 0.1.0", result.stdout)
        self.assertIn("Report schema: 1.0", result.stdout)
        self.assertIn("Check catalog: p0-1", result.stdout)
        self.assertIn("Target Python: 3.12.8", result.stdout)

    def test_global_version_option_is_available(self) -> None:
        result = run_cli("--version")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ColdStart 0.1.0", result.stdout)

    def test_audit_is_truthful_and_does_not_execute_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            marker = repository / "executed-marker.txt"
            (repository / "project_script.py").write_text(
                f"Path({str(marker)!r}).write_text('executed')\n",
                encoding="utf-8",
            )

            result = run_cli("audit", str(repository))

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Status: not_verified", result.stdout)
        self.assertIn("M3 evaluates", result.stdout)
        self.assertIn("never executes repository code", result.stdout)
        self.assertFalse(marker.exists())

    def test_audit_rejects_a_missing_path(self) -> None:
        missing = ROOT / "this-path-does-not-exist-phase1"

        result = run_cli("audit", str(missing))

        self.assertEqual(result.returncode, 2)
        self.assertIn("does not exist", result.stderr)


if __name__ == "__main__":
    unittest.main()
