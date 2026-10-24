"""Contract tests for the M6/M6.1 verification report boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "clean-python"


def run_verify(
    *arguments: str,
    path_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the CLI from the repository root with the in-tree source path."""

    environment = os.environ.copy()
    environment["PYTHONPATH"] = "src"
    if path_override is not None:
        environment["PATH"] = path_override
    return subprocess.run(
        [sys.executable, "-m", "coldstart", "verify", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def load_report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Decode one JSON CLI report and include stderr when decoding fails."""

    if not result.stdout.strip():
        raise AssertionError(f"expected JSON report; stderr was {result.stderr!r}")
    report = json.loads(result.stdout)
    if not isinstance(report, dict):
        raise AssertionError("expected a JSON report object")
    return report


class Phase6M6ContractTests(unittest.TestCase):
    def test_report_schema_declares_verification_plan_and_receipt_contract(self) -> None:
        schema_path = ROOT / "docs" / "contracts" / "report-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        definitions = schema["$defs"]
        verification = definitions["verification"]
        for required_field in ("requested", "authorized", "executions"):
            self.assertIn(required_field, verification["required"])

        expected_statuses = {
            "not_requested",
            "planned",
            "denied",
            "passed",
            "failed",
            "not_verified",
            "unavailable",
            "timeout",
            "incomplete",
            "error",
        }
        self.assertIn("status", verification["properties"])
        status_enum = set(verification["properties"]["status"]["enum"])
        self.assertTrue(expected_statuses <= status_enum)

        self.assertIn("plan", verification["properties"])
        self.assertEqual(
            verification["properties"]["plan"]["$ref"],
            "#/$defs/execution_plan",
        )

        self.assertIn("execution_plan", definitions)
        execution_plan = definitions["execution_plan"]
        for required_field in ("runner", "isolation", "sandbox", "no_host_fallback"):
            self.assertIn(required_field, execution_plan["required"])

        self.assertIn("execution", definitions)
        execution = definitions["execution"]
        for required_field in (
            "execution_id",
            "kind",
            "status",
            "authorization",
            "cleanup_status",
        ):
            self.assertIn(required_field, execution["required"])

    def test_offline_plan_report_is_docker_isolated_and_path_safe(self) -> None:
        result = run_verify(
            "examples/clean-python",
            "--kind",
            "tests",
            "--offline",
            "--plan",
            "--format",
            "json",
        )
        report = load_report(result)

        self.assertEqual(result.returncode, 0, result.stderr)
        verification = report["verification"]
        plan = verification["plan"]
        self.assertEqual(plan["runner"], "docker")
        self.assertEqual(plan["isolation"], "docker")
        self.assertEqual(plan["sandbox"], "docker")
        self.assertTrue(plan["no_host_fallback"])
        self.assertEqual(plan["network_mode"], "none")
        self.assertEqual(plan["image"], "python:3.12.8-slim-bookworm")

        repository_mount = plan["repository_mount"]
        self.assertEqual(repository_mount["target"], "/workspace")
        self.assertTrue(repository_mount["read_only"])

        plan_argv = plan["argv"]
        self.assertIn("--read-only", plan_argv)
        self.assertIn("<repository>:/workspace:ro", plan_argv)
        self.assertEqual(
            plan["resource_limits"],
            {
                "cpus": "1",
                "memory": "512m",
                "pids_limit": "256",
                "tmpfs": "/tmp:rw,nosuid,nodev,noexec,size=64m",
            },
        )

        serialized_plan = json.dumps(plan, sort_keys=True)
        absolute_paths = {
            str(ROOT),
            ROOT.as_posix(),
            str(EXAMPLE),
            EXAMPLE.as_posix(),
            os.path.abspath("examples/clean-python"),
        }
        for absolute_path in absolute_paths:
            self.assertNotIn(absolute_path, serialized_plan)

    def test_authorized_offline_report_is_fail_closed_without_host_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m6-contract-no-docker-") as empty_path:
            result = run_verify(
                "examples/clean-python",
                "--kind",
                "tests",
                "--offline",
                "--authorize",
                "--format",
                "json",
                path_override=empty_path,
            )
        report = load_report(result)

        self.assertIn(result.returncode, {1, 3, 4}, result.stderr)
        verification = report["verification"]
        executions = verification["executions"]
        self.assertEqual(len(executions), 1)
        receipt = executions[0]
        self.assertIn(receipt["status"], {"not_verified", "failed", "error"})
        self.assertTrue(receipt["no_host_fallback"])
        self.assertFalse(receipt["host_fallback"])
        self.assertEqual(receipt["fallback_policy"], "none")
        self.assertIn("no host fallback", receipt["reason"].lower())


if __name__ == "__main__":
    unittest.main()
