# ColdStart Implementation and Approval Plan

**Status:** Awaiting explicit owner approval
**Version:** 0.1
**Rule:** No application source code may be written until this document pack and this plan are explicitly approved.

## 1. Current gate

The planning phase is complete enough to review. The workspace contains documentation only. No application source, dependency installation, project execution, Docker build, or runtime setup has been performed.

Implementation may start only after the owner confirms all of the following:

- the product definition and first-release scope;
- the recommended Python 3.12 CLI baseline;
- the Python and Node.js first-class adapter scope;
- the read-only default and explicit execution authorization model;
- Docker-backed verification with no automatic host fallback;
- the versioned terminal/JSON contract and exit codes;
- the security, privacy, and failure-mode constraints;
- the verification gates and buildathon reproducibility requirements.

## 2. Recommended implementation sequence

Each phase is a small, reviewable working step. After each phase, the implementation must run the smallest meaningful checks, update documentation, and create a focused Git commit. A phase must not be declared complete from intent alone.

### Phase 1 — Repository and packaging foundation

Deliver:

- pinned Python runtime declaration;
- `pyproject.toml` and committed lockfile;
- minimal package structure;
- Dockerfile that can build and run the CLI;
- Makefile with the canonical offline `make test` command;
- README setup, run, test, build, and deploy instructions;
- no project-dependent installation during static ColdStart scans.

Checks:

- clean checkout setup on Linux;
- `make test` offline;
- Docker build and smoke run;
- package version and report schema version output.

### Phase 2 — Safe workspace and static core

Deliver:

- CLI argument and path validation;
- scan boundary and symlink policy;
- bounded file inventory;
- generic detection and evidence model;
- status/severity model;
- safe redaction and terminal escaping.

Checks:

- boundary, limit, symlink, malformed-input, and redaction unit tests;
- safe first-scan acceptance scenario A-001;
- no project process execution in static tests.

### Phase 3 — Adapters, checks, and reporting

Deliver:

- adapter registry;
- Python and Node.js adapters;
- generic runtime, dependency, lockfile, setup, test, build, portability, and local-assumption checks;
- documentation consistency checks;
- terminal renderer;
- versioned JSON renderer;
- policy evaluation and exit codes.

Checks:

- fixture integration suite;
- report contract suite;
- terminal/JSON parity;
- traceability matrix updated for every check.

### Phase 4 — Authorized verification

Deliver:

- execution-plan presentation;
- interactive and non-interactive authorization rules;
- staging and manifest comparison;
- Docker-backed test runner;
- Docker build runner;
- timeout, resource, output, network, and cleanup controls;
- execution receipts.

Checks:

- approval/denial tests;
- pass, fail, timeout, unavailable, and cleanup-failure tests;
- Docker-enabled integration suite;
- confirmation that the original project remains unchanged.

### Phase 5 — Hardening and release readiness

Deliver:

- cross-platform path/process handling;
- performance measurements against representative fixtures;
- security review and dependency review;
- CI example and strict policy example;
- baseline/diff design decision for a later release;
- final user documentation and troubleshooting.

Checks:

- complete offline `make test`;
- clean Linux rebuild from scratch;
- Windows and macOS smoke checks where available;
- Docker build/run from a clean checkout;
- all release gates in the verification strategy;
- final audit of reports, secrets, and documentation.

## 3. Planned first-release deliverables

| Deliverable | Acceptance evidence |
| --- | --- |
| Cross-platform CLI | Help, version, safe scan, JSON output, and documented exit codes |
| Generic scanner | Works without project dependencies or network |
| Python adapter | Runtime/dependencies/docs/build/test checks with fixtures |
| Node.js adapter | Runtime/dependencies/docs/build/test checks with fixtures |
| Terminal report | Evidence, severity, status, and suggested fixes |
| JSON report | Contract version, stable IDs, provenance, and execution section |
| Policy support | Strict/permissive unknown handling and CI exit code |
| Authorized verification | Docker-backed tests and Docker build with receipts |
| Project reproducibility | Pinned runtime, lockfile, Dockerfile, offline `make test`, exact README instructions |
| Security posture | Threat controls and security test evidence |

## 4. Definition of done

ColdStart is ready for owner acceptance when:

1. A clean Linux checkout can set up and run it using only repository-documented steps.
2. `make test` completes offline and covers unit, contract, integration, and security suites appropriate to the release.
3. The Dockerfile builds and runs the CLI from a clean checkout.
4. A default scan never executes project code, installs dependencies, sends network traffic, or mutates the inspected project.
5. Authorized verification cannot run without a displayed plan and explicit approval or an explicit CI policy.
6. Every report finding has evidence or a precise unknown/error reason.
7. An execution result contains actual exit status, limits, authorization state, and cleanup result.
8. Secret, command-injection, path-escape, resource, timeout, and terminal-control tests pass.
9. The implementation and report contract are traceable to this document pack.
10. A reviewer can reproduce the release from a clean Linux machine without relying on global packages or hidden files.

## 5. Owner approval checklist

The owner should approve or request changes to these decisions:

- [ ] Product statement and target users.
- [ ] First release is CLI/local-first rather than a GUI or hosted service.
- [ ] Python 3.12 is the recommended implementation runtime.
- [ ] Python and Node.js receive full adapters first; other ecosystems receive generic checks and honest unknowns.
- [ ] Static inspection is the default and does not execute project code.
- [ ] Tests and Docker builds require distinct explicit authorization.
- [ ] Docker-backed verification is preferred; Docker absence does not trigger host execution.
- [ ] Network is disabled by default for verification.
- [ ] Terminal and JSON report contract version `1.0` is acceptable.
- [ ] Exit codes `0` through `4` are acceptable.
- [ ] `.coldstart.toml` is the proposed local policy format.
- [ ] Readiness scoring is optional and non-authoritative.
- [ ] The listed out-of-scope features are deferred.

## 6. Approval response

An acceptable approval message is:

> I approve the ColdStart document pack and implementation plan in commit `<commit-id>`. Proceed with Phase 1 only, following the stated safety, verification, and reproducibility gates.

The owner may instead identify specific sections to revise. Until approval is recorded, the next action is documentation revision or review, not implementation.
