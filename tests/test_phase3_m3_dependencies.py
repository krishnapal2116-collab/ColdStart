"""Focused offline tests for the standalone M3 dependency checks."""

from __future__ import annotations

import contextlib
import dataclasses
import os
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path

from coldstart.checks.dependencies import evaluate_dependency_checks
from coldstart.discovery import detect_projects, inventory_repository


@contextlib.contextmanager
def fixture_repository(files: Mapping[str, str | bytes]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="coldstart-m3-dependencies-") as temporary_directory:
        root = Path(temporary_directory) / "fixture"
        root.mkdir()
        for relative, contents in files.items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(contents, bytes):
                destination.write_bytes(contents)
            else:
                destination.write_text(contents, encoding="utf-8")
        yield root


def evaluate(root: Path):
    inventory = inventory_repository(root)
    detection = detect_projects(root, inventory)
    return evaluate_dependency_checks(root, inventory, detection)


def finding_map(findings):
    return {finding.check_id: finding for finding in findings}


class Phase3M3DependencyChecksTests(unittest.TestCase):
    def test_declared_dependency_passes_and_lockfile_is_recognized(self) -> None:
        with fixture_repository(
            {
                "pyproject.toml": (
                    "[project]\n"
                    "name = 'declared-fixture'\n"
                    "dependencies = ['requests>=2.0']\n"
                    "[project.optional-dependencies]\n"
                    "test = ['pytest==8.0']\n"
                    "[dependency-groups]\n"
                    "dev = ['ruff==0.6']\n"
                ),
                "poetry.lock": "# bounded lock evidence\n",
                "src/app.py": "import requests\n",
            }
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-DEPS-001"].status, "passed")
        self.assertEqual(findings["CS-DEPS-002"].status, "passed")
        self.assertEqual(findings["CS-DEPS-001"].rule_version, "3")
        self.assertEqual(findings["CS-DEPS-002"].category, "dependencies")

    def test_undeclared_high_confidence_import_fails_declaration_check(self) -> None:
        with fixture_repository(
            {
                "pyproject.toml": "[project]\nname = 'missing-fixture'\ndependencies = []\n",
                "src/app.py": "import requests\n",
            }
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-DEPS-001"].status, "failed")
        self.assertEqual(findings["CS-DEPS-002"].status, "failed")
        self.assertTrue(any(item.path == "src/app.py" for item in findings["CS-DEPS-001"].evidence))

    def test_dependency_free_python_project_is_pass_and_lock_not_applicable(self) -> None:
        with fixture_repository(
            {
                "pyproject.toml": "[project]\nname = 'stdlib-only'\ndependencies = []\n",
                "src/app.py": "from pathlib import Path\nimport json\n",
            }
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-DEPS-001"].status, "passed")
        self.assertEqual(findings["CS-DEPS-002"].status, "not_applicable")

    def test_requirements_declaration_and_lock_variants(self) -> None:
        cases = (
            ({"requirements.txt": "requests==2.31.0\n", "src/app.py": "import requests\n"}, "failed"),
            (
                {
                    "requirements.txt": "requests==2.31.0\n",
                    "requirements.lock": "requests==2.31.0\n",
                    "src/app.py": "import requests\n",
                },
                "passed",
            ),
            (
                {
                    "requirements.txt": "requests==2.31.0\n",
                    "package-lock.json": "{\"lockfileVersion\": 3}\n",
                    "src/app.py": "import requests\n",
                },
                "failed",
            ),
        )
        for files, expected_lock_status in cases:
            with self.subTest(expected_lock_status=expected_lock_status), fixture_repository(files) as root:
                findings = finding_map(evaluate(root))
                self.assertEqual(findings["CS-DEPS-001"].status, "passed")
                self.assertEqual(findings["CS-DEPS-002"].status, expected_lock_status)
                if expected_lock_status == "failed":
                    self.assertFalse(
                        any(
                            evidence.path == "package-lock.json" and evidence.kind == "file"
                            and "not accepted" not in evidence.detail
                            for evidence in findings["CS-DEPS-002"].evidence
                        )
                    )

    def test_fully_pinned_requirements_requires_clear_documentation(self) -> None:
        with fixture_repository(
            {
                "requirements.txt": "requests==2.31.0\n",
                "README.md": "Use the fully pinned requirements.txt as the reproducibility lockfile.\n",
                "src/app.py": "import requests\n",
            }
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-DEPS-002"].status, "passed")
        self.assertEqual(findings["CS-DEPS-002"].evidence[0].path, "requirements.txt")

    def test_malformed_and_partial_evidence_is_not_verified(self) -> None:
        with fixture_repository(
            {
                "pyproject.toml": "[project\nname = 'broken'\n",
                "src/app.py": "import requests\n",
            }
        ) as root:
            malformed = finding_map(evaluate(root))
            complete_inventory = inventory_repository(root)
            detection = detect_projects(root, complete_inventory)
            partial_inventory = dataclasses.replace(
                complete_inventory,
                truncated=True,
                omission_reasons=("file_limit",),
            )
            partial = finding_map(
                evaluate_dependency_checks(root, partial_inventory, detection)
            )

        self.assertEqual(malformed["CS-DEPS-001"].status, "not_verified")
        self.assertEqual(malformed["CS-DEPS-002"].status, "not_verified")
        self.assertEqual(partial["CS-DEPS-001"].status, "not_verified")
        self.assertEqual(partial["CS-DEPS-002"].status, "not_verified")

    def test_unreadable_discovered_file_is_not_verified(self) -> None:
        with fixture_repository(
            {
                "pyproject.toml": "[project]\nname = 'unreadable'\ndependencies = ['requests']\n",
                "src/app.py": "import requests\n",
            }
        ) as root:
            inventory = inventory_repository(root)
            records = tuple(
                dataclasses.replace(record, readable=False)
                if record.relative_path == "pyproject.toml"
                else record
                for record in inventory.records
            )
            unreadable = dataclasses.replace(
                inventory,
                records=records,
                unreadable_paths=("pyproject.toml",),
            )
            detection = detect_projects(root, unreadable)
            findings = finding_map(evaluate_dependency_checks(root, unreadable, detection))

        self.assertEqual(findings["CS-DEPS-001"].status, "not_verified")
        self.assertEqual(findings["CS-DEPS-002"].status, "not_verified")

    def test_non_python_detection_is_explicitly_not_applicable(self) -> None:
        with fixture_repository(
            {
                "package.json": "{\"name\": \"node-only\", \"version\": \"1.0.0\"}\n",
                "package-lock.json": "{\"lockfileVersion\": 3}\n",
                "index.js": "module.exports = {};\n",
            }
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-DEPS-001"].status, "not_applicable")
        self.assertEqual(findings["CS-DEPS-002"].status, "not_applicable")
        self.assertTrue(all(not finding.applicability.applicable for finding in findings.values()))

    def test_exclusion_remains_visible_and_only_excludes_selected_check(self) -> None:
        with fixture_repository(
            {
                "pyproject.toml": "[project]\nname = 'excluded'\ndependencies = ['requests']\n",
                "src/app.py": "import requests\n",
            }
        ) as root:
            findings = finding_map(
                evaluate_dependency_checks(
                    root,
                    inventory_repository(root),
                    detect_projects(root),
                    excluded_checks=("CS-DEPS-001",),
                )
            )

        self.assertEqual(findings["CS-DEPS-001"].status, "skipped")
        self.assertEqual(findings["CS-DEPS-001"].applicability.adapter, "policy")
        self.assertTrue(any(item.kind == "policy" for item in findings["CS-DEPS-001"].evidence))
        self.assertEqual(findings["CS-DEPS-002"].status, "failed")

    def test_results_are_deterministic_and_do_not_execute_source(self) -> None:
        with fixture_repository(
            {
                "pyproject.toml": "[project]\nname = 'readonly'\ndependencies = []\n",
                "src/project.py": (
                    "from pathlib import Path\n"
                    "Path('executed-marker.txt').write_text('executed')\n"
                ),
            }
        ) as root:
            inventory = inventory_repository(root)
            detection = detect_projects(root, inventory)
            first = evaluate_dependency_checks(root, inventory, detection)
            second = evaluate_dependency_checks(root, inventory, detection)

            self.assertEqual(
                [finding.to_dict() for finding in first],
                [finding.to_dict() for finding in second],
            )
            self.assertFalse((root / "executed-marker.txt").exists())


if __name__ == "__main__":
    unittest.main()
