# ColdStart Implementation and Release Plan

**Status:** Phase 2/M1 audit core implemented; target verification pending
**Version:** 0.2
**Rule:** Phase 0 was documentation-only. Phase 1 implementation is approved; later slices still require their own checks and must not overclaim unavailable verification.

## 1. Phase 0 closeout

Phase 0 has been executed as a documentation-only design freeze in response to the owner's instruction to implement Phase 0. The following baseline is frozen for Phase 1 planning:

- Python 3.12.8 and a standard-library-first deterministic core;
- CLI-first local operation with `coldstart audit PATH` as the P0 entry point;
- Python-focused P0 scope and the 13-check catalog;
- read-only, non-executing static audit;
- evidence-strength classes and deterministic audit fingerprints;
- no P0 repository staging workspace;
- terminal and versioned JSON report contract;
- P1-only Docker/test execution, explicit authorization, and plan-only preview;
- P1 advanced improvements added one at a time only after P0 is stable;
- local-only operation without a generative AI API or required network access.

The existing terminology assumptions remain explicit: “save repositories” means accept and scan a local repository, and “Zone report with documented sigma” means the versioned JSON report. They can be revised before Phase 1 without changing the safety principle.

Phase 0 completion did **not** mean that ColdStart built, ran, or passed tests. It meant that the implementation boundary and design baseline were recorded. Phase 1 is now approved, but its target-runtime and container checks remain subject to actual execution.

The owner approved implementation. The Phase 1 foundation and Phase 2/M1 audit core are present, but the current machine lacks Python 3.12.8, Make, and Docker. Therefore exact target-runtime, Make, and Docker acceptance remain unverified.

## 2. Milestone method

Work proceeds in vertical slices. Each milestone ends with actual checks, documentation updates, and a focused Git checkpoint. A generated file or an intended test is not evidence of completion.

## 3. Ordered milestones

### M0 — Reproducible repository foundation

**Current state:** Foundation implementation present; target-runtime, Make, and Docker checks pending in a suitable environment.

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

**Current state:** Implemented and tested under Python 3.14.7; exact target-runtime, Make, and Docker checks remain pending.

- **Goal:** `coldstart audit PATH` validates a directory and emits a truthful empty/minimal report.
- **Requirements:** FR-001, FR-002, FR-006, FR-007, FR-009, FR-010, FR-011, FR-028, FR-029; NFR-001, NFR-002, NFR-015.
- **Expected files/modules:** `cli`, `boundary`, `findings`, `reporting`, `policy`.
- **Dependencies:** M0.
- **Tasks:** Implement argument parsing, boundary result, normalized report model, evidence-strength taxonomy, audit fingerprint, terminal/JSON serializers, and exit codes.
- **Tests:** Valid/invalid path, six status values, evidence-strength values, fingerprint stability, schema validation, terminal/JSON parity, no subprocess.
- **Acceptance:** A safe audit of a fixture produces stable output and never runs project code.
- **Failure conditions:** Report cannot represent unknowns, JSON/terminal disagree, or invalid paths reach discovery.
- **Git checkpoint:** `feat: add safe audit command and report model`.
- **Relative effort:** Medium.

### M2 — Discovery and applicability

- **Goal:** Build deterministic bounded inventory and Python/unknown/mixed detection.
- **Requirements:** FR-003, FR-004, FR-012, FR-014, FR-015; NFR-005, NFR-006, NFR-007.
- **Expected files/modules:** `discovery`, `config`, file-limit logic, fixture inventory cases.
- **Dependencies:** M1.
- **Tasks:** Add sorted inventory, limits, exclusions, symlink handling, TOML policy parsing, applicability decisions, and the invariant that P0 creates no staging workspace.
- **Tests:** Large/malformed/unreadable/symlink/path fixtures, invalid config, repeated inventory, and P0 temporary-workspace observation.
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
- **Requirements:** All P0 FR/NFR; especially FR-013–017, FR-028–030, NFR-001–012, and NFR-015.
- **Expected files/modules:** tests, fixtures, docs, CI/local scripts, release evidence.
- **Dependencies:** M4.
- **Tasks:** Run complete offline suite, clean Linux build, Docker build of ColdStart, cross-platform smoke checks, self-audit the ColdStart repository, documentation audit, and demo preparation.
- **Tests:** `make test`, clean checkout, Docker build/run, security suite, deterministic snapshots, no-network test, and self-audit report review.
- **Acceptance:** P0 definition of done, a reviewed self-audit, and all release-blocking defects closed.
- **Failure conditions:** Any false pass, unsafe execution, reproducibility gap, or undocumented requirement.
- **Git checkpoint:** `release: ColdStart P0 candidate`.
- **Relative effort:** Large and reserved time.

### M6 — Optional P1 verification layer

- **Goal:** Add explicit offline test and clean Docker build verification without changing P0 safety.
- **Requirements:** FR-018, FR-019, NFR-013, NFR-014.
- **Expected files/modules:** `execution` broker, plan/authorization, staging, Docker runner, receipts, P1 fixtures.
- **Dependencies:** M5; Docker-enabled environment; threat-model review.
- **Tasks:** Implement plan-only preview first, then structured argv, approval prompt, network/resource/output limits, timeout/cleanup, manifest comparison, and Docker build attempt.
- **Tests:** Authorization denial, pass/fail, timeout, network deny, Docker unavailable, cleanup, source unchanged.
- **Acceptance:** No execution occurs without explicit plan/approval; actual results are recorded.
- **Failure conditions:** Host fallback, unbounded process, hidden network, or Docker overclaim.
- **Git checkpoint:** `feat: add authorized Docker verification`.
- **Relative effort:** Very large; omit if it threatens P0.

### M7 — Optional advanced improvements

- **Goal:** Add one evidence-preserving P1 enhancement without destabilizing P0.
- **Requirements:** FR-020, FR-021, FR-031, FR-032, FR-033, or FR-034 only if selected.
- **Expected files/modules:** baseline comparison, `explain` command, policy profiles, SARIF, or an additional adapter; focused tests/docs.
- **Dependencies:** M5 and owner decision.
- **Tasks:** Select exactly one feature after M5; update contract/traceability, implement, test, and demo it honestly. Prefer baseline/diff or `explain` before broader ecosystem support.
- **Tests:** Feature-specific contract and regression tests.
- **Acceptance:** P0 remains green, the feature is clearly versioned, and no new feature changes the meaning of P0 statuses.
- **Failure conditions:** Scope expansion or contract regression.
- **Git checkpoint:** `feat: add approved P1 enhancement`.
- **Relative effort:** Small to large depending on choice; may be skipped.

## 4. Release gates

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

## 5. Time protection

Reserve at least one implementation slice for integration and security fixes, one for clean-build verification, and one for documentation/demo review. If time becomes constrained, remove M6/M7 features before reducing P0 safety or evidence quality.
