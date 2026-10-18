# ColdStart MVP Scope and Acceptance

**Status:** P0 approved; M6 verification, M7 explanations, and M8 baseline comparison are implemented with target-environment limits
**Version:** 0.3
**MVP principle:** Ship a reliable Python-focused static auditor before adding execution or ecosystem breadth.

## 1. Priority levels

### P0 — mandatory first release

P0 is the competition-ready MVP:

- local repository intake, path validation, and boundary enforcement;
- deterministic repository discovery and Python project detection;
- applicability-aware static checks from `docs/06_CHECK_CATALOG.md`;
- stable findings with evidence, remediation, and explicit status semantics;
- deterministic evidence-strength classification (`direct`, `derived`, `indicator`, `absence`, `unverified`);
- a deterministic audit fingerprint in every normalized report;
- human-readable terminal report;
- versioned JSON report with a documented schema;
- actionable exit codes;
- optional local configuration with fail-closed parsing;
- no AI API and no network requirement during normal audit;
- no P0 staging workspace; cleanup controls for any future P1 temporary material;
- unit, integration, CLI, security, malformed-input, and deterministic-output tests;
- a clean example repository and a deliberately defective Python repository;
- a release self-audit of the ColdStart repository using ColdStart;
- pinned ColdStart setup documentation, lockfile, Dockerfile, and offline test command as release gates.

P0 does not execute the inspected repository and does not create a repository staging workspace.

### P1 — only after P0 is stable

- Docker-based clean build verification;
- offline test execution verification in a controlled environment;
- explicit permission plan and execution receipt;
- plan-only verification preview before execution;
- SARIF export if useful and feasible;
- baseline comparison;
- `coldstart explain CHECK_ID`;
- beginner, strict, and CI policy profiles;
- one additional well-supported repository type.

P1 must not change P0 safety defaults or the finding contract.

### P2 — explicitly deferred

- AI-generated fixes or AI-dependent judgments;
- automatic repository modification;
- remote repository ingestion or hosted accounts;
- multi-agent, distributed, or complex execution orchestration;
- enterprise dashboard/compliance platform;
- complete language ecosystem coverage;
- plugin marketplace requiring permanent internet access;
- a universal reproducibility guarantee.

## 2. MVP user journeys

### Journey A — maintainer static audit

```text
coldstart audit ./project --format terminal
```

The user sees the repository type, applicable checks, findings, evidence, remediation, limitations, and exit status. No project script, package manager install, test, or build runs.

### Journey B — machine-readable review

```text
coldstart audit ./project --format json --output ../reports/project.json
```

The report is versioned, deterministic apart from run metadata, safe to parse, and suitable for a later CI wrapper.

### Journey C — strict review

```text
coldstart audit ./project --config .coldstart.toml --strict
```

The configured policy decides whether failed or `not_verified` checks block the process. `skipped` and `not_applicable` checks remain visible and are not counted as passes.

### Journey D — P1 verification (not required for P0)

```text
coldstart verify ./project --kind tests --offline
coldstart verify ./project --kind docker-build
coldstart verify ./project --kind tests --authorize
```

These commands first print a plan. `--plan` previews without a child process, and `--authorize` is required before a supported test or Docker process starts. An authorized `--offline` test uses Docker network isolation, a read-only repository mount, fixed resource limits, and no host fallback; if Docker is unavailable, the static audit remains useful and the verification status is `not_verified`.

## 3. Required command set

| Command | Release | Purpose |
| --- | --- | --- |
| `coldstart audit PATH` | P0 | Perform the safe deterministic audit |
| `coldstart version` | P0 | Print tool, report schema, and check-catalog versions |
| `coldstart --help` | P0 | Explain command and option usage |
| `coldstart explain CHECK_ID` | P1 | Explain a rule without auditing a repository |
| `coldstart verify PATH --kind tests` | P1 | Authorized offline test verification |
| `coldstart verify PATH --kind docker-build` | P1 | Authorized clean Docker build attempt |
| `coldstart verify PATH --kind tests --plan` | P1 | Preview a test verification without executing it |
| `coldstart compare CURRENT BASELINE` | P1 | Compare findings and fingerprints |

The names are the proposed external contract. Any implementation change requires an explicit decision-log update before code changes.

## 4. Required reports

### Terminal report

Must contain, in stable order:

1. ColdStart version and report schema version.
2. Repository label and detected project type.
3. Overall policy result and counts by status.
4. Findings ordered by severity and check ID.
5. Evidence and affected relative path.
6. Remediation guidance.
7. `not_applicable`, `skipped`, and `not_verified` limitations.
8. Execution section, explicitly saying “not requested” for P0.
9. Next action and process exit code.

### JSON report

