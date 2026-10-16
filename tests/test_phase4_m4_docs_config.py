"""Focused offline tests for the standalone M4 documentation/config checks."""

from __future__ import annotations

import contextlib
import dataclasses
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path

from coldstart.checks.docs_config import (
    DOCS_CONFIG_READ_LIMIT,
    evaluate_docs_and_config_checks,
)
from coldstart.discovery import FileRecord, detect_projects, inventory_repository


@contextlib.contextmanager
def fixture_repository(files: Mapping[str, str | bytes]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="coldstart-m4-docs-config-") as temporary_directory:
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
    return evaluate_docs_and_config_checks(
        root,
        inventory,
        detection,
        excluded_checks=excluded_checks,
    )


def finding_map(findings):
    return {finding.check_id: finding for finding in findings}


class Phase4M4DocumentationConfigurationTests(unittest.TestCase):
    def test_positive_command_and_safe_configuration_template(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": (
                    "# Fixture\n\n"
                    "## Tests\n\nRun `python -m pytest`.\n\n"
                    "## Configuration\n\nSet DATABASE_URL before starting.\n"
                ),
                ".env.example": "DATABASE_URL=${DATABASE_URL}\n",
                "src/app.py": "DATABASE_URL = os.environ[\"DATABASE_URL\"]\n",
            }
        ) as root:
            findings = evaluate(root)

        self.assertEqual(
            [finding.check_id for finding in findings],
            ["CS-DOCS-002", "CS-CONFIG-001", "CS-CONFIG-002"],
        )
        by_id = finding_map(findings)
        self.assertEqual(by_id["CS-DOCS-002"].status, "passed")
        self.assertEqual(by_id["CS-DOCS-002"].severity, "info")
        self.assertEqual(by_id["CS-CONFIG-001"].status, "passed")
        self.assertEqual(by_id["CS-CONFIG-001"].severity, "info")
        self.assertEqual(by_id["CS-CONFIG-002"].status, "passed")
        self.assertEqual(by_id["CS-CONFIG-002"].severity, "info")
        self.assertTrue(all(finding.rule_version == "4" for finding in findings))

    def test_missing_test_command_is_error_for_test_bearing_repository(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": "# Fixture\n\nA description without a test command.\n",
            }
        ) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-002"]

        self.assertEqual(docs.status, "failed")
        self.assertEqual(docs.severity, "error")
        self.assertTrue(any(item.kind == "absence" for item in docs.evidence))

    def test_test_configuration_contradiction_is_warning(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "pytest.ini": "[pytest]\ntestpaths = tests\n",
                "README.md": "Run `python -m unittest`.\n",
            }
        ) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-002"]

        self.assertEqual(docs.status, "failed")
        self.assertEqual(docs.severity, "warning")
        self.assertTrue(any(item.kind == "metadata" for item in docs.evidence))
        self.assertTrue(any("unittest" in item.detail for item in docs.evidence))

    def test_shell_chain_is_evidence_but_not_a_command_candidate(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": "```sh\npytest && rm -f marker.txt\n```\n",
            }
        ) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-002"]

        self.assertEqual(docs.status, "failed")
        self.assertEqual(docs.severity, "error")
        shell_items = [item for item in docs.evidence if item.kind == "command"]
        self.assertTrue(shell_items)
        self.assertTrue(all("unsupported shell composition" in item.detail for item in shell_items))

    def test_readme_command_without_test_evidence_is_not_applicable(self) -> None:
        with fixture_repository({"README.md": "Run `pytest`.\n"}) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-002"]

        self.assertEqual(docs.status, "not_applicable")
        self.assertFalse(docs.applicability.applicable)

    def test_makefile_target_and_ci_command_are_test_bearing(self) -> None:
        with fixture_repository(
            {
                "Makefile": "test:\n\tpytest\n",
                ".github/workflows/test.yml": "jobs:\n  test:\n    steps:\n      - run: pytest\n",
            }
        ) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-002"]

        self.assertEqual(docs.status, "passed")
        self.assertEqual(docs.severity, "info")

    def test_configuration_reference_without_safe_template_fails_without_secret_value(self) -> None:
        secret = "super-secret-not-for-output"
        with fixture_repository(
            {
                ".env": f"DATABASE_URL={secret}\n",
                "src/app.py": "value = os.environ[\"DATABASE_URL\"]\n",
            }
        ) as root:
            findings = evaluate(root)

        by_id = finding_map(findings)
        self.assertEqual(by_id["CS-CONFIG-001"].status, "failed")
        self.assertEqual(by_id["CS-CONFIG-002"].status, "failed")
        rendered = repr([finding.to_dict() for finding in findings])
        self.assertNotIn(secret, rendered)
        self.assertNotIn("DATABASE_URL=" + secret, rendered)

    def test_common_optional_environment_names_do_not_create_required_variable_finding(self) -> None:
        with fixture_repository(
            {
                "src/app.py": (
                    "import os\n"
                    "path = os.getenv('PATH')\n"
                    "debug = os.getenv('DEBUG', '0')\n"
                )
            }
        ) as root:
            config = finding_map(evaluate(root))

        self.assertEqual(config["CS-CONFIG-002"].status, "not_applicable")
        self.assertEqual(config["CS-CONFIG-001"].status, "not_applicable")

    def test_explicit_no_configuration_statement_suppresses_heading_false_positive(self) -> None:
        with fixture_repository(
            {"README.md": "## Configuration\n\nNo configuration is required.\n"}
        ) as root:
            config = finding_map(evaluate(root))

        self.assertEqual(config["CS-CONFIG-001"].status, "not_applicable")
        self.assertEqual(config["CS-CONFIG-002"].status, "not_applicable")

    def test_dynamic_environment_access_is_not_verified(self) -> None:
        with fixture_repository({"src/app.py": "value = os.getenv(variable_name)\n"}) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-CONFIG-001"].status, "not_verified")
        self.assertEqual(findings["CS-CONFIG-002"].status, "not_verified")

    def test_dynamic_environment_name_construction_is_not_treated_as_literal(self) -> None:
        with fixture_repository({"src/app.py": "value = os.getenv('PREFIX_' + suffix)\n"}) as root:
            findings = finding_map(evaluate(root))

        self.assertEqual(findings["CS-CONFIG-002"].status, "not_verified")
        rendered = repr(findings["CS-CONFIG-002"].to_dict())
        self.assertNotIn("PREFIX_", rendered)

    def test_malformed_and_partial_inventory_are_not_verified(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": "Run `pytest`.\n",
                "pyproject.toml": "[project\nname = 'broken'\n",
            }
        ) as root:
            inventory = inventory_repository(root)
            detection = detect_projects(root, inventory)
            malformed = finding_map(evaluate_docs_and_config_checks(root, inventory, detection))
            partial_inventory = dataclasses.replace(
                inventory,
                truncated=True,
                omission_reasons=("file_limit",),
            )
            partial = finding_map(
                evaluate_docs_and_config_checks(root, partial_inventory, detection)
            )

        self.assertEqual(malformed["CS-DOCS-002"].status, "not_verified")
        self.assertEqual(malformed["CS-CONFIG-001"].status, "not_verified")
        self.assertEqual(malformed["CS-CONFIG-002"].status, "not_verified")
        self.assertTrue(all(item.status == "not_verified" for item in partial.values()))

    def test_unreadable_and_malformed_paths_are_rejected(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": "Run `pytest`.\n",
            }
        ) as root:
            inventory = inventory_repository(root)
            unreadable_records = tuple(
                dataclasses.replace(record, readable=False)
                if record.relative_path == "README.md"
                else record
                for record in inventory.records
            )
            unreadable = dataclasses.replace(
                inventory,
                records=unreadable_records,
                unreadable_paths=("README.md",),
            )
            detection = detect_projects(root, unreadable)
            unreadable_findings = finding_map(
                evaluate_docs_and_config_checks(root, unreadable, detection)
            )

            malformed_records = inventory.records + (
                FileRecord("../outside.txt", "file", 1, 0),
            )
            malformed = dataclasses.replace(inventory, records=malformed_records)
            malformed_findings = finding_map(
                evaluate_docs_and_config_checks(root, malformed, detection)
            )

        self.assertEqual(unreadable_findings["CS-DOCS-002"].status, "not_verified")
        self.assertTrue(all(item.status == "not_verified" for item in malformed_findings.values()))
        self.assertTrue(all(item.path is None or not item.path.startswith("..") for item in malformed_findings["CS-DOCS-002"].evidence))

    def test_symlink_inventory_entries_are_not_read(self) -> None:
        with fixture_repository({"README.md": "Run `pytest`.\n"}) as root:
            inventory = inventory_repository(root)
            symlink_inventory = dataclasses.replace(
                inventory,
                records=inventory.records
                + (FileRecord("tests/test_link.py", "symlink", 0, 1, external_symlink=True),),
            )
            detection = detect_projects(root, symlink_inventory)
            findings = finding_map(
                evaluate_docs_and_config_checks(root, symlink_inventory, detection)
            )

        self.assertEqual(findings["CS-DOCS-002"].status, "not_verified")
        self.assertTrue(any(item.kind == "error" for item in findings["CS-DOCS-002"].evidence))

    def test_hard_per_file_limit_is_visible(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": "pytest\n" + ("x" * DOCS_CONFIG_READ_LIMIT),
            }
        ) as root:
            docs = finding_map(evaluate(root))["CS-DOCS-002"]

        self.assertEqual(docs.status, "not_verified")
        self.assertTrue(any(item.kind == "error" for item in docs.evidence))

    def test_exclusions_are_visible_and_do_not_change_other_findings(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": "Run `pytest`.\n",
            }
        ) as root:
            findings = finding_map(
                evaluate(root, excluded_checks=("CS-DOCS-002", "CS-CONFIG-001"))
            )

        self.assertEqual(findings["CS-DOCS-002"].status, "skipped")
        self.assertEqual(findings["CS-CONFIG-001"].status, "skipped")
        self.assertEqual(findings["CS-CONFIG-002"].status, "not_applicable")
        self.assertTrue(all(any(item.kind == "policy" for item in findings[key].evidence) for key in ("CS-DOCS-002", "CS-CONFIG-001")))
        self.assertTrue(all(findings[key].rule_version == "4" for key in findings))

    def test_all_exclusions_return_exactly_three_policy_findings_without_reading(self) -> None:
        with fixture_repository({"tests/test_app.py": "raise RuntimeError('must not execute')\n"}) as root:
            findings = evaluate(
                root,
                excluded_checks=("CS-DOCS-002", "CS-CONFIG-001", "CS-CONFIG-002"),
            )

        self.assertEqual(len(findings), 3)
        self.assertEqual([item.status for item in findings], ["skipped"] * 3)
        self.assertTrue(all(item.evidence[0].kind == "policy" for item in findings))

    def test_results_are_deterministic_and_never_execute_source(self) -> None:
        with fixture_repository(
            {
                "tests/test_app.py": "def test_app():\n    assert True\n",
                "README.md": "Run `python -m unittest`.\n",
                "src/project.py": (
                    "from pathlib import Path\n"
                    "Path('executed-marker.txt').write_text('executed')\n"
                ),
            }
        ) as root:
            inventory = inventory_repository(root)
            detection = detect_projects(root, inventory)
            first = evaluate_docs_and_config_checks(root, inventory, detection)
            second = evaluate_docs_and_config_checks(root, inventory, detection)

            self.assertEqual(
                [finding.to_dict() for finding in first],
                [finding.to_dict() for finding in second],
            )
            self.assertFalse((root / "executed-marker.txt").exists())


if __name__ == "__main__":
    unittest.main()
