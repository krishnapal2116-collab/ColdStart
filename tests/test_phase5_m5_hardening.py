"""Offline M5 hardening, release-file, and self-audit checks."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CATALOG_IDS = {
    "CS-PROJECT-001",
    "CS-PROJECT-002",
    "CS-DEPS-001",
    "CS-DEPS-002",
    "CS-RUNTIME-001",
    "CS-DOCS-001",
    "CS-DOCS-002",
    "CS-CONFIG-001",
    "CS-CONFIG-002",
    "CS-PORT-001",
    "CS-SEC-001",
    "CS-BUILD-001",
    "CS-PATH-001",
}
REQUIRED_REPORT_FIELDS = {
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
STATUS_VALUES = {
    "passed",
    "failed",
    "not_applicable",
    "skipped",
    "not_verified",
    "error",
}
SEVERITY_VALUES = {"info", "warning", "error", "blocking"}
EVIDENCE_STRENGTH_VALUES = {
    "direct",
    "derived",
    "indicator",
    "absence",
    "unverified",
}


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


def load_report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if not result.stdout.strip():
        raise AssertionError(f"expected JSON report; stderr was {result.stderr!r}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise AssertionError("expected a JSON object report")
    return value


def normalize(value: object) -> object:
    volatile = {"created_at", "generated_at", "report_id", "run_id", "timestamp"}
    if isinstance(value, Mapping):
        return {
            str(key): normalize(item)
            for key, item in value.items()
            if key not in volatile
        }
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


@contextlib.contextmanager
def fixture_repository(files: Mapping[str, str | bytes]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="coldstart-m5-hardening-") as temporary:
        root = Path(temporary) / "fixture"
        root.mkdir()
        for relative, contents in files.items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(contents, bytes):
                destination.write_bytes(contents)
            else:
                destination.write_text(contents, encoding="utf-8")
        yield root


class Phase5M5HardeningTests(unittest.TestCase):
    def test_self_audit_has_complete_catalog_safe_output_and_no_staging(self) -> None:
        before = {
            path.relative_to(ROOT).as_posix()
            for path in ROOT.iterdir()
            if path.name not in {".git"}
        }
        result = run_cli("audit", str(ROOT), "--format", "json")
        report = load_report(result)
        after = {
            path.relative_to(ROOT).as_posix()
            for path in ROOT.iterdir()
            if path.name not in {".git"}
        }

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertEqual(before, after)
        findings = report["findings"]
        self.assertIsInstance(findings, list)
        assert isinstance(findings, list)
        catalog_findings = [
            item
            for item in findings
            if isinstance(item, Mapping) and item.get("check_id") in CATALOG_IDS
        ]
        ids = [item["check_id"] for item in catalog_findings]
        self.assertEqual(set(ids), CATALOG_IDS)
        self.assertEqual(len(ids), len(set(ids)))
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(str(ROOT), serialized)
        self.assertNotIn("super-secret-value-not-for-output", serialized)
        self.assertNotIn("coldstart-stage", serialized.casefold())

    def test_repeated_self_audit_reports_and_fingerprints_are_stable(self) -> None:
        first = load_report(run_cli("audit", str(ROOT), "--format", "json"))
        second = load_report(run_cli("audit", str(ROOT), "--format", "json"))
        self.assertEqual(normalize(first), normalize(second))
        first_repository = first.get("repository")
        second_repository = second.get("repository")
        self.assertIsInstance(first_repository, Mapping)
        self.assertIsInstance(second_repository, Mapping)
        assert isinstance(first_repository, Mapping)
        assert isinstance(second_repository, Mapping)
        self.assertEqual(
            first_repository.get("audit_fingerprint"),
            second_repository.get("audit_fingerprint"),
        )

    def test_report_contract_and_finding_enums_are_complete(self) -> None:
        report = load_report(run_cli("audit", str(ROOT), "--format", "json"))
        self.assertTrue(REQUIRED_REPORT_FIELDS.issubset(report))
        self.assertEqual(report.get("schema_version"), "1.0")
        findings = report.get("findings")
        self.assertIsInstance(findings, list)
        assert isinstance(findings, list)
        required_finding_fields = {
            "check_id",
            "severity",
            "status",
            "title",
            "message",
            "evidence",
            "remediation",
            "affected_path",
            "category",
            "applicability",
            "rule_version",
            "evidence_strength",
        }
        for finding in findings:
            self.assertIsInstance(finding, Mapping)
            assert isinstance(finding, Mapping)
            self.assertTrue(required_finding_fields.issubset(finding))
            self.assertIn(finding.get("status"), STATUS_VALUES)
            self.assertIn(finding.get("severity"), SEVERITY_VALUES)
            self.assertIn(finding.get("evidence_strength"), EVIDENCE_STRENGTH_VALUES)
            self.assertIsInstance(finding.get("evidence"), list)
            self.assertGreater(len(finding["evidence"]), 0)

    def test_terminal_and_json_reports_expose_the_same_catalog_statuses(self) -> None:
        files = {
            ".python-version": "3.12.8\n",
            "pyproject.toml": "[project]\nname='m5'\nrequires-python='>=3.12,<3.13'\ndependencies=[]\n",
            "README.md": "# M5\n\nNo external configuration is required.\n",
            "src/app.py": "from pathlib import Path\n",
        }
        with fixture_repository(files) as root:
            json_report = load_report(run_cli("audit", str(root), "--format", "json"))
            terminal = run_cli("audit", str(root), "--format", "terminal")

        self.assertIn(terminal.returncode, {0, 1, 3}, terminal.stderr)
        terminal_statuses: dict[str, str] = {}
        current: str | None = None
        for line in terminal.stdout.splitlines():
            if line.startswith("[") and "] " in line and " -- " in line:
                current = line.split("] ", 1)[1].split(" -- ", 1)[0]
            elif current is not None and line.strip().startswith("Status:"):
                terminal_statuses[current] = line.split(":", 1)[1].strip()
        json_statuses = {
            item["check_id"]: item["status"]
            for item in json_report["findings"]
            if isinstance(item, Mapping) and item.get("check_id") in CATALOG_IDS
        }
        self.assertEqual(
            {key: value for key, value in terminal_statuses.items() if key in CATALOG_IDS},
            json_statuses,
        )

    def test_release_files_and_canonical_commands_are_present(self) -> None:
        for relative in (
            ".python-version",
            "requirements.lock",
            "requirements-dev.lock",
            "Dockerfile",
            "Makefile",
            "README.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertEqual((ROOT / ".python-version").read_text(encoding="utf-8").strip(), "3.12.8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("python:3.12.8-slim-bookworm", dockerfile)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("test:", makefile)
        self.assertIn("unittest discover", makefile)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("make test", readme)
        self.assertIn("Docker", readme)

    def test_malicious_fixture_is_not_executed_or_modified(self) -> None:
        files = {
            "README.md": "# Malicious-looking fixture\n",
            "project.py": (
                "from pathlib import Path\n"
                "Path('executed-marker.txt').write_text('executed')\n"
                "Path(__file__).write_text('modified')\n"
            ),
        }
        with fixture_repository(files) as root:
            before = hashlib.sha256((root / "project.py").read_bytes()).hexdigest()
            result = run_cli("audit", str(root), "--format", "json")
            after = hashlib.sha256((root / "project.py").read_bytes()).hexdigest()

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertEqual(before, after)
        self.assertFalse((root / "executed-marker.txt").exists())

    def test_sensitive_and_control_like_fixture_evidence_is_redacted(self) -> None:
        secret = "super-secret-value-not-for-output"
        with fixture_repository(
            {
                "README.md": "Use C:\\Users\\alice\\project and configure DATABASE_URL.\x1b[31m\n",
                "config.py": f"import os\nTOKEN = {secret!r}\nDATABASE_URL = os.environ['DATABASE_URL']\n",
            }
        ) as root:
            report = load_report(run_cli("audit", str(root), "--format", "json"))

        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("C:\\Users\\alice", serialized)
        self.assertNotIn("\\x1b[31m", serialized)
        self.assertIn("redacted", serialized)


if __name__ == "__main__":
    unittest.main()
