# ColdStart Scope and Requirements

**Status:** Proposed for approval
**Version:** 0.1
**Source:** Product definition and owner descriptions

## 1. Requirement conventions

- `MUST` is required for the first implementation release.
- `SHOULD` is strongly recommended but may be deferred with a recorded decision.
- `MAY` is optional and must not weaken a `MUST` requirement.
- A requirement is not satisfied by the presence of a file or command alone; where execution is relevant, the result must be recorded.

## 2. Functional requirements

### Project intake and boundaries

| ID | Requirement | Priority |
| --- | --- | --- |
| CS-F-001 | ColdStart MUST accept a local project directory as its primary input. | Must |
| CS-F-002 | ColdStart MUST reject a missing, unreadable, or non-directory input with an actionable error. | Must |
| CS-F-003 | ColdStart MUST define and display the scan boundary before reading project files. | Must |
| CS-F-004 | ColdStart MUST NOT follow symlinks outside the scan boundary by default. | Must |
| CS-F-005 | ColdStart MUST bound file count, file size, total bytes, and scan duration. | Must |
| CS-F-006 | ColdStart SHOULD support an explicit configuration for additional scan exclusions. | Should |

### Project identification

| ID | Requirement | Priority |
| --- | --- | --- |
| CS-F-010 | ColdStart MUST identify one or more project ecosystems using file evidence. | Must |
| CS-F-011 | ColdStart MUST distinguish a high-confidence identification from a heuristic detection. | Must |
| CS-F-012 | ColdStart MUST report mixed or ambiguous project types rather than choosing silently. | Must |
| CS-F-013 | The first full adapters MUST cover Python and Node.js. | Must |
| CS-F-014 | Generic checks MUST remain available when no full adapter exists. | Must |
| CS-F-015 | Go, Rust, Java, and other future ecosystems MAY be detected before full adapter support exists, but their unsupported checks MUST be `not_verified`, never `passed`. | Should |

### Static reproducibility checks

| ID | Requirement | Priority |
| --- | --- | --- |
| CS-F-020 | ColdStart MUST check for a declared runtime and identify whether the version is pinned, ranged, inferred, or absent. | Must |
| CS-F-021 | ColdStart MUST check dependency declarations and report the relevant files. | Must |
| CS-F-022 | ColdStart MUST check for a dependency lockfile where the ecosystem supports one. | Must |
| CS-F-023 | ColdStart MUST inspect setup documentation, with README as the minimum supported entry point. | Must |
| CS-F-024 | ColdStart MUST check whether a test command is documented or declared in project metadata. | Must |
| CS-F-025 | ColdStart MUST check whether build instructions or build configuration are present when the project has a build step. | Must |
| CS-F-026 | ColdStart SHOULD compare documented commands with detected project scripts and entry points. | Should |
| CS-F-027 | ColdStart SHOULD detect common absolute paths, undeclared environment variables, ignored-but-referenced files, and local service assumptions. | Should |
| CS-F-028 | Static checks MUST NOT claim that tests or builds pass without executing them. | Must |

### Reporting and recommendations

| ID | Requirement | Priority |
| --- | --- | --- |
| CS-F-030 | ColdStart MUST produce a readable terminal report. | Must |
| CS-F-031 | ColdStart MUST produce a versioned JSON report when requested. | Must |
| CS-F-032 | Each check MUST have a stable identifier, status, severity, summary, and evidence or a reason for missing evidence. | Must |
| CS-F-033 | Findings MUST distinguish `passed`, `failed`, `not_verified`, `skipped`, and `error`. | Must |
| CS-F-034 | Findings MUST include a practical suggested fix when a fix is reasonably inferable. | Must |
| CS-F-035 | Evidence paths MUST be project-relative by default. | Must |
| CS-F-036 | Reports MUST omit secret values and avoid exposing host usernames and absolute paths by default. | Must |
| CS-F-037 | ColdStart SHOULD support an optional non-authoritative readiness score. | Should |
| CS-F-038 | ColdStart SHOULD support a baseline/diff report in a later release. | Should |

### Authorized execution

