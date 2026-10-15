# ColdStart

ColdStart is a local-first software-repository reproducibility auditor. It helps developers, maintainers, students, buildathon participants, small teams, and reviewers determine whether a Python repository contains enough evidence for another environment to recreate it.

## Current status

**Phase 0 design freeze is complete. Phase 1 application implementation has not started and remains blocked pending explicit implementation approval.** This workspace contains specifications and report-contract artifacts, but no ColdStart application source, dependency environment, executable, Dockerfile, or test suite.

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

The frozen P0 command will inspect the selected local repository, report applicable findings, and return a documented exit code. It has not been implemented or executed.

## Safety promise

Static inspection is read-only and non-executing by default. Every finding must identify its rule, status, severity, evidence or limitation, and remediation where appropriate. `not_applicable`, `skipped`, and `not_verified` are not passes. ColdStart must never claim tests or builds passed unless an authorized execution actually produced that evidence.

## Phase 0 checks

No application test suite exists yet. Phase 0 was checked with Markdown-link, JSON-contract, requirement-ID, whitespace, and cross-document consistency validation. Phase 1 still requires a pinned Python runtime, hash-checked lockfiles, Dockerfile, offline `make test`, clean Linux rebuild, and exact README setup/run/test/build/deploy instructions before ColdStart itself can be declared reproducible.
