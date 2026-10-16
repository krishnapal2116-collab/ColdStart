"""CLI/report integration tests for the complete M4 P0 catalog."""

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
    with tempfile.TemporaryDirectory(prefix="coldstart-m4-integration-") as temporary:
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


HEALTHY_README = """# Fixture

## Prerequisites
Use Python 3.12.8.

## Installation
```sh
python -m pip install -e .
```

## Configuration
No external configuration is required.

## Run
```sh
python -m fixture
```

## Test
```sh
python -m unittest discover -s tests -p 'test_*.py'
```
"""


def healthy_files() -> dict[str, str]:
    return {
        ".python-version": "3.12.8\n",
        "pyproject.toml": (
            "[project]\n"
            "name = 'm4-fixture'\n"
            "version = '0.1.0'\n"
            "requires-python = '>=3.12,<3.13'\n"
            "dependencies = []\n"
        ),
        "requirements.lock": "# empty dependency set\n",
        "README.md": HEALTHY_README,
        "src/fixture.py": "from pathlib import Path\n",
        "tests/test_fixture.py": "def test_fixture():\n    assert True\n",
    }


def finding_map(report: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = report.get("findings")
    if not isinstance(raw, list):
        raise AssertionError("report findings must be a list")
    result: dict[str, Mapping[str, object]] = {}
    for item in raw:
        if isinstance(item, Mapping) and isinstance(item.get("check_id"), str):
            result[item["check_id"]] = item
    return result


class Phase4M4IntegrationTests(unittest.TestCase):
    def test_healthy_fixture_reports_every_catalog_check_once(self) -> None:
        with fixture_repository(healthy_files()) as root:
            result = run_cli("audit", str(root), "--format", "json")
            report = load_report(result)

        self.assertEqual(result.returncode, 0, result.stderr)
        raw_findings = report.get("findings")
        self.assertIsInstance(raw_findings, list)
        assert isinstance(raw_findings, list)
        catalog_findings = [
            item
            for item in raw_findings
            if isinstance(item, Mapping) and item.get("check_id") in CATALOG_IDS
        ]
        ids = [item["check_id"] for item in catalog_findings]
        self.assertEqual(set(ids), CATALOG_IDS)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            report.get("detection", {}).get("scope"),
            "M2 bounded discovery and complete M3/M4 static catalog checks",
        )

    def test_defective_fixture_reports_m4_findings_redacted_and_nonexecuting(self) -> None:
        files = {
            ".python-version": "3.12.8\n",
            "pyproject.toml": (
                "[project]\n"
                "name = 'defective-m4'\n"
                "version = '0.1.0'\n"
                "requires-python = '>=3.12,<3.13'\n"
                "dependencies = []\n"
            ),
            "README.md": "Docker is required to run this project.\n",
            "tests/test_fixture.py": "def test_fixture():\n    assert True\n",
            "config.py": (
                "import os\n"
                "from pathlib import Path\n"
                "Path('executed-marker.txt').write_text('executed')\n"
                "API_TOKEN = 'super-secret-value-not-for-output'\n"
                "DATABASE_URL = os.environ[\"DATABASE_URL\"]\n"
                "CACHE_ROOT = '/home/alice/project'\n"
            ),
            "Dockerfile": "FROM alpine\nCOPY ../outside.txt /app/outside.txt\n",
        }
        with fixture_repository(files) as root:
            result = run_cli("audit", str(root), "--format", "json")
            report = load_report(result)
            marker_exists = (root / "executed-marker.txt").exists()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(marker_exists)
        findings = finding_map(report)
        self.assertEqual(findings["CS-DOCS-002"]["status"], "failed")
        self.assertEqual(findings["CS-CONFIG-001"]["status"], "failed")
        self.assertEqual(findings["CS-CONFIG-002"]["status"], "failed")
        self.assertEqual(findings["CS-PORT-001"]["status"], "failed")
        self.assertEqual(findings["CS-SEC-001"]["status"], "failed")
        self.assertEqual(findings["CS-SEC-001"]["severity"], "error")
        self.assertEqual(findings["CS-PATH-001"]["status"], "failed")
        rendered = repr(report)
        self.assertNotIn("super-secret-value-not-for-output", rendered)
        self.assertNotIn("/home/alice/project", rendered)

    def test_m4_policy_exclusions_are_visible_once(self) -> None:
        files = healthy_files()
        files[".coldstart.toml"] = (
            "excluded_checks = [\"CS-DOCS-002\", \"CS-SEC-001\", \"CS-PATH-001\"]\n"
        )
        with fixture_repository(files) as root:
            result = run_cli("audit", str(root), "--format", "json")
            report = load_report(result)

        self.assertEqual(result.returncode, 0, result.stderr)
        raw_findings = report.get("findings")
        self.assertIsInstance(raw_findings, list)
        assert isinstance(raw_findings, list)
        for check_id in ("CS-DOCS-002", "CS-SEC-001", "CS-PATH-001"):
            matches = [
                item
                for item in raw_findings
                if isinstance(item, Mapping) and item.get("check_id") == check_id
            ]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].get("status"), "skipped")


if __name__ == "__main__":
    unittest.main()
