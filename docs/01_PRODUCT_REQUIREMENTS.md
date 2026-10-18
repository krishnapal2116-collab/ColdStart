# ColdStart Product Requirements

**Status:** P0 approved; M6 verification and M7 offline rule-explanation slices implemented, target execution gates remain open
**Version:** 0.3
**Requirement language:** `MUST` is release-blocking; `SHOULD` is strongly preferred; `MAY` is optional. All requirements below have a priority and a testable completion definition.

## 1. Personas

| Persona | Need | Risk if unsupported |
| --- | --- | --- |
| Maintainer | Catch missing setup evidence before release | Contributors cannot reproduce the project |
| Student | Understand what another computer needs | Submission fails for evaluators |
| Buildathon participant | Get a fast, defensible pre-submission report | Time is lost debugging environment differences |
| Small team | Standardize handoff review | Knowledge remains trapped in one workstation |
| Reviewer/evaluator | Check claims against repository evidence | Reviews become subjective or overly manual |

## 2. User stories

- As a maintainer, I want to audit a repository without running it so that a suspicious project cannot execute merely because its metadata contains scripts.
- As a student, I want each finding to explain the evidence and fix in plain language so that I can repair my setup.
- As a reviewer, I want a JSON report with stable check IDs so that I can retain or compare results.
- As a small team, I want a process exit code and deterministic output so that the audit can run in CI later.
- As an authorized developer, I want a proposed execution plan before a Docker build or offline test so that I understand the risk and the limitation.

## 3. Normal workflow

1. User supplies a local repository path.
2. ColdStart validates the path and establishes a boundary.
3. ColdStart discovers supported project files and candidate ecosystem metadata.
4. ColdStart determines which checks apply.
5. ColdStart runs deterministic static checks without project execution.
6. ColdStart emits terminal and optionally JSON results.
7. In a P1 verification flow, the user reviews and explicitly authorizes a proposed test or Docker action.
8. ColdStart runs the approved action under documented constraints and records the actual result.

## 4. Error workflows

- Invalid path: return a usage/configuration error, identify the invalid input, and run no audit.
- Unreadable file: continue independent checks, record incomplete evidence, and never claim complete coverage.
- Unsupported repository type: run generic checks, mark ecosystem-specific checks `not_applicable` or `not_verified`, and explain the limitation.
- Malformed metadata: isolate the parser error to the relevant finding and continue safe checks.
- User denies P1 execution: record `skipped` or `not_verified` according to the contract; never report a pass.
- Docker unavailable: retain the static report and mark Docker verification `not_verified`; never fall back to host execution automatically.
- Resource limit reached: stop safely, report partial coverage, and return the documented incomplete-result exit code.
- Output destination unavailable: retain terminal output when safe and return an output error when the requested machine report could not be written.

## 5. Functional requirements

