from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

STATUS_VALUES = {
    "passed",
    "failed",
    "not_applicable",
    "skipped",
    "not_verified",
    "error",
}
EVIDENCE_STRENGTH_VALUES = {
    "direct",
    "derived",
    "indicator",
    "absence",
    "unverified",
}
SUMMARY_STATUS_KEYS = (
    "passed",
    "failed",
    "not_applicable",
    "skipped",
    "not_verified",
    "error",
)
REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "tool",
    "invocation",
    "repository",
    "detection",
    "findings",
    "policy",
    "verification",
    "redaction",
    "summary",
}
FINGERPRINT_RE = re.compile(r"^[a-f0-9]{64}$")
TERMINAL_SUMMARY_RE = re.compile(
    r"Summary:\s+"
    r"passed=(?P<passed>\d+)\s+"
    r"failed=(?P<failed>\d+)\s+"
    r"not_applicable=(?P<not_applicable>\d+)\s+"
    r"skipped=(?P<skipped>\d+)\s+"
    r"not_verified=(?P<not_verified>\d+)\s+"
    r"error=(?P<error>\d+)"
)
TERMINAL_FINDING_RE = re.compile(
    r"^\[[A-Za-z]+\]\s+([A-Za-z0-9][A-Za-z0-9_-]*)\s+"
)


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


@contextlib.contextmanager
def healthy_repository(
    *,
    unsupported_test_command: bool = False,
    malicious_script: bool = False,
) -> Iterator[tuple[Path, Path]]:
    """Create a small, dependency-free Python repository for CLI integration tests."""

    with tempfile.TemporaryDirectory() as temporary_directory:
        parent = Path(temporary_directory)
        repository = parent / "fixture-project"
        repository.mkdir()

        test_command = "python -m unittest discover -s tests -p 'test_*.py'"
        if unsupported_test_command:
            # The contract's example uses an unsupported shell composition as a
            # truthful source of a not_verified documentation finding.
            test_command += " && echo 'finished'"

        files = {
            ".python-version": "3.12.8\n",
            "pyproject.toml": (
                "[project]\n"
                "name = 'fixture-project'\n"
                "version = '0.1.0'\n"
                "requires-python = '>=3.12,<3.13'\n"
                "dependencies = []\n"
            ),
            "requirements.txt": "# This fixture has no third-party runtime dependencies.\n",
            "requirements.lock": "# The empty runtime dependency set is intentional.\n",
            "README.md": (
                "# Fixture project\n\n"
                "## Prerequisites\n\n"
                "Use Python 3.12.8.\n\n"
                "## Install\n\n"
                "python -m pip install --no-deps -e .\n\n"
                "## Configuration\n\n"
                "No external configuration is required.\n\n"
                "## Run\n\n"
                "python -m fixture_project\n\n"
                "## Test\n\n"
                f"{test_command}\n"
            ),
            "src/fixture_project/__init__.py": '"""A minimal audit fixture."""\n',
            "src/fixture_project/__main__.py": (
                "from . import __doc__\n\n"
                "if __name__ == '__main__':\n"
                "    print(__doc__ or 'fixture')\n"
            ),
            "tests/test_fixture_project.py": (
                "import unittest\n\n"
                "\nclass FixtureTests(unittest.TestCase):\n"
                "    def test_fixture_is_present(self):\n"
                "        self.assertTrue(True)\n"
            ),
        }
        if malicious_script:
            files["src/fixture_project/project_script.py"] = (
                "from pathlib import Path\n\n"
                "marker = Path(__file__).with_name('executed-marker.txt')\n"
                "Path(__file__).write_text('modified by execution\\n', encoding='utf-8')\n"
                "marker.write_text('executed\\n', encoding='utf-8')\n"
            )

        for relative_path, contents in files.items():
            destination = repository / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents, encoding="utf-8")

        yield repository, parent


def load_json_report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if result.stdout.strip() == "":
        raise AssertionError(f"expected JSON on stdout; stderr was: {result.stderr!r}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"expected one JSON report on stdout, got: {result.stdout!r}"
        ) from error
    if not isinstance(report, dict):
        raise AssertionError(f"expected a JSON object report, got {type(report)!r}")
    return report


def normalized_report(report: dict[str, object]) -> dict[str, object]:
    """Remove only explicitly non-semantic run metadata before comparing reports."""

    volatile_keys = {
        "created_at",
        "generated_at",
        "report_id",
        "run_id",
        "timestamp",
    }

    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: normalize(item)
                for key, item in value.items()
                if key not in volatile_keys
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    normalized = normalize(report)
    if not isinstance(normalized, dict):  # pragma: no cover - guarded by input type
        raise AssertionError("normalized report must remain an object")
    return normalized


