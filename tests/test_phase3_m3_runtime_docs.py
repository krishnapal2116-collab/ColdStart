"""Focused offline tests for the standalone M3 runtime/docs checks."""

from __future__ import annotations

import contextlib
import dataclasses
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path

from coldstart.checks.runtime_docs import evaluate_runtime_and_setup_checks
from coldstart.discovery import detect_projects, inventory_repository


@contextlib.contextmanager
def fixture_repository(files: Mapping[str, str | bytes]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="coldstart-m3-runtime-docs-") as temporary_directory:
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


def evaluate(root: Path, *, excluded_checks=()):
    inventory = inventory_repository(root)
    detection = detect_projects(root, inventory)
    return evaluate_runtime_and_setup_checks(
        root,
        inventory,
        detection,
        excluded_checks=excluded_checks,
    )


def finding_map(findings):
    return {finding.check_id: finding for finding in findings}


COMPLETE_README = """# Example

## Prerequisites
Use Python 3.12.

## Installation
```sh
python -m pip install -e .
```

## Configuration
Set APP_ENV=development before starting.

## Run
```sh
python -m example
```
"""


class Phase3M3RuntimeDocumentationTests(unittest.TestCase):
    def test_exact_runtime_pin_and_matching_range_pass(self) -> None:
        with fixture_repository(
            {
                ".python-version": "3.12.8\n",
                "pyproject.toml": (
                    "[project]\n"
                    "name = 'runtime-fixture'\n"
                    "requires-python = '>=3.12,<3.13'\n"
                ),
                "README.md": COMPLETE_README,
                "src/app.py": "raise RuntimeError('must not execute')\n",
            }
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-RUNTIME-001"].status, "passed")
        self.assertEqual(findings["CS-RUNTIME-001"].severity, "info")
        self.assertEqual(findings["CS-RUNTIME-001"].rule_version, "3")
        self.assertEqual(findings["CS-RUNTIME-001"].category, "runtime")

    def test_runtime_absent_fails(self) -> None:
        with fixture_repository({"pyproject.toml": "[project]\nname = 'absent'\n", "src/app.py": ""}) as root:
            runtime = finding_map(evaluate(root))["CS-RUNTIME-001"]

        self.assertEqual(runtime.status, "failed")
        self.assertTrue(any(item.kind == "absence" for item in runtime.evidence))

    def test_conflicting_machine_readable_runtime_declarations_fail(self) -> None:
        with fixture_repository(
            {
                ".python-version": "3.11.9\n",
                "pyproject.toml": "[project]\nrequires-python = '>=3.12,<3.13'\n",
            }
        ) as root:
            runtime = finding_map(evaluate(root))["CS-RUNTIME-001"]

        self.assertEqual(runtime.status, "failed")
        self.assertTrue(any(item.kind == "error" for item in runtime.evidence))

    def test_malformed_runtime_is_not_verified(self) -> None:
        with fixture_repository({".python-version": "python-latest\n"}) as root:
            runtime = finding_map(evaluate(root))["CS-RUNTIME-001"]

        self.assertEqual(runtime.status, "not_verified")
        self.assertTrue(any(item.kind == "error" for item in runtime.evidence))

    def test_partial_inventory_runtime_is_not_verified(self) -> None:
        with fixture_repository({".python-version": "3.12.8\n"}) as root:
            inventory = inventory_repository(root)
            partial_inventory = dataclasses.replace(
                inventory,
                truncated=True,
                omission_reasons=("file_limit",),
            )
            detection = detect_projects(root, inventory)
            runtime = finding_map(
                evaluate_runtime_and_setup_checks(root, partial_inventory, detection)
            )["CS-RUNTIME-001"]

        self.assertEqual(runtime.status, "not_verified")

    def test_complete_readme_setup_guidance_passes(self) -> None:
        with fixture_repository({"README.md": COMPLETE_README, "app.py": ""}) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-001"]

        self.assertEqual(docs.status, "passed")
        self.assertEqual(docs.severity, "info")
        self.assertEqual(docs.category, "documentation")
        self.assertEqual(len(docs.evidence), 4)

    def test_incomplete_readme_guidance_fails(self) -> None:
        with fixture_repository({"README.md": "# Example\n\nA small Python project.\n"}) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-001"]

        self.assertEqual(docs.status, "failed")
        self.assertTrue(any(item.kind == "absence" for item in docs.evidence))

    def test_missing_readme_setup_guidance_fails(self) -> None:
        with fixture_repository({"app.py": "print('static only')\n"}) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-001"]

        self.assertEqual(docs.status, "failed")
        self.assertTrue(any(item.kind == "absence" for item in docs.evidence))

    def test_non_python_runtime_is_not_applicable_but_docs_are_generic(self) -> None:
        with fixture_repository(
            {
                "package.json": '{"name": "node-fixture"}\n',
                "index.js": "module.exports = {};\n",
                "README.md": COMPLETE_README,
            }
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-RUNTIME-001"].status, "not_applicable")
        self.assertFalse(findings["CS-RUNTIME-001"].applicability.applicable)
        self.assertEqual(findings["CS-DOCS-001"].status, "passed")
        self.assertTrue(findings["CS-DOCS-001"].applicability.applicable)
        self.assertEqual(findings["CS-DOCS-001"].applicability.adapter, "generic")

    def test_exclusion_remains_visible_with_policy_evidence(self) -> None:
        with fixture_repository({".python-version": "3.12.8\n", "README.md": COMPLETE_README}) as root:
            findings = finding_map(evaluate(root, excluded_checks=("CS-RUNTIME-001",)))

        runtime = findings["CS-RUNTIME-001"]
        self.assertEqual(runtime.status, "skipped")
        self.assertEqual(runtime.applicability.adapter, "policy")
        self.assertTrue(any(item.kind == "policy" for item in runtime.evidence))
        self.assertEqual(findings["CS-DOCS-001"].status, "passed")

    def test_results_are_deterministic_and_do_not_execute_source(self) -> None:
        with fixture_repository(
            {
                ".python-version": "3.12.8\n",
                "README.md": COMPLETE_README,
                "src/project.py": (
                    "from pathlib import Path\n"
                    "Path('executed-marker.txt').write_text('executed')\n"
                ),
            }
        ) as root:
            inventory = inventory_repository(root)
            detection = detect_projects(root, inventory)
            first = evaluate_runtime_and_setup_checks(root, inventory, detection)
            second = evaluate_runtime_and_setup_checks(root, inventory, detection)

            self.assertEqual(
                [finding.to_dict() for finding in first],
                [finding.to_dict() for finding in second],
            )
            self.assertFalse((root / "executed-marker.txt").exists())


if __name__ == "__main__":
    unittest.main()
