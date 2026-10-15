# ColdStart

ColdStart is a local-first reproducibility readiness scanner and verifier. It helps a developer determine whether another person can recreate and run a software project without relying on undocumented local state.

## Current status

**Planning only. Implementation is intentionally blocked pending explicit approval of the document pack and implementation plan.** This workspace currently contains no application source code, dependency manifest, executable, or runtime environment for ColdStart.

The approved planning boundary is:

1. Inspect a supplied project path without executing project code.
2. Identify the project type and reproducibility evidence.
3. Report passed, failed, not-verified, and skipped checks with evidence.
4. Suggest practical fixes.
5. With explicit permission, verify supported tests and a clean Docker build.

## Product definition

> ColdStart is a safe, evidence-based tool that checks whether a software project can be recreated by someone else. It scans project files by default, explains missing or inconsistent reproducibility information, and—with explicit permission—verifies documented tests and clean builds in an isolated environment.

## Document pack

Read the documents in this order:

1. [Product definition](docs/01-product-definition.md)
2. [Scope and requirements](docs/02-scope-and-requirements.md)
3. [Architecture](docs/03-architecture.md)
4. [Security, privacy, and threat model](docs/04-security-privacy-threat-model.md)
5. [Interface and data contract](docs/05-interface-and-data-contract.md)
6. [Audit rules and observability](docs/06-audit-rules-and-observability.md)
7. [Failure modes and resilience](docs/07-failure-modes-and-resilience.md)
8. [Verification strategy](docs/08-verification-strategy.md)
9. [Requirements traceability](docs/09-requirements-traceability.md)
10. [Implementation and approval plan](docs/10-implementation-and-approval-plan.md)
11. [Documentation audit](docs/11-documentation-audit.md)
12. [Decision log](docs/12-decision-log.md)

## Recommended implementation baseline

The specification recommends a cross-platform Python 3.12 CLI with a standard-library-first core, an adapter model for project ecosystems, terminal and versioned JSON reports, and Docker-backed execution for authorized verification. This is a proposal, not an implementation decision, until the owner approves the plan.

## Safety promise

ColdStart must be read-only by default. It must not install dependencies, run project commands, contact a network service, upload project contents, or modify the inspected project unless the user explicitly authorizes a clearly described operation. Findings must never claim that a test or build passed unless ColdStart actually ran it and recorded the result.

## Planning-phase checks

No application test suite exists yet because implementation has not been approved. The planning deliverable is validated with documentation consistency review and `git diff --check`. The implementation plan requires a single offline `make test` command, a pinned runtime, a lockfile, a Dockerfile, and a README with exact setup, run, test, and deploy steps before application work is considered complete.