| ID | Priority | Requirement | Testable definition of completion |
| --- | --- | --- | --- |
| FR-001 | P0 | Accept a local repository path without persisting a repository copy. | A valid directory reaches the audit pipeline; no persistent snapshot is created. |
| FR-002 | P0 | Validate the path and establish a repository boundary. | Missing, non-directory, unreadable, and boundary-escape inputs receive documented errors or findings. |
| FR-003 | P0 | Discover relevant files and project metadata deterministically. | The same fixture yields the same sorted inventory and discovery evidence. |
| FR-004 | P0 | Detect supported project types and determine check applicability. | Python fixtures produce a Python candidate; unknown/mixed fixtures do not silently select one type. |
| FR-005 | P0 | Run the P0 static check catalog without executing repository code. | Instrumented fixtures show no project process during `coldstart audit`. |
| FR-006 | P0 | Give every finding a stable check ID, severity, title, and status. | Contract tests reject findings missing required fields or using unknown IDs/statuses. |
| FR-007 | P0 | Distinguish `passed`, `failed`, `not_applicable`, `skipped`, `not_verified`, and `error`. | Status fixtures demonstrate each state and no non-pass state is counted as passed. |
| FR-008 | P0 | Attach evidence and actionable remediation to findings when applicable. | Defective fixtures identify a relative path, safe detail, and concrete next step. |
| FR-009 | P0 | Produce a human-readable terminal report. | A CLI test checks ordered summary, findings, evidence, remediation, limitations, and next step. |
| FR-010 | P0 | Produce a versioned machine-readable JSON report. | A report validates against the documented schema and matches terminal statuses. |
| FR-011 | P0 | Return documented process exit codes. | CLI tests cover success, policy failure, invalid input, incomplete audit, and internal error. |
| FR-012 | P0 | Support an optional local configuration file for policy and bounded limits. | Valid configuration changes only documented policy behavior; invalid configuration fails closed. |
| FR-013 | P0 | Perform normal static auditing without an AI API, network access, or project dependencies. | Offline tests run with network disabled and no model/API configuration. |
| FR-014 | P0 | Keep reports and static processing read-only with respect to the inspected repository. | A before/after manifest is unchanged after static audits, including failures. |
| FR-015 | P0 | Keep static audits staging-free; any P1 temporary material must be cleaned up on success, failure, and cancellation. | P0 filesystem observers show no staging workspace; P1 cleanup tests verify no owned temporary directory remains or failure is reported. |
| FR-016 | P0 | Provide a complete Python repository adapter for the defined P0 checks. | Python fixtures cover applicable runtime, dependency, docs, configuration, path, and container checks. |
| FR-017 | P0 | Document ColdStart setup, test, and clean-checkout reproduction requirements. | Documentation review finds exact future commands and no undocumented required global dependency. |
| FR-018 | P1 | Propose and run an explicitly authorized offline test verification. | The implemented runner emits a Docker-isolated plan, requires explicit authorization, and records a bounded receipt for a safe direct Python test; missing Docker or image capability remains `not_verified`, never a pass. |
| FR-019 | P1 | Propose and attempt an explicitly authorized clean Docker build. | The implemented runner uses fixed structured Docker argv and records actual exit status or a truthful unavailable receipt; Docker-enabled build evidence remains pending. |
| FR-020 | P1 | Export SARIF when it can be done without contract or safety compromise. | A valid SARIF fixture is produced or the feature remains clearly unavailable. |
| FR-021 | P1 | Compare a new audit with a user-supplied baseline. | Added, removed, and changed findings are deterministic in a dedicated test. |
| FR-022 | P1 | Add one additional well-supported repository type after Python is stable. | The additional adapter has its own catalog, fixtures, contract, and documentation. |
| FR-023 | P2 | Generate AI-authored fixes or depend on AI judgments. | Deferred: no implementation or acceptance test is permitted in the first release. |
| FR-024 | P2 | Modify the inspected repository automatically. | Deferred: all remediation is advisory and no write path exists in the MVP. |
| FR-025 | P2 | Ingest remote repositories or operate as a hosted account service. | Deferred: only a local path is accepted in the first release. |
| FR-026 | P2 | Orchestrate multiple agents, distributed execution, or a plugin marketplace. | Deferred: no runtime or permanent-network framework is added for the MVP. |
| FR-027 | P2 | Claim universal reproducibility or compatibility with every language. | Prohibited: reports and docs must state their scope and limitations. |
| FR-028 | P0 | Classify finding evidence deterministically as `direct`, `derived`, `indicator`, `absence`, or `unverified`. | Contract and fixture tests reject missing/unknown evidence-strength values and confirm no percentage confidence is emitted. |
| FR-029 | P0 | Include a deterministic audit fingerprint in every normalized report. | Equivalent bounded inputs, tool version, policy, and catalog produce the same fingerprint; timestamps and run IDs do not affect it. |
| FR-030 | P0 | ColdStart MUST audit its own release-candidate repository before release. | Release evidence contains an actual self-audit report and a reviewed result. |
| FR-031 | P1 | Compare a current report with a baseline using findings and audit fingerprints. | A comparison identifies added, resolved, unchanged, and worsened findings deterministically. |
| FR-032 | P1 | Explain a stable check ID without using an AI service. | `coldstart explain CHECK_ID` shows purpose, applicability, algorithm, evidence, limitations, and remediation. |
| FR-033 | P1 | Provide beginner, strict, and CI policy profiles without changing rule semantics. | Profile tests show only documented policy/presentation differences and preserve all findings. |
| FR-034 | P1 | Preview an execution plan without executing it. | `verify --plan` displays command, working directory, network, limits, and side effects while producing no child process; the M6 CLI test covers this. |

