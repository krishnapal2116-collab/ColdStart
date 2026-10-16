# ColdStart

ColdStart is a local-first software-repository reproducibility auditor. It helps developers, maintainers, students, buildathon participants, small teams, and reviewers determine whether a Python repository contains enough evidence for another environment to recreate it.

## Current status

**Phase 0 design freeze, Phase 2/M1, Phase 3/M2 discovery/applicability, M3 Python checks, M4 complete P0 static catalog checks, M5 offline hardening/self-audit coverage, and the first M6 verification slice are implemented.** The bounded read-only inventory, Python/Node/unknown/mixed detection, fail-closed local policy, applicability plan, complete static catalog, report evidence, release-file checks, deterministic self-audit, redaction checks, explicit verification plans, structured authorized test execution, bounded receipts, and Docker-unavailable handling are implemented. Target-runtime, Make, Docker, network-isolated test execution, and clean project test/build verification remain environment or P1 gaps in the current workspace.

ColdStart's P0 product is a deterministic, read-only CLI audit. It does not call a generative AI API, upload repository data, install the inspected project's dependencies, or execute repository commands. P1 verification is a separate command: it prints a plan, requires `--authorize` before starting a child process, and records a bounded receipt. Docker-based clean builds and network-isolated test execution remain optional capabilities and are not required for static audit usefulness.

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

The M1 audit engine validates the selected readable repository boundary, emits a deterministic terminal or JSON report, and returns a documented exit code. M2 adds a bounded metadata inventory, project candidates, catalog applicability decisions, and explicit partial-coverage evidence. M3 evaluates dependency declarations, applicable Python lock evidence, runtime declarations, and setup documentation. M4 completes the remaining seven P0 static checks. M6 adds a separate explicit verification command; all 13 catalog checks remain read-only and non-executing, and they do not claim that project tests or builds ran.

## Phase 1 foundation

Phase 1 provides the package/toolchain foundation, help/version commands, and an offline standard-library test suite. Phase 2/M1 adds the safe `audit` report core, boundary validation, evidence strength, deterministic fingerprints, and terminal/JSON output. Phase 3/M2 adds bounded deterministic discovery, project detection, fail-closed `.coldstart.toml` policy parsing, applicability planning, inventory limits, exclusions, and visible skipped-check evidence. M3 adds static dependency, lockfile, runtime, and setup-documentation findings. M4 completes static test-command, configuration, environment-variable, portability, security, build-configuration, and contained-path findings. M6 adds `verify --plan`, explicit authorization, safe direct Python test execution, bounded receipts, source-manifest comparison, and fixed Docker build planning. A static pass never implies that verification ran.

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

`make test` is the canonical Linux command. The direct source-tree 117-test suite currently passes with 114 tests run and 3 platform-expected skips under Python 3.14.7. Docker build/run, `make test`, and the exact Python 3.12.8 setup must still be verified on an environment that provides those tools.

## P1 verification preview

Review a bounded plan without starting a child process:

```text
PYTHONPATH=src python -m coldstart verify PATH --kind tests --offline --plan
```

To explicitly authorize a supported direct Python test command after reviewing the plan:

```text
PYTHONPATH=src python -m coldstart verify PATH --kind tests --authorize
```

Docker verification uses a fixed `docker build` argv and returns `not_verified` with exit code `3` when Docker is unavailable. The current host runner does not claim network-isolated test execution: an authorized `--offline` test attempt returns `not_verified` until a network-isolated runner is available.

## Safety promise

Static inspection is read-only and non-executing by default. Every finding must identify its rule, status, severity, evidence or limitation, and remediation where appropriate. `not_applicable`, `skipped`, and `not_verified` are not passes. ColdStart must never claim tests or builds passed unless an authorized execution actually produced that evidence.

## Phase 0, M1, M2, M3, M4, M5, and M6 checks

Phase 0 was checked with Markdown-link, JSON-contract, requirement-ID, whitespace, and cross-document consistency validation. M1/M2/M3/M4/M5/M6 have a passing 117-test offline integration/unit suite: 114 tests ran successfully and 3 platform-expected cases were skipped under Python 3.14.7. The current machine lacks Python 3.12.8, `make`, and Docker; network-isolated test execution is deliberately reported `not_verified` rather than overclaimed. ColdStart itself cannot be declared reproducible until the target commands run successfully.
