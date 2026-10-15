# ColdStart Implementation and Release Plan

**Status:** Awaiting explicit owner approval
**Version:** 0.2
**Rule:** No application source code may be created or modified until this plan and the document pack are explicitly approved.

## 1. Milestone method

Work proceeds in vertical slices. Each milestone ends with actual checks, documentation updates, and a focused Git checkpoint. A generated file or an intended test is not evidence of completion.

## 2. Ordered milestones

### M0 — Reproducible repository foundation

- **Goal:** Make the ColdStart repository itself buildable and testable.
- **Requirements:** FR-017, NFR-009, NFR-011.
- **Expected files/modules:** `.python-version`, `pyproject.toml`, lockfiles, `Dockerfile`, `Makefile`, `src/coldstart/version.py`, test runner skeleton, README setup section.
- **Dependencies:** Owner approval; Python 3.12.8; chosen packaging tools.
- **Tasks:** Create package metadata, pin runtime/dependencies, add Dockerfile, define `make test`, add help/version smoke test.
- **Tests:** Clean setup, package import, help/version, offline `make test`, Docker build/run.
- **Acceptance:** Clean Linux checkout follows exact commands; no hidden global dependency.
- **Failure conditions:** Unpinned dependency, Docker build failure, or missing offline command blocks progress.
- **Git checkpoint:** `build: establish reproducible ColdStart toolchain`.
- **Relative effort:** Medium.

### M1 — Smallest end-to-end static audit

- **Goal:** `coldstart audit PATH` validates a directory and emits a truthful empty/minimal report.
- **Requirements:** FR-001, FR-002, FR-006, FR-007, FR-009, FR-010, FR-011; NFR-001, NFR-002.
- **Expected files/modules:** `cli`, `boundary`, `findings`, `reporting`, `policy`.
- **Dependencies:** M0.
- **Tasks:** Implement argument parsing, boundary result, normalized report model, terminal/JSON serializers, exit codes.
- **Tests:** Valid/invalid path, six status values, schema validation, terminal/JSON parity, no subprocess.
- **Acceptance:** A safe audit of a fixture produces stable output and never runs project code.
- **Failure conditions:** Report cannot represent unknowns, JSON/terminal disagree, or invalid paths reach discovery.
- **Git checkpoint:** `feat: add safe audit command and report model`.
- **Relative effort:** Medium.

### M2 — Discovery and applicability

- **Goal:** Build deterministic bounded inventory and Python/unknown/mixed detection.
- **Requirements:** FR-003, FR-004, FR-012, FR-014, FR-015; NFR-005, NFR-006, NFR-007.
- **Expected files/modules:** `discovery`, `config`, file-limit logic, fixture inventory cases.
- **Dependencies:** M1.
- **Tasks:** Add sorted inventory, limits, exclusions, symlink handling, TOML policy parsing, applicability decisions.
- **Tests:** Large/malformed/unreadable/symlink/path fixtures, invalid config, repeated inventory.
- **Acceptance:** Coverage limits and applicability are visible; no external symlink is followed.
- **Failure conditions:** Unbounded read, policy fail-open, or non-deterministic discovery.
- **Git checkpoint:** `feat: add bounded discovery and applicability`.
- **Relative effort:** Medium.

### M3 — Python P0 check slice

- **Goal:** Implement the first half of the catalog: discovery, dependency, lockfile, runtime, and setup checks.
- **Requirements:** FR-005, FR-008, FR-016; NFR-012.
- **Expected files/modules:** `checks/registry`, `checks/python`, evidence/redaction helpers, clean/defective fixtures.
- **Dependencies:** M2.
- **Tasks:** Implement exact catalog algorithms, evidence, remediation, and rule versions.
- **Tests:** Positive/negative/edge/false-positive cases for each rule; contract snapshots.
- **Acceptance:** Defective fixture produces expected findings and clean fixture does not inherit them.
- **Failure conditions:** Rule lacks applicability or evidence, or a false positive is accepted without review.
- **Git checkpoint:** `feat: implement Python dependency and runtime checks`.
- **Relative effort:** Large.

### M4 — Remaining catalog and release reports