def terminal_semantics(text: str) -> tuple[dict[str, int], dict[str, tuple[str, str]]]:
    summary_match = TERMINAL_SUMMARY_RE.search(text)
    if summary_match is None:
        raise AssertionError(f"terminal report has no contract summary: {text!r}")
    summary = {
        key: int(value) for key, value in summary_match.groupdict().items()
    }

    findings: dict[str, tuple[str, str]] = {}
    current_check_id: str | None = None
    current_status: str | None = None
    current_evidence_strength: str | None = None
    for line in text.splitlines():
        finding_match = TERMINAL_FINDING_RE.match(line)
        if finding_match is not None:
            if current_check_id is not None:
                if current_status is None or current_evidence_strength is None:
                    raise AssertionError(
                        f"terminal finding {current_check_id} is missing status/evidence strength"
                    )
                findings[current_check_id] = (
                    current_status,
                    current_evidence_strength,
                )
            current_check_id = finding_match.group(1)
            current_status = None
            current_evidence_strength = None
            continue
        if current_check_id is None:
            continue
        stripped_line = line.strip()
        if stripped_line.startswith("Status:"):
            current_status = stripped_line.split(":", 1)[1].strip()
        elif stripped_line.startswith("Evidence strength:"):
            current_evidence_strength = stripped_line.split(":", 1)[1].strip()

    if current_check_id is not None:
        if current_status is None or current_evidence_strength is None:
            raise AssertionError(
                f"terminal finding {current_check_id} is missing status/evidence strength"
            )
        findings[current_check_id] = (current_status, current_evidence_strength)

    return summary, findings


