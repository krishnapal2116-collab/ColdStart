"""CLI/report integration tests for the M3 Python check slice."""

from __future__ import annotations

import contextlib
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


@contextlib.contextmanager
def fixture_repository(files: Mapping[str, str | bytes]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="coldstart-m3-integration-") as temporary:
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


COMPLETE_README = """# Fixture

## Prerequisites
Use Python 3.12.8.

## Installation
```sh
python -m pip install -e .
```

## Configuration
No configuration is required.

## Run
```sh
python -m fixture
```
"""


def healthy_python_files() -> dict[str, str]:
    return {
        ".python-version": "3.12.8\n",
        "pyproject.toml": (
            "[project]\n"
            "name = 'm3-fixture'\n"
            "version = '0.1.0'\n"
            "requires-python = '>=3.12,<3.13'\n"
            "dependencies = ['requests==2.31.0']\n"
        ),
        "requirements.lock": "requests==2.31.0\n",
        "README.md": COMPLETE_README,
        "src/fixture.py": "import requests\n",
    }


def findings_by_id(report: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = report.get("findings")
    if not isinstance(raw, list):
        raise AssertionError("report findings must be a list")
    result: dict[str, Mapping[str, object]] = {}
    for item in raw:
        if isinstance(item, Mapping) and isinstance(item.get("check_id"), str):
            result[item["check_id"]] = item
    return result


class Phase3M3IntegrationTests(unittest.TestCase):
    def test_healthy_python_fixture_integrates_four_m3_findings(self) -> None:
        with fixture_repository(healthy_python_files()) as root:
            result = run_cli("audit", str(root), "--format", "json")
            report = load_report(result)

        self.assertEqual(result.returncode, 0, result.stderr)
        findings = findings_by_id(report)
        self.assertEqual(
            {
                check_id: findings[check_id]["status"]
                for check_id in (
                    "CS-DEPS-001",
                    "CS-DEPS-002",
                    "CS-RUNTIME-001",
                    "CS-DOCS-001",
                )
            },
            {check_id: "passed" for check_id in (
                "CS-DEPS-001",
                "CS-DEPS-002",
                "CS-RUNTIME-001",
                "CS-DOCS-001",
            )},
        )
        detection = report.get("detection")
        self.assertIsInstance(detection, Mapping)
        assert isinstance(detection, Mapping)
        self.assertIn("M3", " ".join(str(item) for item in detection.get("limitations", [])))

    def test_defective_python_fixture_reports_static_findings_without_execution(self) -> None:
        files = {
            "pyproject.toml": (
                "[project]\n"
                "name = 'defective'\n"
                "version = '0.1.0'\n"
                "dependencies = []\n"
            ),
            "src/fixture.py": (
                "from pathlib import Path\n"
                "Path('executed-marker.txt').write_text('executed')\n"
                "import requests\n"
            ),
            "README.md": "# Defective fixture\n\nA description only.\n",
        }
        with fixture_repository(files) as root:
            result = run_cli("audit", str(root), "--format", "json")
            report = load_report(result)
            marker_exists = (root / "executed-marker.txt").exists()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(marker_exists)
        findings = findings_by_id(report)
        self.assertEqual(findings["CS-DEPS-001"]["status"], "failed")
        self.assertEqual(findings["CS-DEPS-002"]["status"], "failed")
        self.assertEqual(findings["CS-RUNTIME-001"]["status"], "failed")
        self.assertEqual(findings["CS-DOCS-001"]["status"], "failed")
        self.assertTrue(
            all(
                item.get("rule_version") == "3"
                for check_id, item in findings.items()
                if check_id in {
                    "CS-DEPS-001",
                    "CS-DEPS-002",
                    "CS-RUNTIME-001",
                    "CS-DOCS-001",
                }
            )
        )

    def test_node_project_keeps_python_checks_not_applicable(self) -> None:
        with fixture_repository(
            {
                "package.json": '{"name":"node-fixture","version":"1.0.0"}\n',
                "package-lock.json": '{"lockfileVersion":3}\n',
                "index.js": "module.exports = {};\n",
                "README.md": COMPLETE_README,
            }
        ) as root:
            result = run_cli("audit", str(root), "--format", "json")
            report = load_report(result)

        self.assertEqual(result.returncode, 0, result.stderr)
        findings = findings_by_id(report)
        self.assertEqual(findings["CS-DEPS-001"]["status"], "not_applicable")
        self.assertEqual(findings["CS-DEPS-002"]["status"], "not_applicable")
        self.assertEqual(findings["CS-RUNTIME-001"]["status"], "not_applicable")
        self.assertEqual(findings["CS-DOCS-001"]["status"], "passed")

    def test_m3_exclusion_is_visible_once_and_does_not_duplicate_findings(self) -> None:
        files = healthy_python_files()
        files[".coldstart.toml"] = 'excluded_checks = ["CS-DEPS-001"]\n'
        with fixture_repository(files) as root:
            result = run_cli("audit", str(root), "--format", "json")
            report = load_report(result)

        self.assertEqual(result.returncode, 0, result.stderr)
        raw_findings = report.get("findings")
        self.assertIsInstance(raw_findings, list)
        assert isinstance(raw_findings, list)
        matching = [
            item
            for item in raw_findings
            if isinstance(item, Mapping) and item.get("check_id") == "CS-DEPS-001"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].get("status"), "skipped")

    def test_m3_fingerprint_changes_when_bounded_source_evidence_changes(self) -> None:
        files = healthy_python_files()
        files["pyproject.toml"] = files["pyproject.toml"].replace(
            "dependencies = ['requests==2.31.0']", "dependencies = []"
        )
        files["src/fixture.py"] = "from pathlib import Path\n"
        with fixture_repository(files) as root:
            first = load_report(run_cli("audit", str(root), "--format", "json"))
            (root / "src" / "fixture.py").write_text("import requests\n", encoding="utf-8")
            second = load_report(run_cli("audit", str(root), "--format", "json"))

        first_repository = first.get("repository")
        second_repository = second.get("repository")
        self.assertIsInstance(first_repository, Mapping)
        self.assertIsInstance(second_repository, Mapping)
        assert isinstance(first_repository, Mapping)
        assert isinstance(second_repository, Mapping)
        self.assertNotEqual(
            first_repository.get("audit_fingerprint"),
            second_repository.get("audit_fingerprint"),
        )


if __name__ == "__main__":
    unittest.main()