- **Goal:** Complete P0 documentation/configuration/path/security/container-discovery checks and polished reports.
- **Requirements:** FR-005, FR-008, FR-009, FR-010, FR-011, FR-012, FR-016; NFR-003, NFR-008.
- **Expected files/modules:** remaining `checks`, redaction, terminal formatting, JSON schema validator/fixtures, report docs.
- **Dependencies:** M3.
- **Tasks:** Add remaining checks, status counts, no-color output, secret-safe evidence, policy/strict behavior.
- **Tests:** Full catalog matrix, secret/path/control-character tests, terminal/JSON parity, exit matrix.
- **Acceptance:** All 13 P0 checks appear with correct applicability/status and remediation.
- **Failure conditions:** Secret leakage, hidden skipped checks, schema mismatch, or report overclaim.
- **Git checkpoint:** `feat: complete P0 reproducibility report`.
- **Relative effort:** Large.

### M5 — P0 hardening and clean release candidate

- **Goal:** Demonstrate the small working product under competition constraints.
- **Requirements:** All P0 FR/NFR; especially FR-013–017 and NFR-001–012.
- **Expected files/modules:** tests, fixtures, docs, CI/local scripts, release evidence.
- **Dependencies:** M4.
- **Tasks:** Run complete offline suite, clean Linux build, Docker build of ColdStart, cross-platform smoke checks, documentation audit, demo preparation.
- **Tests:** `make test`, clean checkout, Docker build/run, security suite, deterministic snapshots, no-network test.
- **Acceptance:** P0 definition of done and all release-blocking defects closed.
- **Failure conditions:** Any false pass, unsafe execution, reproducibility gap, or undocumented requirement.
- **Git checkpoint:** `release: ColdStart P0 candidate`.
- **Relative effort:** Large and reserved time.

### M6 — Optional P1 verification layer

- **Goal:** Add explicit offline test and clean Docker build verification without changing P0 safety.
- **Requirements:** FR-018, FR-019, NFR-013, NFR-014.
- **Expected files/modules:** `execution` broker, plan/authorization, staging, Docker runner, receipts, P1 fixtures.
- **Dependencies:** M5; Docker-enabled environment; threat-model review.
- **Tasks:** Implement structured argv, plan prompt, network/resource/output limits, timeout/cleanup, manifest comparison, Docker build attempt.
- **Tests:** Authorization denial, pass/fail, timeout, network deny, Docker unavailable, cleanup, source unchanged.
- **Acceptance:** No execution occurs without explicit plan/approval; actual results are recorded.
- **Failure conditions:** Host fallback, unbounded process, hidden network, or Docker overclaim.
- **Git checkpoint:** `feat: add authorized Docker verification`.
- **Relative effort:** Very large; omit if it threatens P0.

### M7 — Optional competition enhancements

- **Goal:** Add only a small number of P1 features that improve the demo without destabilizing P0.
- **Requirements:** FR-020, FR-021, or FR-022 only if selected.
- **Expected files/modules:** SARIF/baseline/additional adapter, focused tests/docs.
- **Dependencies:** M5 and owner decision.
- **Tasks:** Select one feature, update contract/traceability, implement, test, and demo it honestly.
- **Tests:** Feature-specific contract and regression tests.
- **Acceptance:** P0 remains green and the feature is clearly versioned.
- **Failure conditions:** Scope expansion or contract regression.
- **Git checkpoint:** `feat: add approved P1 enhancement`.
- **Relative effort:** Small to large depending on choice; may be skipped.

## 3. Release gates

### Gate G0 — Toolchain

Pinned runtime, lockfiles, Dockerfile, README commands, and a real offline test command exist and are actually run.

### Gate G1 — Safety

Default audit is read-only/non-executing; threat tests pass; no secrets/control sequences leak.

### Gate G2 — P0 behavior

All catalog fixtures, clean/defective examples, report contract, exit codes, and deterministic-output tests pass.

### Gate G3 — Reproducibility

Clean Linux rebuild and Docker build/run succeed using repository-contained instructions and no global dependency.

### Gate G4 — Release and demo

Documentation, limitations, GitHub/README checklist, and demo use actual recorded output. Owner approves the release candidate.

P1 gates are additive and cannot waive a P0 gate.

## 4. Time protection

Reserve at least one implementation slice for integration and security fixes, one for clean-build verification, and one for documentation/demo review. If time becomes constrained, remove M6/M7 features before reducing P0 safety or evidence quality.