| ID | Requirement | Priority |
| --- | --- | --- |
| CS-F-040 | ColdStart MUST be read-only and non-executing by default. | Must |
| CS-F-041 | ColdStart MUST show the exact proposed execution plan before requesting permission. | Must |
| CS-F-042 | ColdStart MUST obtain explicit user approval for each execution class: project tests and Docker build. | Must |
| CS-F-043 | ColdStart MUST execute only commands selected by the user and accepted by the safety policy. | Must |
| CS-F-044 | The first implementation MUST prefer a Docker-backed sandbox for project test execution. | Must |
| CS-F-045 | Host execution MUST NOT be an automatic fallback when Docker is unavailable. | Must |
| CS-F-046 | ColdStart MUST apply time, output, process, and resource limits to authorized execution. | Must |
| CS-F-047 | ColdStart MUST report exit status, timeout, refusal, unavailable capability, cleanup result, and captured output status. | Must |
| CS-F-048 | Network access MUST be disabled by default and separately approved when technically required. | Must |
| CS-F-049 | ColdStart MUST attempt a clean Docker build only after explicit approval. | Must |

### Automation and packaging

| ID | Requirement | Priority |
| --- | --- | --- |
| CS-F-050 | ColdStart MUST provide a documented non-interactive mode for CI static checks. | Must |
| CS-F-051 | The implementation repository MUST contain a pinned runtime declaration. | Must |
| CS-F-052 | The implementation repository MUST contain a dependency lockfile. | Must |
| CS-F-053 | The implementation repository MUST contain a Dockerfile able to build and run ColdStart. | Must |
| CS-F-054 | The implementation repository MUST provide one offline test command, standardized as `make test`. | Must |
| CS-F-055 | The implementation README MUST document exact setup, run, test, and deploy steps. | Must |

## 3. Non-functional requirements

| ID | Requirement | Acceptance measure |
| --- | --- | --- |
| CS-N-001 | Safety | No project execution, dependency installation, network call, or project mutation during a default scan. |
| CS-N-002 | Privacy | No telemetry or upload; default reports contain relative paths and redacted evidence. |
| CS-N-003 | Determinism | Static findings are stable for the same input snapshot, tool version, and options. |
| CS-N-004 | Portability | Supported CLI workflows work on Windows, Linux, and macOS subject to documented Docker availability. |
| CS-N-005 | Recoverability | A timeout or failed command does not leave a running child process or untracked temporary resource. |
| CS-N-006 | Usability | A new developer can understand the next fix from the terminal report without reading internal documentation. |
| CS-N-007 | Performance | A typical project scan completes within 30 seconds on a modern developer laptop, excluding authorized execution. |
| CS-N-008 | Resource safety | Default limits prevent unbounded file traversal, output capture, process count, and disk use. |
| CS-N-009 | Maintainability | Ecosystem-specific logic is isolated behind adapters and does not require changes to the core report contract. |
| CS-N-010 | Auditability | Every result identifies tool version, schema version, options, scan boundary, and execution authorization state. |

## 4. Initial support matrix

| Ecosystem | Detection | Runtime | Dependencies/lockfile | Docs/test consistency | Authorized verification |
| --- | --- | --- | --- | --- | --- |
| Python | Full | Full | Full for `pyproject.toml`, requirements files, and common lockfiles | Full | Docker-backed where supported |
| Node.js | Full | Full | Full for `package.json` and common lockfiles | Full | Docker-backed where supported |
| Go | Detection | Not verified until adapter | Not verified until adapter | Generic only | Not verified |
| Rust | Detection | Not verified until adapter | Not verified until adapter | Generic only | Not verified |
| Java | Detection | Not verified until adapter | Not verified until adapter | Generic only | Not verified |
| Unknown/mixed | Evidence-based | Not verified | Generic only | Generic only | Not verified |

## 5. Status and severity semantics

### Status

- `passed`: The defined evidence supports the check.
- `failed`: Evidence shows a reproducibility or policy problem.
- `not_verified`: ColdStart could not establish the result without unsupported capability, missing evidence, or missing authorization.
- `skipped`: The check was intentionally excluded by policy or user choice.
- `error`: ColdStart itself could not complete the check reliably.

### Severity

- `info`: Useful context; no action required.
- `warning`: A meaningful risk or incomplete practice.
- `error`: A likely reproducibility failure or policy violation.
- `blocking`: Prevents the requested verification or makes the project non-shareable under the selected policy.

## 6. Release gates

The first implementation release cannot be declared complete until all `Must` requirements have an implementation or a formally approved deferral. A deferral must name the affected requirement, explain why it is safe, and add a replacement verification or future milestone.
