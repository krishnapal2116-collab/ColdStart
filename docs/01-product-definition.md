# ColdStart Product Definition

**Status:** Proposed for approval
**Version:** 0.1
**Date:** 2026-10-15
**Owner:** ColdStart project owner
**Implementation status:** Not started

## 1. Problem statement

Software frequently works on its author's computer but fails when another person receives it. The cause is often an unreproduced environment: an unpinned runtime, an undeclared dependency, a missing lockfile, a setup step known only to the author, a local file or service, or a build that was never tested from a clean environment.

Manual checking is inconsistent and often stops at “the file exists.” A README can mention a command that does not match the project configuration, and a Dockerfile can exist without ever having built successfully. Developers need evidence about what is present, what is missing, and what has actually been executed.

## 2. Product statement

ColdStart is a local-first reproducibility readiness scanner and verifier. It accepts a software project location, examines the project without executing it by default, identifies supported project ecosystems, checks for reproducibility evidence, and produces an evidence-based report. With explicit permission, it can run supported verification commands and attempt a clean Docker build in a controlled environment.

## 3. Outcomes

ColdStart is successful when a user can answer these questions before sharing a project:

- What kind of project is this?
- Which runtime and dependency versions are declared?
- Is there a usable setup path for another developer?
- Is a test command documented and supported by the project?
- Does the documentation agree with the files?
- Are local-only paths, undeclared files, or environment assumptions visible?
- What did ColdStart actually verify, and what could it not verify?
- What should the developer fix first?

## 4. Target users

| User | Primary need | First useful result |
| --- | --- | --- |
| Student | Learn what a shareable project needs | A friendly terminal report with explanations |
| Independent developer | Avoid “works on my machine” failures | A prioritized checklist and JSON report |
| Open-source maintainer | Check contributions before release | A repeatable CI-compatible policy result |
| Software reviewer or educator | Evaluate project readiness consistently | Evidence and reproducible findings |
| Development team | Enforce handoff and release standards | Baselines, policy failures, and execution receipts |

The initial product is optimized for independent developers and small teams while remaining usable by all listed audiences.

## 5. Product principles

1. **Safe before convenient.** Static inspection is the default; execution is an explicit capability.
2. **Evidence before opinion.** Every finding has evidence or a clear reason it could not be verified.
3. **Not verified is not passed.** Lack of evidence is represented honestly.
4. **Local-first privacy.** Project contents and reports stay local unless a future feature is explicitly approved.
5. **Actionable output.** Each important finding gives a concrete next step.
6. **Deterministic analysis.** The same project state and options should produce the same static findings.
7. **Progressive trust.** Riskier operations require more specific confirmation and stricter isolation.
8. **Portable by construction.** The tool itself must be reproducible and must not depend on the author's global environment.

## 6. Core user journeys

### 6.1 Safe scan

1. User supplies a project path.
2. ColdStart validates the path and displays the scan boundary.
3. ColdStart reads eligible files and parses supported metadata.
4. ColdStart identifies the project type and runs static checks.
5. ColdStart writes a terminal report and optionally a versioned JSON report.
6. User receives findings, evidence, suggested fixes, and explicit unknowns.

No project command, package installation, network call, or project modification occurs in this journey.

### 6.2 Authorized verification

1. ColdStart completes the safe scan.
2. It proposes exact test and build actions, including timeout, isolation, network policy, and possible side effects.
3. User explicitly approves selected actions.
4. ColdStart executes only approved actions through the execution broker.
5. It records command, environment policy, exit status, output limits, duration, and cleanup result.
6. The report distinguishes actual pass, actual failure, timeout, refusal, unavailable capability, and unverified state.

### 6.3 CI policy check

1. CI invokes ColdStart in non-interactive mode with a checked-in policy.
2. Static checks run without network access or project mutation.
3. The process returns a documented exit code based on policy violations.
4. JSON or SARIF-compatible output can be retained by the CI system in a later release.

## 7. Value proposition

ColdStart is worth using instead of manually opening a few files because it:

- applies the same checks consistently across projects;
- compares documentation with project configuration;
- detects local-only and undeclared assumptions that are easy to miss;
- cites evidence using relative paths and line locations where possible;
- separates passed, failed, skipped, and not-verified states;
- performs authorized clean-room verification rather than inferring success;
- produces both beginner-friendly output and automation-friendly data;
- supports a baseline/diff workflow so improvements are visible over time.

## 8. Scope boundaries

### In scope for the first implementation release

- Local project paths.
- Generic file and documentation inspection.
- Full static checks for Python and Node.js.
- Detection and safe “not verified” reporting for other recognizable ecosystems.
- Runtime, dependency, lockfile, setup, test, build, portability, and local-assumption checks.
- Terminal and versioned JSON reports.
- Explicitly authorized test verification where the required sandbox is available.
- Explicitly authorized Docker build attempts.
- A local policy file and CI-compatible exit status.

### Out of scope for the first implementation release

- Automatically changing the inspected project.
- Automatically installing missing dependencies on the host.
- Cloning remote repositories.
- Uploading project files, reports, or telemetry.
- A hosted dashboard or account system.
- Vulnerability scanning, license compliance, or malware classification.
- Guaranteeing that a project works on every operating system.
- Running arbitrary shell pipelines by default.
- A graphical desktop application.

These may be considered later, but they are not implicit commitments.

## 9. Definition of success

The first implementation is ready for a broader pilot when it can:

- scan a representative Python and Node.js fixture without executing project code;
- identify at least one concrete issue and cite its evidence;
- produce stable terminal and JSON results;
- refuse or safely classify unsafe and unsupported execution requests;
- run an approved supported test in the defined sandbox and report its actual result;
- attempt an approved Docker build and report its actual result;
- pass the security, contract, integration, and offline verification gates defined in the verification strategy.
