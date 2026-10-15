# ColdStart Decision Log

**Status:** Proposed decisions awaiting owner approval
**Version:** 0.1

This log records design choices made to make the plan internally consistent. “Proposed” means the choice is recommended but may be changed by the owner before implementation. A change after implementation requires an ADR update and affected test/documentation changes.

## D-001 — Product form

**Decision:** Build ColdStart first as a local-first command-line application.

**Reason:** A terminal tool is useful for students and independent developers, easy to run in CI, and avoids introducing a GUI or hosted service before the core evidence model is proven.

**Alternatives considered:** Desktop GUI, hosted dashboard, editor extension.

**Status:** Proposed; included in the approval checklist.

## D-002 — Recommended implementation runtime

**Decision:** Use Python 3.12 as the implementation baseline, pinned in the repository.

**Reason:** Python is approachable for the intended audience, has strong text/config parsing support, and supports rapid adapter development. ColdStart itself will address its own reproducibility requirements with a lockfile and Dockerfile.

**Alternatives considered:** Rust for a single binary; Node.js for ecosystem familiarity.

**Status:** Proposed.

## D-003 — Initial ecosystem coverage

**Decision:** Provide full adapters for Python and Node.js first. Provide generic checks and honest `not_verified` results for other recognized ecosystems.

**Reason:** This keeps the first release manageable while leaving an adapter boundary for later coverage. It avoids false claims for ecosystems without complete rules.

**Alternatives considered:** Support five ecosystems partially; support only one ecosystem deeply.

**Status:** Proposed.

## D-004 — Execution safety

**Decision:** Static inspection is always the default. Project tests and Docker builds require separate explicit authorization. Docker-backed execution is preferred, and Docker absence does not trigger host execution automatically.

**Reason:** Project files and Dockerfiles are untrusted and may execute code or access resources. Separate approval makes risk visible.

**Alternatives considered:** Automatic execution when a command is found; direct host execution as a convenience fallback.

**Status:** Proposed and security-critical.

## D-005 — Network policy

**Decision:** Authorized execution starts with network disabled. Network-enabled verification, if implemented, is a separate approval decision.

**Reason:** Dependency downloads and build scripts can contact arbitrary endpoints. Network denial makes a clean, deterministic attempt safer and exposes undeclared network requirements.

**Alternatives considered:** Network enabled by default to maximize successful builds.

**Status:** Proposed.

## D-006 — Report format

**Decision:** Provide a readable terminal report and a versioned JSON report. This specification interprets the owner's phrase “Johnson report” as “JSON report.”

**Reason:** Terminal output helps beginners; JSON supports CI and future interfaces. A versioned contract prevents output changes from silently breaking consumers.

**Alternatives considered:** Terminal-only output; unversioned ad hoc JSON.

**Status:** Proposed; owner clarification welcome.

## D-007 — Result semantics

**Decision:** Use `passed`, `failed`, `not_verified`, `skipped`, and `error` statuses. `not_verified` is never converted to `passed`.

**Reason:** The product promise is evidence-based reporting. The distinction prevents false confidence when a capability, permission, or evidence source is missing.

**Alternatives considered:** A binary pass/fail result; treating missing evidence as a warning-only pass.

**Status:** Proposed.

## D-008 — Policy configuration

**Decision:** Use an optional local `.coldstart.toml` policy file, with fail-closed parsing and no secrets.

**Reason:** Local policy is portable, reviewable, and works offline. TOML is readable for the target audience and compatible with the recommended runtime.

**Alternatives considered:** Environment-only settings; remote policy service; YAML.

**Status:** Proposed.

## D-009 — Readiness score

**Decision:** Treat a 0–100 readiness score as optional, non-authoritative, and secondary to individual findings.

**Reason:** A score can show progress, but it can also hide important unknowns or create false precision. Findings and evidence remain the source of truth.

**Alternatives considered:** No score; score as the primary result.

**Status:** Proposed; score weights require owner approval if included in v1.

## D-010 — Buildathon reproducibility gates

**Decision:** The implemented ColdStart repository must include a pinned runtime, lockfile, Dockerfile, offline `make test`, and exact README setup/run/test/deploy instructions.

**Reason:** ColdStart must demonstrate the reproducibility behavior it checks and must rebuild on a clean Linux machine.

**Alternatives considered:** Rely on developer-local setup; provide an informal test command.

**Status:** Required by project constraints.

## 3. Open approval items

The owner needs to confirm:

1. The JSON interpretation of “Johnson report.”
2. The Python 3.12 baseline and packaging-tool choice after Phase 1 begins.
3. Whether the optional score belongs in the first release.
4. Whether any ecosystem besides Python and Node.js must be first-class before implementation.
5. Whether the proposed out-of-scope list omits a business-critical need.

Until these are approved or revised, no implementation source should be created.