def finding_semantics(report: dict[str, object]) -> dict[str, tuple[str, str]]:
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise AssertionError("report findings must be a list")
    semantics: dict[str, tuple[str, str]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            raise AssertionError("each finding must be an object")
        check_id = finding.get("check_id")
        status = finding.get("status")
        evidence_strength = finding.get("evidence_strength")
        if not all(isinstance(value, str) for value in (check_id, status, evidence_strength)):
            raise AssertionError(f"finding has invalid semantic fields: {finding!r}")
        semantics[check_id] = (status, evidence_strength)
    return semantics


class Phase2M1AuditIntegrationTests(unittest.TestCase):
    def test_valid_directory_terminal_report_exits_zero(self) -> None:
        with healthy_repository() as (repository, _parent):
            result = run_cli("audit", str(repository), "--format", "terminal")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ColdStart", result.stdout)
        self.assertIn("Repository:", result.stdout)
        self.assertIn("Summary:", result.stdout)
        self.assertIn("Exit code: 0", result.stdout)
        self.assertNotIn("\x1b[", result.stdout)

    def test_valid_directory_json_report_has_contract_fields_and_counts(self) -> None:
        with healthy_repository() as (repository, _parent):
            result = run_cli("audit", str(repository), "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = load_json_report(result)
        self.assertTrue(REQUIRED_TOP_LEVEL_FIELDS <= report.keys())
        self.assertEqual(report["schema_version"], "1.0")

        repository_section = report["repository"]
        self.assertIsInstance(repository_section, dict)
        assert isinstance(repository_section, dict)
        fingerprint = repository_section.get("audit_fingerprint")
        self.assertIsInstance(fingerprint, str)
        assert isinstance(fingerprint, str)
        self.assertRegex(fingerprint, FINGERPRINT_RE)

        findings = report["findings"]
        self.assertIsInstance(findings, list)
        assert isinstance(findings, list)
        self.assertGreater(len(findings), 0)
        status_counts: Counter[str] = Counter()
        for finding in findings:
            self.assertIsInstance(finding, dict)
            assert isinstance(finding, dict)
            status = finding.get("status")
            evidence_strength = finding.get("evidence_strength")
            self.assertIsInstance(status, str)
            self.assertIsInstance(evidence_strength, str)
            assert isinstance(status, str)
            assert isinstance(evidence_strength, str)
            self.assertIn(status, STATUS_VALUES)
            self.assertIn(evidence_strength, EVIDENCE_STRENGTH_VALUES)
            status_counts[status] += 1

        summary = report["summary"]
        self.assertIsInstance(summary, dict)
        assert isinstance(summary, dict)
        counts = summary.get("counts")
        self.assertIsInstance(counts, dict)
        assert isinstance(counts, dict)
        self.assertTrue(set(SUMMARY_STATUS_KEYS) <= set(counts))
        for status in SUMMARY_STATUS_KEYS:
            self.assertIsInstance(counts[status], int)
            self.assertGreaterEqual(counts[status], 0)
            self.assertEqual(counts[status], status_counts[status])

    def test_terminal_and_json_reports_have_matching_semantics(self) -> None:
        with healthy_repository() as (repository, _parent):
            terminal_result = run_cli("audit", str(repository), "--format", "terminal")
            json_result = run_cli("audit", str(repository), "--format", "json")

        self.assertEqual(terminal_result.returncode, 0, terminal_result.stderr)
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        report = load_json_report(json_result)
        terminal_summary, terminal_findings = terminal_semantics(terminal_result.stdout)

        json_summary = report.get("summary")
        self.assertIsInstance(json_summary, dict)
        assert isinstance(json_summary, dict)
        json_counts = json_summary.get("counts")
        self.assertIsInstance(json_counts, dict)
        assert isinstance(json_counts, dict)
        self.assertEqual(
            terminal_summary,
            {status: json_counts[status] for status in SUMMARY_STATUS_KEYS},
        )
        self.assertEqual(terminal_findings, finding_semantics(report))

    def test_missing_and_non_directory_paths_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            missing = parent / "missing-repository"
            non_directory = parent / "not-a-directory"
            non_directory.write_text("not a repository\n", encoding="utf-8")

            for path in (missing, non_directory):
                with self.subTest(path=path):
                    result = run_cli("audit", str(path))
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertNotEqual(result.stderr.strip(), "")

    def test_output_path_writes_selected_terminal_and_json_reports(self) -> None:
        with healthy_repository() as (repository, parent):
            for report_format in ("terminal", "json"):
                with self.subTest(report_format=report_format):
                    output_path = parent / f"report.{report_format}"
                    result = run_cli(
                        "audit",
                        str(repository),
                        "--format",
                        report_format,
                        "--output",
                        str(output_path),
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(output_path.is_file())
                    saved_report = output_path.read_text(encoding="utf-8")
                    self.assertNotEqual(saved_report, "")
                    self.assertNotIn("schema_version", result.stdout)
                    if report_format == "json":
                        self.assertIsInstance(json.loads(saved_report), dict)
                    else:
                        self.assertIn("ColdStart", saved_report)
                        self.assertIn("Exit code: 0", saved_report)

    def test_repeated_json_runs_are_normalized_and_fingerprint_stable(self) -> None:
        with healthy_repository() as (repository, _parent):
            first_result = run_cli("audit", str(repository), "--format", "json")
            second_result = run_cli("audit", str(repository), "--format", "json")

        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        first_report = load_json_report(first_result)
        second_report = load_json_report(second_result)
        self.assertEqual(
            json.dumps(normalized_report(first_report), sort_keys=True),
            json.dumps(normalized_report(second_report), sort_keys=True),
        )

        first_repository = first_report["repository"]
        second_repository = second_report["repository"]
        self.assertIsInstance(first_repository, dict)
        self.assertIsInstance(second_repository, dict)
        assert isinstance(first_repository, dict)
        assert isinstance(second_repository, dict)
        self.assertEqual(
            first_repository.get("audit_fingerprint"),
            second_repository.get("audit_fingerprint"),
        )

    def test_strict_mode_keeps_not_verified_findings_visible(self) -> None:
        with healthy_repository(unsupported_test_command=True) as (repository, _parent):
            result = run_cli(
                "audit",
                str(repository),
                "--format",
                "json",
                "--strict",
            )

        report = load_json_report(result)
        findings = report.get("findings")
        self.assertIsInstance(findings, list)
        assert isinstance(findings, list)
        not_verified = [
            finding
            for finding in findings
            if isinstance(finding, dict) and finding.get("status") == "not_verified"
        ]
        self.assertGreater(
            len(not_verified),
            0,
            "strict mode must retain the original not_verified findings",
        )
        summary = report.get("summary")
        self.assertIsInstance(summary, dict)
        assert isinstance(summary, dict)
        counts = summary.get("counts")
        self.assertIsInstance(counts, dict)
        assert isinstance(counts, dict)
        self.assertEqual(counts["not_verified"], len(not_verified))

    def test_malicious_looking_project_script_is_not_executed_or_modified(self) -> None:
        with healthy_repository(malicious_script=True) as (repository, _parent):
            script = repository / "src/fixture_project/project_script.py"
            before_bytes = script.read_bytes()
            before_digest = hashlib.sha256(before_bytes).hexdigest()
            before_mtime = script.stat().st_mtime_ns

            result = run_cli("audit", str(repository), "--format", "json")

            after_bytes = script.read_bytes()
            after_digest = hashlib.sha256(after_bytes).hexdigest()
            after_mtime = script.stat().st_mtime_ns
            marker = script.with_name("executed-marker.txt")
            marker_created = marker.exists()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(after_digest, before_digest)
        self.assertEqual(after_bytes, before_bytes)
        self.assertEqual(after_mtime, before_mtime)
        self.assertFalse(marker_created)

    def test_invalid_format_and_output_selection_exit_two(self) -> None:
        with healthy_repository() as (repository, parent):
            invalid_format = run_cli("audit", str(repository), "--format", "yaml")
            output_directory = run_cli(
                "audit",
                str(repository),
                "--format",
                "json",
                "--output",
                str(repository),
            )
            missing_parent_output = run_cli(
                "audit",
                str(repository),
                "--format",
                "json",
                "--output",
                str(parent / "missing-parent" / "report.json"),
            )

        self.assertEqual(invalid_format.returncode, 2)
        self.assertEqual(invalid_format.stdout, "")
        self.assertNotEqual(invalid_format.stderr.strip(), "")

        self.assertEqual(output_directory.returncode, 2)
        self.assertEqual(output_directory.stdout, "")
        self.assertNotEqual(output_directory.stderr.strip(), "")

        self.assertNotEqual(missing_parent_output.returncode, 0)
        self.assertEqual(missing_parent_output.stdout, "")
        self.assertNotEqual(missing_parent_output.stderr.strip(), "")


if __name__ == "__main__":
    unittest.main()
