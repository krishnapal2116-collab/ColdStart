"""Offline Phase 3/M2 discovery, limits, and applicability tests.

These tests deliberately use the public CLI/report contract.  The M2 source
slice is not present on the phase3-m2-tests branch yet; the tests are intended
to become the acceptance slice when that core is merged.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the source-tree CLI without installing anything or using a network."""

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


def load_json_report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if not result.stdout.strip():
        raise AssertionError(
            f"expected a JSON report on stdout; stderr was {result.stderr!r}"
        )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise AssertionError(f"expected a JSON object report, got {type(value)!r}")
    return value


def run_json(
    repository: Path, *options: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    result = run_cli("audit", str(repository), "--format", "json", *options)
    return result, load_json_report(result)


@contextlib.contextmanager
def fixture_repository(
    files: Mapping[str, str | bytes] | None = None,
) -> Iterator[Path]:
    """Yield an isolated repository fixture with deterministic initial files."""

    with tempfile.TemporaryDirectory(prefix="coldstart-m2-") as temporary_directory:
        repository = Path(temporary_directory) / "fixture-project"
        repository.mkdir()
        if files:
            write_files(repository, files)
        yield repository


def write_files(repository: Path, files: Mapping[str, str | bytes]) -> None:
    for relative_path, contents in files.items():
        destination = repository / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            destination.write_bytes(contents)
        else:
            destination.write_text(contents, encoding="utf-8")


def python_fixture_files() -> dict[str, str]:
    return {
        ".python-version": "3.12.8\n",
        "pyproject.toml": (
            "[project]\n"
            "name = 'm2-python-fixture'\n"
            "version = '0.1.0'\n"
            "requires-python = '>=3.12,<3.13'\n"
            "dependencies = []\n"
        ),
        "requirements.lock": "# deliberately empty for a dependency-free fixture\n",
        "src/m2_fixture/__init__.py": '"""M2 Python fixture."""\n',
        "tests/test_fixture.py": "import unittest\n\n\nclass FixtureTest(unittest.TestCase):\n    def test_present(self):\n        self.assertTrue(True)\n",
    }


def node_fixture_files() -> dict[str, str]:
    return {
        "package.json": (
            '{"name":"m2-node-fixture","version":"1.0.0",'
            '"scripts":{"test":"node test.js"}}\n'
        ),
        "package-lock.json": '{"name":"m2-node-fixture","lockfileVersion":3,"packages":{}}\n',
        "index.js": "module.exports = {};\n",
        "test.js": "console.log('fixture');\n",
    }


def inventory_records(report: Mapping[str, object]) -> list[object]:
    """Return the M2 inventory from its documented report area.

    The report schema permits additive fields.  During the M2 merge the
    inventory may live under ``repository``, ``repository.boundary``,
    ``detection``, or a top-level ``discovery`` object; accepting those
    contract-equivalent locations keeps the tests focused on behavior rather
    than a private dataclass layout.
    """

    containers: list[object] = [report]
    for key in ("repository", "detection", "discovery"):
        value = report.get(key)
        if isinstance(value, Mapping):
            containers.append(value)
            if key == "repository":
                boundary = value.get("boundary")
                if isinstance(boundary, Mapping):
                    containers.append(boundary)

    for container in containers:
        if not isinstance(container, Mapping):
            continue
        for key in ("inventory", "file_inventory", "files"):
            value = container.get(key)
            if isinstance(value, list):
                return value
    raise AssertionError("M2 report does not expose a file inventory")


def inventory_paths(report: Mapping[str, object]) -> list[str]:
    paths: list[str] = []
    for record in inventory_records(report):
        if isinstance(record, str):
            path = record
        elif isinstance(record, Mapping):
            path_value = None
            for key in ("path", "relative_path", "name"):
                if isinstance(record.get(key), str):
                    path_value = record[key]
                    break
            if path_value is None:
                continue
            path = path_value
        else:
            continue
        paths.append(path.replace("\\", "/"))
    return paths


def inventory_sizes(report: Mapping[str, object]) -> list[int]:
    sizes: list[int] = []
    for record in inventory_records(report):
        if not isinstance(record, Mapping):
            continue
        for key in ("size", "bytes", "byte_count"):
            value = record.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                sizes.append(value)
                break
    return sizes


def detection_candidates(report: Mapping[str, object]) -> list[Mapping[str, object]]:
    detection = report.get("detection")
    if not isinstance(detection, Mapping):
        raise AssertionError("report detection must be an object")
    candidates = detection.get("candidates")
    if not isinstance(candidates, list):
        raise AssertionError("report detection.candidates must be an array")
    return [candidate for candidate in candidates if isinstance(candidate, Mapping)]


def candidate_ids(report: Mapping[str, object]) -> set[str]:
    ids: set[str] = set()
    for candidate in detection_candidates(report):
        for key in ("id", "type", "name", "ecosystem"):
            value = candidate.get(key)
            if isinstance(value, str):
                ids.add(value.lower())
                break
    return ids


def applicability_records(report: Mapping[str, object]) -> list[Mapping[str, object]]:
    detection = report.get("detection")
    if not isinstance(detection, Mapping):
        raise AssertionError("report detection must be an object")
    records = detection.get("applicability")
    if not isinstance(records, list):
        raise AssertionError("report detection.applicability must be an array")
    return [record for record in records if isinstance(record, Mapping)]


def report_limits(report: Mapping[str, object]) -> Mapping[str, object]:
    invocation = report.get("invocation")
    if not isinstance(invocation, Mapping):
        raise AssertionError("report invocation must be an object")
    limits = invocation.get("limits")
    if not isinstance(limits, Mapping):
        raise AssertionError("report invocation.limits must be an object")
    return limits


def report_findings(report: Mapping[str, object]) -> list[Mapping[str, object]]:
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise AssertionError("report findings must be an array")
    return [finding for finding in findings if isinstance(finding, Mapping)]


def normalize_report(value: object) -> object:
    volatile_keys = {
        "created_at",
        "generated_at",
        "report_id",
        "run_id",
        "timestamp",
    }
    if isinstance(value, Mapping):
        return {
            str(key): normalize_report(item)
            for key, item in value.items()
            if key not in volatile_keys
        }
    if isinstance(value, list):
        return [normalize_report(item) for item in value]
    return value


def repository_manifest(repository: Path) -> dict[str, tuple[object, ...]]:
    """Capture content/type metadata without following symlinks."""

    manifest: dict[str, tuple[object, ...]] = {}
    for current, directories, files in os.walk(repository, followlinks=False):
        names = sorted(set(directories) | set(files))
        for name in names:
            path = Path(current) / name
            relative = path.relative_to(repository).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                manifest[relative] = ("symlink", os.readlink(path))
            elif stat.S_ISREG(metadata.st_mode):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest[relative] = (
                    "file",
                    metadata.st_mode,
                    metadata.st_size,
                    digest,
                )
            elif stat.S_ISDIR(metadata.st_mode):
                manifest[relative] = ("directory", metadata.st_mode)
    return manifest


def write_policy(repository: Path, text: str) -> Path:
    config = repository / ".coldstart.toml"
    config.write_text(text, encoding="utf-8")
    return config


VALID_CONFIG = """\
schema_version = "1.0"
name = "m2-review"
fail_on = "error"
treat_not_verified_as = "fail"
required_checks = ["CS-PROJECT-001"]
excluded_checks = ["CS-BUILD-001"]

[limits]
max_files = 5
max_bytes = 100000
max_depth = 8
max_seconds = 10
"""


class Phase3M2DiscoveryIntegrationTests(unittest.TestCase):
    def test_deterministic_inventory_is_sorted_and_stable(self) -> None:
        files = {
            "z-last.txt": "z\n",
            "a-first.txt": "a\n",
            "nested/z.txt": "nested z\n",
            "nested/a.txt": "nested a\n",
        }
        with fixture_repository(files) as repository:
            first_result, first_report = run_json(repository)
            second_result, second_report = run_json(repository)

        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        first_paths = inventory_paths(first_report)
        second_paths = inventory_paths(second_report)
        self.assertEqual(first_paths, sorted(first_paths))
        self.assertEqual(first_paths, second_paths)
        self.assertEqual(
            json.dumps(normalize_report(first_report), sort_keys=True),
            json.dumps(normalize_report(second_report), sort_keys=True),
        )

    def test_file_count_limit_bounds_inventory_and_reports_incomplete(self) -> None:
        files = {f"files/{index:02d}.txt": f"{index}\n" for index in range(8)}
        with fixture_repository(files) as repository:
            result, report = run_json(repository, "--max-files", "2")

        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(report_limits(report).get("max_files"), 2)
        self.assertLessEqual(len(inventory_paths(report)), 2)
        self.assertIn(report.get("summary", {}).get("overall"), {"incomplete", "needs_attention"})

    def test_byte_limit_bounds_inventory_and_reports_incomplete(self) -> None:
        files = {
            "small.txt": "ok\n",
            "large.txt": "x" * 512,
        }
        with fixture_repository(files) as repository:
            result, report = run_json(repository, "--max-bytes", "8")

        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(report_limits(report).get("max_bytes"), 8)
        paths = inventory_paths(report)
        self.assertNotIn("large.txt", paths)
        sizes = inventory_sizes(report)
        if sizes:
            self.assertLessEqual(sum(sizes), 8)

    def test_depth_limit_bounds_inventory_and_reports_incomplete(self) -> None:
        files = {
            "root.txt": "root\n",
            "one/allowed.txt": "one\n",
            "one/two/three/deep.txt": "deep\n",
        }
        with fixture_repository(files) as repository:
            result, report = run_json(repository, "--max-depth", "1")

        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(report_limits(report).get("max_depth"), 1)
        paths = inventory_paths(report)
        self.assertNotIn("one/two/three/deep.txt", paths)

    def test_time_limit_is_positive_and_recorded(self) -> None:
        with fixture_repository({"README.md": "bounded\n"}) as repository:
            result, report = run_json(repository, "--max-seconds", "1")
            invalid = run_cli(
                "audit",
                str(repository),
                "--format",
                "json",
                "--max-seconds",
                "0",
            )

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertEqual(report_limits(report).get("max_seconds"), 1)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid.stdout, "")

    def test_generated_directories_are_excluded_by_default(self) -> None:
        files = {
            "source.txt": "source\n",
            ".git/objects/ignored.txt": "git\n",
            ".venv/lib/ignored.txt": "venv\n",
            ".venv3128/lib/ignored.txt": "pinned venv\n",
            "__pycache__/ignored.pyc": b"cache\n",
            "build/generated.txt": "build\n",
            "dist/generated.txt": "dist\n",
            "node_modules/generated.js": "node\n",
        }
        with fixture_repository(files) as repository:
            result, report = run_json(repository)

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        paths = inventory_paths(report)
        for path in paths:
            self.assertFalse(
                path == ".git" or path.startswith(".git/"),
                f"generated .git path was inventoried: {path}",
            )
            self.assertFalse(
                path == ".venv" or path.startswith(".venv/"),
                f"generated .venv path was inventoried: {path}",
            )
            self.assertFalse(
                path == ".venv3128" or path.startswith(".venv3128/"),
                f"generated .venv3128 path was inventoried: {path}",
            )
            self.assertFalse(
                path == "__pycache__" or path.startswith("__pycache__/"),
                f"generated __pycache__ path was inventoried: {path}",
            )
            self.assertFalse(
                path == "build" or path.startswith("build/"),
                f"generated build path was inventoried: {path}",
            )
            self.assertFalse(
                path == "dist" or path.startswith("dist/"),
                f"generated dist path was inventoried: {path}",
            )
            self.assertFalse(
                path == "node_modules" or path.startswith("node_modules/"),
                f"generated node_modules path was inventoried: {path}",
            )

    def test_symlink_inventory_does_not_follow_internal_or_external_targets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coldstart-m2-links-") as temporary_directory:
            parent = Path(temporary_directory)
            repository = parent / "fixture-project"
            repository.mkdir()
            outside = parent / "outside-only.txt"
            outside.write_text(
                "EXTERNAL_TARGET_SENTINEL_SHOULD_NOT_BE_READ\n", encoding="utf-8"
            )
            (repository / "inside.txt").write_text("inside\n", encoding="utf-8")
            try:
                (repository / "internal-link.txt").symlink_to(
                    repository / "inside.txt"
                )
                (repository / "external-link.txt").symlink_to(outside)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlinks unavailable on this platform: {error}")

            result, report = run_json(repository)

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertEqual(
            report.get("repository", {}).get("boundary", {}).get("external_symlinks"),
            "not_followed",
        )
        paths = inventory_paths(report)
        self.assertTrue(
            "internal-link.txt" in paths or "external-link.txt" in paths,
            "symlink entries should be represented or explicitly diagnosed",
        )
        self.assertNotIn("EXTERNAL_TARGET_SENTINEL_SHOULD_NOT_BE_READ", result.stdout)

    def test_python_detection_and_applicability_data(self) -> None:
        with fixture_repository(python_fixture_files()) as repository:
            result, report = run_json(repository)

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertIn("python", candidate_ids(report))
        records = applicability_records(report)
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertIsInstance(record.get("check_id"), str)
            self.assertIsInstance(record.get("applicable"), bool)
            self.assertIsInstance(record.get("reason"), str)
            self.assertIsInstance(record.get("adapter"), str)
        self.assertTrue(any(record.get("applicable") for record in records))

    def test_node_detection(self) -> None:
        with fixture_repository(node_fixture_files()) as repository:
            result, report = run_json(repository)

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertIn("node", candidate_ids(report))

    def test_unknown_detection_is_explicit(self) -> None:
        with fixture_repository(
            {"notes.txt": "unrecognized content\n", "data.bin": b"\x00\x01\x02"}
        ) as repository:
            result, report = run_json(repository)

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        detection = report.get("detection")
        self.assertIsInstance(detection, Mapping)
        assert isinstance(detection, Mapping)
        text = json.dumps(detection, sort_keys=True).lower()
        self.assertTrue(
            "unknown" in candidate_ids(report)
            or detection.get("status") in {"unknown", "unsupported"}
            or "unknown" in text,
            f"unknown project type was not explicit: {detection!r}",
        )
        records = applicability_records(report)
        self.assertGreater(len(records), 0)
        self.assertTrue(
            any(record.get("applicable") is False for record in records),
            "unsupported ecosystem checks must be explicitly not applicable",
        )

    def test_mixed_detection_keeps_python_and_node_candidates(self) -> None:
        files = python_fixture_files()
        files.update(node_fixture_files())
        with fixture_repository(files) as repository:
            result, report = run_json(repository)

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        ids = candidate_ids(report)
        self.assertIn("python", ids)
        self.assertIn("node", ids)
        detection = report.get("detection")
        self.assertIsInstance(detection, Mapping)
        assert isinstance(detection, Mapping)
        if "status" in detection:
            self.assertEqual(detection["status"], "mixed")

    def test_valid_config_applies_limits_exclusions_and_policy(self) -> None:
        files = python_fixture_files()
        files["generated/ignored.txt"] = "generated\n"
        with fixture_repository(files) as repository:
            config = write_policy(repository, VALID_CONFIG)
            result, report = run_json(repository, "--config", str(config))

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertEqual(report_limits(report).get("max_files"), 5)
        invocation = report.get("invocation")
        self.assertIsInstance(invocation, Mapping)
        assert isinstance(invocation, Mapping)
        self.assertTrue(str(invocation.get("config_path", "")).endswith(".coldstart.toml"))

        policy = report.get("policy")
        self.assertIsInstance(policy, Mapping)
        assert isinstance(policy, Mapping)
        self.assertEqual(policy.get("name"), "m2-review")
        self.assertEqual(policy.get("treat_not_verified_as"), "fail")

        excluded = [
            finding
            for finding in report_findings(report)
            if finding.get("check_id") == "CS-BUILD-001"
        ]
        self.assertTrue(excluded, "configured excluded check should remain visible")
        self.assertTrue(any(finding.get("status") == "skipped" for finding in excluded))

    def test_malformed_toml_fails_closed_before_inventory(self) -> None:
        with fixture_repository(
            {
                "project_script.py": (
                    "from pathlib import Path\n"
                    "Path('executed-marker.txt').write_text('executed')\n"
                ),
                ".coldstart.toml": "[limits\nmax_files = 1\n",
            }
        ) as repository:
            result = run_cli(
                "audit",
                str(repository),
                "--format",
                "json",
                "--config",
                str(repository / ".coldstart.toml"),
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotEqual(result.stderr.strip(), "")
            self.assertFalse((repository / "executed-marker.txt").exists())

    def test_invalid_or_forbidden_config_fails_closed(self) -> None:
        invalid_configs = {
            "wrong schema": 'schema_version = "9.9"\n',
            "zero limit": 'schema_version = "1.0"\n[limits]\nmax_files = 0\n',
            "bad unknown policy": (
                'schema_version = "1.0"\n'
                'treat_not_verified_as = "ignore"\n'
            ),
            "forbidden command": (
                'schema_version = "1.0"\n'
                'command = ["sh", "-c", "touch executed-marker.txt"]\n'
            ),
            "forbidden url": (
                'schema_version = "1.0"\n'
                'remote_url = "https://example.invalid/config"\n'
            ),
        }
        for label, contents in invalid_configs.items():
            with self.subTest(config=label), fixture_repository(
                {
                    "project_script.py": (
                        "from pathlib import Path\n"
                        "Path('executed-marker.txt').write_text('executed')\n"
                    ),
                    ".coldstart.toml": contents,
                }
            ) as repository:
                result = run_cli(
                    "audit",
                    str(repository),
                    "--format",
                    "json",
                    "--config",
                    str(repository / ".coldstart.toml"),
                )

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse((repository / "executed-marker.txt").exists())

    def test_cli_limits_and_exclude_options_are_recorded_and_applied(self) -> None:
        files = {
            "source.txt": "source\n",
            "generated/ignored.txt": "ignored\n",
        }
        with fixture_repository(files) as repository:
            result, report = run_json(
                repository,
                "--max-files",
                "20",
                "--max-bytes",
                "10000",
                "--max-depth",
                "4",
                "--max-seconds",
                "5",
                "--exclude",
                "generated",
            )

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        limits = report_limits(report)
        self.assertEqual(limits.get("max_files"), 20)
        self.assertEqual(limits.get("max_bytes"), 10000)
        self.assertEqual(limits.get("max_depth"), 4)
        self.assertEqual(limits.get("max_seconds"), 5)
        self.assertNotIn("generated/ignored.txt", inventory_paths(report))
        boundary = report.get("repository", {}).get("boundary", {})
        if isinstance(boundary, Mapping) and isinstance(boundary.get("exclusions"), list):
            self.assertIn("generated", boundary["exclusions"])

    def test_repeated_m2_reports_and_fingerprints_are_stable(self) -> None:
        files = python_fixture_files()
        files.update({"z.txt": "z\n", "a.txt": "a\n"})
        with fixture_repository(files) as repository:
            first_result, first_report = run_json(repository)
            second_result, second_report = run_json(repository)

        self.assertEqual(first_result.returncode, second_result.returncode)
        self.assertEqual(inventory_paths(first_report), inventory_paths(second_report))
        self.assertEqual(candidate_ids(first_report), candidate_ids(second_report))
        first_repository = first_report.get("repository")
        second_repository = second_report.get("repository")
        self.assertIsInstance(first_repository, Mapping)
        self.assertIsInstance(second_repository, Mapping)
        assert isinstance(first_repository, Mapping)
        assert isinstance(second_repository, Mapping)
        self.assertEqual(
            first_repository.get("audit_fingerprint"),
            second_repository.get("audit_fingerprint"),
        )
        self.assertEqual(
            json.dumps(normalize_report(first_report), sort_keys=True),
            json.dumps(normalize_report(second_report), sort_keys=True),
        )

    def test_static_audit_is_read_only_and_creates_no_staging(self) -> None:
        files = {
            "README.md": "## Install\nDo not run this file.\n",
            "project_script.py": (
                "from pathlib import Path\n"
                "Path('executed-marker.txt').write_text('executed')\n"
            ),
            "src/app.py": "print('untrusted project code')\n",
        }
        with fixture_repository(files) as repository:
            before = repository_manifest(repository)
            result, report = run_json(repository)
            after = repository_manifest(repository)

        self.assertIn(result.returncode, {0, 1, 3}, result.stderr)
        self.assertEqual(before, after)
        self.assertNotIn("executed-marker.txt", after)
        verification = report.get("verification")
        self.assertIsInstance(verification, Mapping)
        assert isinstance(verification, Mapping)
        self.assertEqual(verification.get("executions"), [])

    def test_malformed_fixture_is_partial_not_false_pass(self) -> None:
        files = {
            "pyproject.toml": "[project\nname = 'broken'\n",
            "package.json": '{"name": "broken",\n',
            "src/valid.py": "value = 1\n",
            "binary.dat": b"\x00\xff\x00\xff",
        }
        with fixture_repository(files) as repository:
            result, report = run_json(repository)

        self.assertIn(result.returncode, {1, 3, 4}, result.stderr)
        findings = report_findings(report)
        statuses = {finding.get("status") for finding in findings}
        self.assertTrue(
            statuses & {"error", "not_verified"},
            f"malformed input did not produce an incomplete/error finding: {findings!r}",
        )
        summary = report.get("summary")
        self.assertIsInstance(summary, Mapping)
        assert isinstance(summary, Mapping)
        self.assertNotEqual(summary.get("overall"), "pass")
        diagnostic_text = json.dumps(report, sort_keys=True).lower()
        self.assertTrue(
            any(token in diagnostic_text for token in ("malformed", "invalid", "parse", "error")),
            "malformed fixture lacks a bounded diagnostic",
        )

    def test_unreadable_fixture_is_reported_when_platform_permits(self) -> None:
        if os.name == "nt":
            self.skipTest("portable unreadable-file semantics are unavailable on Windows")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read chmod-0 fixtures")

        with fixture_repository(
            {
                "pyproject.toml": "[project]\nname = 'unreadable'\n",
                "src/valid.py": "value = 1\n",
            }
        ) as repository:
            unreadable = repository / "pyproject.toml"
            unreadable.chmod(0)
            if os.access(unreadable, os.R_OK):
                unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)
                self.skipTest("filesystem did not provide an unreadable fixture")
            try:
                result, report = run_json(repository)
            finally:
                unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)

        self.assertIn(result.returncode, {1, 3, 4}, result.stderr)
        diagnostic_text = json.dumps(report, sort_keys=True).lower()
        statuses = {finding.get("status") for finding in report_findings(report)}
        self.assertTrue(
            "unreadable" in diagnostic_text
            or "permission" in diagnostic_text
            or bool(statuses & {"error", "not_verified"}),
            "unreadable fixture was not represented as incomplete evidence",
        )


if __name__ == "__main__":
    unittest.main()