## 6. Non-functional requirements

| ID | Priority | Requirement | Testable definition of completion |
| --- | --- | --- | --- |
| NFR-001 | P0 | Determinism: equal repository state, configuration, tool version, and environment class produce equivalent findings. | Repeated fixture audits compare normalized JSON after excluding run IDs/timestamps. |
| NFR-002 | P0 | Safety: default static auditing cannot execute project commands or mutate the inspected repository. | Security tests instrument subprocess and filesystem behavior; no project execution occurs. |
| NFR-003 | P0 | Privacy: default operation keeps repository data local and redacts secrets from reports. | Network-disabled tests and redaction fixtures show no upload or secret value in output. |
| NFR-004 | P0 | Offline operation: the P0 audit and its tests do not require a network service. | `make test` and representative audits run with network disabled after setup. |
| NFR-005 | P0 | Reliability: isolated parser/file failures yield partial, truthful results rather than false passes. | Malformed and unreadable fixtures produce bounded error/`not_verified` findings and continue. |
| NFR-006 | P0 | Resource safety: file, byte, depth, time, output, and temporary-storage limits are bounded. | Limit fixtures terminate within configured budgets and record incomplete coverage. |
| NFR-007 | P0 | Portability: the static CLI supports the documented Python 3.12 environments on Linux, Windows, and macOS where filesystem behavior permits. | Cross-platform path/line-ending tests pass in the supported matrix. |
| NFR-008 | P0 | CLI accessibility: terminal output is understandable without color, is safe for screen readers, and keeps meaning in plain text. | No-color/redirected-output snapshots retain headings, statuses, evidence, and remediation. |
| NFR-009 | P0 | Compatibility: report schema and stable check IDs are versioned and changes are documented. | Contract tests validate schema version and compatibility rules. |
| NFR-010 | P0 | Maintainability: audit rules are isolated from CLI rendering and execution. | Module dependency tests and code review confirm the stated dependency direction. |
| NFR-011 | P0 | ColdStart itself is reproducible from a clean Linux checkout. | Pinned runtime, lockfile, Dockerfile, and exact README commands are exercised before release. |
| NFR-012 | P0 | Auditability: results record tool/schema versions, options, applicability, and execution authorization state. | Report contract tests require provenance and limitation fields. |
| NFR-013 | P1 | Authorized execution is constrained by working directory, argv, timeout, output, process, and network policy. | M6.1 covers Docker structured argv, read-only mount, `network=none`, fixed resource limits, timeout termination, bounded output, source-manifest comparison, no host fallback, and denial; Docker availability remains target-environment evidence. |
| NFR-014 | P1 | Docker verification is optional and never a hidden prerequisite for static usefulness. | M6 returns a Docker-unavailable receipt while the static report remains complete; Docker-enabled integration remains pending. |
| NFR-015 | P0 | Evidence-strength wording is deterministic and does not imply unsupported confidence. | Snapshot tests verify the same evidence class and phrasing for equivalent findings. |

## 7. Acceptance language

“Implemented” means the requirement has code, a focused test, documentation, and a recorded result from the appropriate verification command. A specification, fixture, or intended design alone is not implementation evidence. “Tested” means the command actually ran and its output was recorded; it does not mean a test plan exists.
