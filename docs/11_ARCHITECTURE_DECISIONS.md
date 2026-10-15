# ColdStart Architecture Decisions

**Status:** Proposed for approval
**Version:** 0.2

These records make the technical direction explicit. They are proposed decisions until the owner approves the documentation pack. Changes after implementation require a new record and affected test/documentation updates.

## ADR-001 — CLI-first product

**Context:** The first users are individual developers, students, maintainers, and reviewers who need a fast local check.
**Options:** CLI; desktop GUI; web application.
**Chosen:** CLI-first local application.
**Rationale:** It is scriptable, transparent, easy to use in CI later, and avoids authentication, hosting, and browser permissions.
**Consequences:** Terminal accessibility and JSON contracts matter; a GUI is deferred.
**Rejected alternatives:** A web app would require source upload or a local server and adds privacy/deployment complexity.
**Reconsider if:** User testing shows terminal output cannot serve the primary audience without a thin local UI.

## ADR-002 — Python 3.12 implementation

**Context:** Python is the primary target repository language and the project owner proposed Python for ColdStart.
**Options:** Python 3.12; Rust; Node.js.
**Chosen:** Python 3.12.8, pinned for implementation.
**Rationale:** It is accessible to the target users, supports the target ecosystem, and provides standard-library parsers suitable for a small deterministic core.
**Consequences:** ColdStart must solve its own runtime reproducibility with a pinned runtime, lockfiles, and Dockerfile.
**Rejected alternatives:** Rust could provide a single binary but increases implementation complexity; Node.js would add a second primary runtime.
**Reconsider if:** Python packaging cannot meet the clean Linux rebuild gate or a competition requirement requires a standalone binary.

## ADR-003 — Deterministic rules over AI judgment

**Context:** Audit results must be explainable, reproducible, and usable without a generative AI API.
**Options:** AI-first classification; deterministic rule engine; hybrid AI suggestions.
**Chosen:** Deterministic, rule-based P0 engine.
**Rationale:** Equal inputs should produce equivalent findings and evidence; rules are testable offline.
**Consequences:** Coverage is narrower and some dynamic behavior becomes `not_verified`; P2 AI fixes are deferred.
**Rejected alternatives:** AI judgments could be variable, require service/privacy controls, and make evidence harder to audit.
**Reconsider if:** A later optional explanation feature can be isolated from authoritative findings and does not require source upload or change statuses.

## ADR-004 — Static inspection separated from execution

**Context:** Repository metadata can contain commands that execute arbitrary code.
**Options:** Execute documented tests automatically; static-only product; separate explicit verification phase.
**Chosen:** P0 static-only by default; P1 explicit verification command.
**Rationale:** It preserves a safe first action and makes actual execution visible.
**Consequences:** Docker/test verification is slower and may be unavailable; reports must distinguish evidence classes.
**Rejected alternatives:** Automatic execution violates the safety promise.
**Reconsider if:** A new sandbox is proven and still requires explicit user/policy authorization.

## ADR-005 — Read-only default

**Context:** Auditing must not change the repository or silently generate project files.
**Options:** Auto-fix; write caches into the repository; read-only with private temporary data.
**Chosen:** Read-only repository, explicit output path, private temporary directory only.
**Rationale:** It protects source integrity and makes before/after evidence meaningful.
**Consequences:** Remediation is advisory; users apply fixes themselves.
**Rejected alternatives:** Automatic modification is P2 and could destroy intent or hide the original defect.
**Reconsider if:** A future opt-in patch mode gets a separate transaction, diff, and approval design.

## ADR-006 — Terminal plus versioned JSON

**Context:** Beginners need readable output; reviewers and CI need structured data.
**Options:** Terminal only; JSON only; both with a versioned schema.
**Chosen:** Both, with JSON schema `1.0` and stable check IDs.
**Rationale:** One normalized model can serve both audiences and future SARIF/baseline features.
**Consequences:** Schema compatibility becomes a release responsibility.
**Rejected alternatives:** Terminal-only output is difficult to automate; unversioned JSON breaks consumers silently.
**Reconsider if:** Actual users demonstrate that a different standard format is more useful without losing the core fields.

## ADR-007 — Minimal dependency strategy

**Context:** ColdStart must work offline and be reproducible.
**Options:** Large framework; standard-library core with small pinned dev tools; plugin ecosystem.
**Chosen:** Standard-library-first P0 with pinned `pytest`/`ruff` development tools and hash-checked lockfiles.
**Rationale:** Fewer supply-chain and installation failure modes, simpler review, and enough parsing for the P0 catalog.
**Consequences:** Some formats and advanced parsing remain unsupported; unknowns are explicit.
**Rejected alternatives:** Framework/plugin layers add complexity before an MVP need exists.
**Reconsider if:** A measured P0 gap cannot be solved safely with the current approach.

## ADR-008 — Local-first privacy

**Context:** Repositories may be private and contain secrets.
**Options:** Hosted analysis; opt-out telemetry; local-only processing.
**Chosen:** Local-only, no telemetry, no required network.
**Rationale:** It matches user trust, competition constraints, and offline determinism.
**Consequences:** No hosted dashboard or remote aggregate metrics in the first release.
**Rejected alternatives:** Uploading source would materially increase privacy and authorization requirements.
**Reconsider if:** A separately approved service has explicit consent, redaction, access control, and threat modeling.

## ADR-009 — Docker's role

**Context:** Clean execution can strengthen evidence but Docker may be unavailable and its daemon is privileged.
**Options:** Require Docker for all audits; never support Docker; optional P1 Docker verification.
**Chosen:** Optional P1 verification; P0 remains useful without Docker.
**Rationale:** It balances safety, usefulness, and competition feasibility.
**Consequences:** A Docker-unavailable result is `not_verified`, not failure or pass; Docker limitations are disclosed.
**Rejected alternatives:** Making Docker a P0 prerequisite would exclude users and obscure static findings.
**Reconsider if:** P0 user research shows Docker is universally available for the target workflow.

## ADR-010 — Adding checks later

**Context:** New checks must not become an unreviewed code-execution or plugin marketplace.
**Options:** General plugin marketplace; dynamic discovery; reviewed registry modules.
**Chosen:** Reviewed in-repository check modules with stable IDs, fixtures, and traceability.
**Rationale:** It is sufficient for the bounded MVP and keeps the attack surface small.
**Consequences:** Adding ecosystems requires a release change and test fixtures.
**Rejected alternatives:** Marketplace/distributed plugins are P2 and need a separate trust model.
**Reconsider if:** Multiple maintained adapters create a measured, documented need for a safe extension boundary.

## Approval note

The highest-impact choices requiring owner confirmation are Python 3.12.8, P0 Python-only first-class support, local-only deterministic operation, no automatic execution, and P1 Docker verification.
