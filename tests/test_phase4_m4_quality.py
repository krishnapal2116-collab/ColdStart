"""Focused offline tests for the standalone M4 quality checks."""

from __future__ import annotations

import contextlib
import dataclasses
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path

from coldstart.checks.quality import QUALITY_READ_LIMIT, evaluate_quality_checks
from coldstart.discovery import FileRecord, detect_projects, inventory_repository


@contextlib.contextmanager
def fixture_repository(files: Mapping[str, str | bytes]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="coldstart-m4-quality-") as temporary_directory:
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
    return evaluate_quality_checks(
        root,
        inventory,
        detection,
        excluded_checks=excluded_checks,
    )


def finding_map(findings):
    return {finding.check_id: finding for finding in findings}


class Phase4M4QualityTests(unittest.TestCase):
    def test_exact_stable_contract_and_rule_version(self) -> None:
        with fixture_repository({"README.md": "A clean repository.\n"}) as root:
            findings = evaluate(root)

        self.assertEqual(
            [finding.check_id for finding in findings],
            ["CS-PORT-001", "CS-SEC-001", "CS-BUILD-001", "CS-PATH-001"],
        )
        self.assertEqual(len(findings), 4)
        self.assertTrue(all(finding.rule_version == "4" for finding in findings))

    def test_portability_redacts_home_path_and_escalates_setup_command(self) -> None:
        with fixture_repository(
            {
                "README.md": "The checkout may live at /home/alice/project.\n",
                "scripts/setup.sh": "cd /home/alice/project\n",
            }
        ) as root:
            port = finding_map(evaluate(root))["CS-PORT-001"]

        self.assertEqual(port.status, "failed")
        self.assertEqual(port.severity, "error")
        rendered = repr(port.to_dict())
        self.assertNotIn("/home/alice/project", rendered)
        self.assertNotIn("alice", rendered)
        self.assertTrue(all("indicator=" in item.detail for item in port.evidence))

    def test_portability_system_urls_workdirs_regex_and_examples_are_exempt(self) -> None:
        with fixture_repository(
            {
                "README.md": (
                    "Use https://example.test/home/alice and /usr/bin/python.\n"
                    "Hosts are listed in /etc/hosts and scratch uses /tmp/cache.\n"
                    "For example: /home/your-user/project.\n"
                    "Regex: /home/[a-z]+/project.\n"
                ),
                "Dockerfile": "FROM python:3.12\nWORKDIR /home/container\n",
            }
        ) as root:
            port = finding_map(evaluate(root))["CS-PORT-001"]

        self.assertEqual(port.status, "passed")

    def test_windows_and_home_reference_categories_are_redacted(self) -> None:
        with fixture_repository(
            {
                "config.yml": "cache: C:\\Users\\alice\\project\nhome: $HOME/project\n",
            }
        ) as root:
            port = finding_map(evaluate(root))["CS-PORT-001"]

        self.assertEqual(port.status, "failed")
        self.assertEqual(port.severity, "warning")
        details = " ".join(item.detail for item in port.evidence)
        self.assertIn("windows-drive-path", details)
        self.assertIn("host-home-path", details)
        self.assertNotIn("alice", repr(port.to_dict()))

    def test_private_key_is_blocking_and_secret_values_are_redacted(self) -> None:
        secret = "super-secret-value-not-for-output"
        with fixture_repository(
            {
                "config.py": (
                    "API_TOKEN = " + repr(secret) + "\n"
                    "PRIVATE_KEY = '-----BEGIN PRIVATE KEY-----'\n"
                )
            }
        ) as root:
            security = finding_map(evaluate(root))["CS-SEC-001"]

        self.assertEqual(security.status, "failed")
        self.assertEqual(security.severity, "blocking")
        rendered = repr(security.to_dict())
        self.assertNotIn(secret, rendered)
        self.assertNotIn("BEGIN PRIVATE KEY", rendered)
        self.assertTrue(all("raw_value=omitted" in item.detail for item in security.evidence))

    def test_weak_credential_indicator_warns_and_placeholders_random_values_do_not(self) -> None:
        with fixture_repository(
            {
                "config.yml": (
                    "TOKEN: abc\n"
                    "API_KEY: ${API_KEY}\n"
                    "PASSWORD: example-password\n"
                    "RANDOM_STRING: 012345678901234567890123456789\n"
                ),
                ".env.example": "SECRET=realistic-looking-example\n",
            }
        ) as root:
            security = finding_map(evaluate(root))["CS-SEC-001"]

        self.assertEqual(security.status, "failed")
        self.assertEqual(security.severity, "warning")
        self.assertTrue(all("credential-assignment" in item.detail for item in security.evidence))
        self.assertNotIn("realistic-looking-example", repr(security.to_dict()))

    def test_binary_random_content_is_not_scanned_as_text(self) -> None:
        with fixture_repository(
            {"artifact.bin": b"\x00-----BEGIN PRIVATE KEY-----\x00TOKEN=actual-secret"}
        ) as root:
            security = finding_map(evaluate(root))["CS-SEC-001"]

        self.assertEqual(security.status, "passed")

    def test_container_claim_without_configuration_fails(self) -> None:
        with fixture_repository(
            {"README.md": "Docker is required to build and run this application.\n"}
        ) as root:
            build = finding_map(evaluate(root))["CS-BUILD-001"]

        self.assertEqual(build.status, "failed")
        self.assertEqual(build.severity, "error")
        self.assertTrue(any(item.kind == "absence" for item in build.evidence))

    def test_container_configuration_and_metadata_pass_without_building(self) -> None:
        with fixture_repository(
            {
                "README.md": "Build the image with Docker.\n",
                "Dockerfile": "FROM python:3.12\nCOPY app.py /app/app.py\n",
                ".dockerignore": ".git\n",
                "app.py": "print('safe')\n",
                "compose.yaml": "services:\n  app:\n    build: .\n",
            }
        ) as root:
            build = finding_map(evaluate(root))["CS-BUILD-001"]

        self.assertEqual(build.status, "passed")
        self.assertEqual(build.severity, "info")
        self.assertTrue(any("docker-from-metadata" in item.detail for item in build.evidence))

    def test_container_workflow_without_claim_or_configuration_is_not_applicable(self) -> None:
        with fixture_repository({"README.md": "This project has no container workflow.\n"}) as root:
            build = finding_map(evaluate(root))["CS-BUILD-001"]

        self.assertEqual(build.status, "not_applicable")
        self.assertFalse(build.applicability.applicable)

    def test_docker_escape_and_missing_resource_are_errors(self) -> None:
        with fixture_repository(
            {
                "Dockerfile": (
                    "FROM alpine\n"
                    "COPY ../outside.txt /app/outside.txt\n"
                    "COPY missing.txt /app/missing.txt\n"
                )
            }
        ) as root:
            path = finding_map(evaluate(root))["CS-PATH-001"]

        self.assertEqual(path.status, "failed")
        self.assertEqual(path.severity, "error")
        details = " ".join(item.detail for item in path.evidence)
        self.assertIn("lexical-parent-escape", details)
        self.assertIn("missing-local-resource", details)

    def test_contained_docker_resource_passes_path_check(self) -> None:
        with fixture_repository(
            {
                "Dockerfile": "FROM alpine\nCOPY assets /app/assets\n",
                "assets/logo.txt": "safe\n",
            }
        ) as root:
            path = finding_map(evaluate(root))["CS-PATH-001"]

        self.assertEqual(path.status, "passed")
        self.assertEqual(path.severity, "info")

    def test_external_symlink_is_detected_without_opening_target_when_supported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m4-quality-link-") as temporary_directory:
            root = Path(temporary_directory) / "root"
            outside = Path(temporary_directory) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "marker.txt").write_text("PRIVATE_KEY=must-not-be-read\n", encoding="utf-8")
            link = root / "external.txt"
            try:
                link.symlink_to(outside / "marker.txt")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this platform")
            inventory = inventory_repository(root)
            detection = detect_projects(root, inventory)
            findings = finding_map(evaluate_quality_checks(root, inventory, detection))

        self.assertEqual(findings["CS-PATH-001"].status, "failed")
        self.assertEqual(findings["CS-PATH-001"].severity, "warning")
        self.assertEqual(findings["CS-SEC-001"].status, "passed")
        self.assertNotIn("must-not-be-read", repr(findings))

    def test_partial_unreadable_and_malformed_inventory_are_not_verified(self) -> None:
        with fixture_repository(
            {
                "README.md": "Run setup from /home/alice/project.\n",
                "config.py": "API_TOKEN = 'secret-value'\n",
                "Dockerfile": "FROM alpine\nCOPY missing.txt /app/missing.txt\n",
            }
        ) as root:
            inventory = inventory_repository(root)
            detection = detect_projects(root, inventory)
            partial = dataclasses.replace(inventory, truncated=True, omission_reasons=("file_limit",))
            partial_findings = evaluate_quality_checks(root, partial, detection)

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
            unreadable_findings = evaluate_quality_checks(root, unreadable, detection)

            malformed = dataclasses.replace(
                inventory,
                records=inventory.records + (FileRecord("../outside.txt", "file", 1, 0),),
            )
            malformed_findings = evaluate_quality_checks(root, malformed, detection)

        for findings in (partial_findings, unreadable_findings, malformed_findings):
            self.assertTrue(all(finding.status == "not_verified" for finding in findings))
            self.assertTrue(all(item.path is None or not item.path.startswith("..") for finding in findings for item in finding.evidence))

    def test_hard_text_limit_is_visible(self) -> None:
        with fixture_repository(
            {"README.md": "x" * (QUALITY_READ_LIMIT + 1)}
        ) as root:
            findings = finding_map(evaluate(root))

        self.assertTrue(all(findings[check_id].status == "not_verified" for check_id in ("CS-PORT-001", "CS-SEC-001", "CS-BUILD-001", "CS-PATH-001")))

    def test_exclusions_are_visible_and_all_exclusions_do_not_inspect(self) -> None:
        check_ids = ("CS-PORT-001", "CS-SEC-001", "CS-BUILD-001", "CS-PATH-001")
        with fixture_repository({"evil.py": "raise RuntimeError('must not execute')\n"}) as root:
            findings = evaluate(root, excluded_checks=check_ids)

        self.assertEqual([finding.check_id for finding in findings], list(check_ids))
        self.assertTrue(all(finding.status == "skipped" for finding in findings))
        self.assertTrue(all(finding.evidence[0].kind == "policy" for finding in findings))

    def test_results_are_deterministic_and_never_execute_repository_code(self) -> None:
        with fixture_repository(
            {
                "README.md": "No container claim.\n",
                "src/evil.py": (
                    "from pathlib import Path\n"
                    "Path('executed-marker.txt').write_text('executed')\n"
                ),
                "config.py": "RANDOM_STRING = '012345678901234567890123456789'\n",
            }
        ) as root:
            inventory = inventory_repository(root)
            detection = detect_projects(root, inventory)
            first = evaluate_quality_checks(root, inventory, detection)
            second = evaluate_quality_checks(root, inventory, detection)

        self.assertEqual(
            [finding.to_dict() for finding in first],
            [finding.to_dict() for finding in second],
        )
        self.assertFalse((root / "executed-marker.txt").exists())


if __name__ == "__main__":
    unittest.main()
