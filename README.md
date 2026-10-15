# ColdStart

ColdStart is a local-first software-repository reproducibility auditor. It helps developers, maintainers, students, buildathon participants, small teams, and reviewers determine whether a Python repository contains enough evidence for another environment to recreate it.

## Current status

**Phase 0 design freeze and Phase 2/M1 audit slice are complete.** The safe boundary/report core is implemented; target-runtime, Make, and Docker verification remain environment gaps in the current workspace. Ecosystem discovery and the P0 catalog checks are still planned for the next slice.

ColdStart's P0 product is a deterministic, read-only CLI audit. It does not call a generative AI API, upload repository data, install the inspected project's dependencies, or execute repository commands. Docker-based clean builds and offline test execution are P1 capabilities that require explicit authorization and are useful but not required for static audit usefulness.

ColdStart is a diagnostic tool, not a guarantee that a repository works on every computer.

## Document pack

The required implementation-start specification is:

1. [Project charter](docs/00_PROJECT_CHARTER.md)
2. [Product requirements](docs/01_PRODUCT_REQUIREMENTS.md)
3. [MVP scope and acceptance](docs/02_MVP_SCOPE_AND_ACCEPTANCE.md)
4. [System architecture](docs/03_SYSTEM_ARCHITECTURE.md)
5. [Threat model](docs/04_THREAT_MODEL.md)
6. [Privacy and data handling](docs/05_PRIVACY_AND_DATA_HANDLING.md)
7. [P0 check catalog](docs/06_CHECK_CATALOG.md)
8. [CLI and report contracts](docs/07_CLI_AND_REPORT_CONTRACTS.md)
9. [Requirement traceability](docs/08_REQUIREMENT_TRACEABILITY.md)
10. [Test strategy](docs/09_TEST_STRATEGY.md)
11. [Build and reproducibility](docs/10_BUILD_AND_REPRODUCIBILITY.md)
12. [Architecture decisions](docs/11_ARCHITECTURE_DECISIONS.md)
13. [Implementation and release plan](docs/12_IMPLEMENTATION_AND_RELEASE_PLAN.md)
14. [Demo and submission plan](docs/13_DEMO_AND_SUBMISSION_PLAN.md)
15. [Documentation quality audit](docs/14_DOCUMENTATION_AUDIT.md)

The machine-readable report contract is documented in `docs/07_CLI_AND_REPORT_CONTRACTS.md` and accompanied by:

- [Report JSON Schema](docs/contracts/report-v1.schema.json)
- [Sanitized example report](docs/contracts/report-v1.example.json)

The advanced roadmap is intentionally layered: P0 adds evidence strength, deterministic audit fingerprints, self-audit, and no static staging workspace. P1 may add baseline comparison, rule explanations, policy profiles, and plan-only verification one at a time.

## Frozen P0 command for Phase 1

```text
coldstart audit PATH --format terminal
```

The M1 audit engine now validates the selected readable repository boundary, emits a deterministic terminal or JSON report, and returns a documented exit code. M1 intentionally does not inspect project files or run ecosystem checks.

## Phase 1 foundation

Phase 1 provides the package/toolchain foundation, help/version commands, and an offline standard-library test suite. Phase 2/M1 adds the safe `audit` report core, boundary validation, evidence strength, deterministic fingerprints, and terminal/JSON output. The report explicitly marks the not-yet-implemented discovery/catalog scope as `not_verified`.

Target setup requires Python 3.12.8:

```text
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
```

The Phase 1 source-tree smoke commands are:

```text
PYTHONPATH=src python -m coldstart --help
PYTHONPATH=src python -m coldstart version
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py' -v
```

`make test` is the canonical Linux command. Docker build/run and the exact Python 3.12.8 setup must still be verified on an environment that provides those tools.

## Safety promise

Static inspection is read-only and non-executing by default. Every finding must identify its rule, status, severity, evidence or limitation, and remediation where appropriate. `not_applicable`, `skipped`, and `not_verified` are not passes. ColdStart must never claim tests or builds passed unless an authorized execution actually produced that evidence.

## Phase 0 and M1 checks

Phase 0 was checked with Markdown-link, JSON-contract, requirement-ID, whitespace, and cross-document consistency validation. M1 has 14 passing offline integration/unit tests under Python 3.14.7. The current machine lacks Python 3.12.8, `make`, and Docker, so those target-environment checks remain unverified. ColdStart itself cannot be declared reproducible until those commands run successfully.