Must conform to the contract in `docs/07_CLI_AND_REPORT_CONTRACTS.md` and the companion artifacts in `docs/contracts/`.

## 5. Core feature acceptance criteria

| Feature | Acceptance criterion |
| --- | --- |
| Path validation | Invalid, unreadable, non-directory, and boundary-escape inputs never begin a project audit and return the documented code. |
| Discovery | A clean Python fixture and defective Python fixture produce deterministic file/project evidence. |
| Applicability | Lockfile and runtime checks become `not_applicable` where the detected package manager/project policy does not require them; absence is not a universal failure. |
| Static checks | The default command cannot spawn project processes, install dependencies, contact the network, or modify the inspected tree. |
| Findings | Every finding contains a stable ID, status, severity, message, evidence or limitation, and remediation when applicable. |
| Evidence strength | Every finding carries one deterministic evidence-strength value; no arbitrary percentage confidence is emitted. |
| Audit fingerprint | Equivalent normalized repository evidence, tool version, catalog, and policy produce the same fingerprint. |
| Terminal report | A no-color redirected report remains understandable and does not expose terminal control sequences. |
| JSON report | A valid JSON report validates against the documented schema and agrees with terminal statuses/counts. |
| Exit code | The same normalized result and policy produce the documented code independent of renderer choice. |
| Configuration | Invalid policy fails closed; valid policy affects only documented thresholds/exclusions and records them. |
| Cleanup | Any temporary directory owned by ColdStart is removed or its cleanup failure is reported. |
| P0 workspace safety | A static P0 audit does not create a repository staging copy or execution workspace. |
| Reproducible ColdStart | A clean Linux checkout can follow the documented setup and run `make test` offline after dependencies are installed. |
| Self-audit | The release candidate can audit its own repository and the result is reviewed as release evidence. |

## 6. Negative acceptance criteria

The MVP is rejected if any of these occur:

- a README-listed script runs during `coldstart audit`;
- a shell string is executed through a shell by the P0 audit;
- a missing lockfile is reported as a defect when the detected project policy does not make one applicable;
- an unknown or skipped check is rendered as a pass or omitted from the report;
- a finding lacks evidence-strength classification or emits an invented confidence percentage;
- two equivalent normalized scans produce different audit fingerprints;
- a report claims tests/builds passed without an execution receipt;
- a finding quotes an unredacted token, password, private key, or environment value;
- a symlink or relative path lets static inspection escape the repository boundary;
- an internal parser exception causes a complete false-pass report;
- Docker availability is required for the static audit;
- a P0 static audit creates an execution staging workspace;
- the product documentation claims universal reproducibility.

## 7. Explicit exclusions

The MVP does not fix files, install project dependencies, run arbitrary host commands, clone remotes, upload source, call a generative model, scan every language, or provide an enterprise policy service.

## 8. Definition of Done

P0 is complete only when:

1. All P0 functional and non-functional requirements have implementation evidence or an approved deferral.
2. The clean and defective Python fixtures pass their expected acceptance tests.
3. The P0 check catalog is traceable to tests.
4. Evidence-strength and fingerprint tests pass.
5. `make test` runs offline from a clean ColdStart checkout.
6. ColdStart's Dockerfile builds and runs from a clean checkout.
7. Security, privacy, malformed-input, path-boundary, redaction, and deterministic-output tests pass.
8. Terminal and JSON reports agree.
9. ColdStart has audited its own release candidate repository.
10. The README explains setup, use, test, clean build, and current limitations.
11. The demo uses actual tool output, not simulated results.
12. Git contains a focused checkpoint for the release candidate.

## 9. Release-blocking defects

Any open defect involving command execution, path escape, secret leakage, false verification, nondeterministic core findings, unbounded resource use, broken report schema, unavailable offline test path, or undocumented required setup blocks release.

## 10. Final MVP acceptance checklist

- [ ] Python 3.12.8 runtime is pinned and documented.
- [ ] ColdStart dependency lockfile is committed.
- [ ] Dockerfile builds and runs ColdStart.
- [ ] `make test` is the single offline test command.
- [ ] `coldstart audit PATH` works on the clean fixture.
- [ ] `coldstart audit PATH` catches the deliberate defect.
- [ ] All findings cite evidence or an explicit limitation.
- [ ] Evidence strength is present and deterministic.
- [ ] Audit fingerprints are stable across equivalent runs.
- [ ] `not_applicable`, `skipped`, and `not_verified` statuses are distinct.
- [ ] JSON validates against the schema.
- [ ] No AI API or network is required for P0.
- [ ] The repository remains unchanged after a static audit.
- [ ] Static P0 auditing creates no staging workspace.
- [ ] ColdStart has self-audited the release candidate.
- [ ] The documentation quality gate is complete.
- [ ] The owner has approved the release candidate.
