# ColdStart Project Charter

**Status:** Implementation and release-candidate documentation
**Version:** 1.0
**Planning date:** 2026-10-15
**Implementation status:** P0 static audit plus optional M6.1 verification, M7 explanations, and M8 comparison are implemented; clean Linux/Docker release evidence remains host-dependent

## 1. Executive summary

ColdStart is a local-first command-line application that audits a software repository for reproducibility risks. It helps a developer, student, maintainer, reviewer, or evaluator determine whether the repository contains enough declared information for another environment to recreate it.

ColdStart starts with deterministic, read-only inspection. It discovers the repository type, checks runtime and dependency evidence, compares setup and test documentation with project metadata where supported, identifies portability and local-environment risks, and reports evidence-backed remediation guidance. Optional execution-based verification is a separate capability: a user may explicitly approve a supported offline test or clean Docker build, and ColdStart records the actual result and limitations.

ColdStart is a diagnostic tool, not a universal guarantee. A clean static report means that the defined checks found no configured defect; it does not prove that the software works on every computer, operating system, service, or future dependency state.

## 2. Project identity

| Attribute | Decision |
| --- | --- |
| Project name | ColdStart |
| Process | Technical planning and implementation for an open-source competition-track tool |
| Product type | Local-first software-repository reproducibility auditor |
| Primary interface | Command-line application |
| Primary language | Python, subject to the architecture decision in `docs/11_ARCHITECTURE_DECISIONS.md` |
| Primary target | Python repositories |
| Initial development model | Local execution |
| Verification layer | Optional Docker-based reproducibility and verification layer |
| Operating principle | Evidence over assumptions |
| Normal operation | No generative AI API and no required network access |

## 3. Problem statement

Software often works on its developer's computer but fails when another developer, evaluator, CI system, or deployment environment tries to run it. Common causes include:

- incomplete dependency declarations;
- a missing lockfile where the package manager or project policy expects one;
- an undocumented or unpinned runtime requirement;
- incomplete setup instructions;
- missing configuration examples or undocumented environment variables;
- hard-coded developer-specific paths and undeclared local resources;
- unclear or untruthful test commands;
- a container configuration that does not build in a clean environment;
- tests that silently require network access;
- unsafe handling of repository files during verification;
- claims that a project is fully reproducible without sufficient evidence.

Developers need a quick, consistent, and trustworthy way to find these risks before sharing, submitting, deploying, or maintaining a project.

## 4. Vision and mission

**Vision:** Reproducible software handoffs become a normal, inspectable part of development rather than a last-minute “works on my machine” surprise.

**Mission:** Give developers a safe local tool that turns repository evidence into understandable findings and only reports execution success when a real, authorized check produced that evidence.

## 5. Target users

1. **Individual open-source maintainer:** wants a release or contribution to be runnable by others.
2. **Student submitting a project:** needs a clear checklist and beginner-readable fixes.
3. **Hackathon/buildathon participant:** needs a fast pre-submission assessment under a time constraint.
4. **Small engineering team:** wants a repeatable handoff check without adopting an enterprise compliance platform.
5. **Reviewer or evaluator:** needs to compare setup instructions and evidence consistently.

The first release prioritizes individual developers and evaluators. It intentionally avoids enterprise policy management, hosted accounts, and organizational dashboards.

## 6. Core value proposition

ColdStart is more useful than manually opening a README and one manifest because it:

- applies a stable rule set consistently;
- determines whether a check applies before judging its result;
- links every finding to relative-path evidence or an explicit unknown reason;
- separates static evidence from commands that actually ran;
- offers precise remediation rather than a generic “fix your setup” warning;
- works without a generative AI service or remote upload;
- can later provide machine-readable output for CI without changing the core audit model.

## 7. Expected user outcomes

After a normal audit, a user should know:

- which repository type ColdStart recognized;
- which runtime and dependency declarations were found;
- whether a lockfile is applicable and present;
- whether setup and test instructions exist and agree with metadata;
- which local paths, files, environment variables, or resources are risks;
- which checks passed, failed, did not apply, were skipped, or could not be verified;
- what the highest-value remediation steps are;
- whether any test or build was actually executed.

## 8. Competitive differentiation

ColdStart differentiates itself through a narrow promise and disciplined evidence:

1. **Safe default:** inspecting a repository does not execute its scripts.
2. **Deterministic core:** rule-based results do not depend on an AI model or network service.
3. **Honest states:** `not_verified` is not silently converted into `passed`.
4. **Actionable evidence:** findings identify a rule, severity, evidence, and remediation.
5. **Clean handoff focus:** the tool checks whether another person can understand and recreate the project, not only whether a developer has a working local checkout.
6. **Small-team fit:** the first release is a CLI and local report, not a compliance platform.

## 9. Product boundaries

### In scope for the P0 MVP

- local repository path intake and boundary validation;
- deterministic discovery of Python project files and common project metadata;
- generic checks that remain useful for an unknown or partially supported repository;
- Python-focused runtime, dependency, documentation, configuration, path, and container-discovery checks;
- terminal and versioned JSON reports;
- stable check IDs, statuses, evidence, and remediation guidance;
- appropriate process exit codes;
- offline unit and integration test fixtures for ColdStart itself;
- clean-checkout documentation and reproducibility instructions for ColdStart.

### Implemented after the P0 MVP stabilized

- Docker-based clean build verification;
- offline test execution verification in a constrained environment;
- baseline comparison across audits;
- a `coldstart explain CHECK_ID` rule-explanation command;
- a plan-only verification preview before any P1 execution;

### Future optional work

- SARIF export if it can be implemented without weakening the core contract;
- built-in beginner, strict, and CI policy profiles;
- one additional well-supported repository ecosystem.

### Explicitly outside the first release

- generative-AI fixes or AI-dependent judgments;
- automatic modifications to the inspected repository;
- multi-agent orchestration;
- hosted accounts, remote repositories, or uploaded source;
- enterprise dashboards and distributed execution;
- a plugin marketplace or a requirement for permanent internet access;
- support for every programming language;
- security vulnerability scanning or a malware guarantee;
- a claim that a repository works on every possible computer.

## 10. Core assumptions and terminology decisions

- The P0 phrase **“save repositories”** is interpreted as **accept and scan repositories**. ColdStart does not create a persistent copy of a scanned repository in the MVP. If persistent snapshots are required, that is a separate feature decision.
- The phrase **“Zone report with documented sigma”** is interpreted as a **machine-readable JSON report with a documented schema**. The final report contract is defined in `docs/07_CLI_AND_REPORT_CONTRACTS.md`.
- “Offline test execution” means no network access during the test attempt. A test may still be `not_verified` if its dependencies are not available in the approved clean environment.
- Docker is an optional verification capability, not a prerequisite for the static audit.
- A check can be useful without proving a defect. Risk indicators are labeled as indicators, not certainty.

## 11. Recommended advanced improvements

These improvements make ColdStart more trustworthy and useful without turning the MVP into an enterprise platform. They are deliberately split by release priority.

### Adopt in P0

1. **Evidence-strength classification:** Every finding identifies whether its evidence is `direct`, `derived`, `indicator`, `absence`, or `unverified`. This replaces arbitrary confidence percentages and makes wording deterministic.
2. **Audit fingerprint:** Every normalized report contains a reproducibility fingerprint derived from the bounded repository evidence, policy, tool version, and check-catalog version. Run IDs and timestamps do not affect the fingerprint.
3. **ColdStart self-audit:** The release process audits the ColdStart repository with ColdStart itself. This is a release gate, not a claim that the current planning workspace has passed.
4. **No P0 staging workspace:** Static auditing reads the repository and writes only requested reports/diagnostics. Repository staging and temporary execution data belong to P1 verification.

### Add in P1, one at a time

1. **Baseline/diff comparison:** Compare fingerprints and findings to identify new, resolved, unchanged, or worsened risks.
2. **Rule explanation:** `coldstart explain CHECK_ID` shows the rule purpose, applicability, algorithm summary, evidence semantics, limitations, and remediation examples.
3. **Policy profiles:** `beginner`, `strict`, and `ci` profiles provide safe defaults without changing rule meaning or hiding findings.
4. **Plan-only verification:** `coldstart verify PATH --kind tests --plan` or `--kind docker-build --plan` previews the exact operation and constraints before approval.

### Deliberately not recommended for the MVP

ColdStart should not add AI-generated fixes, a primary readiness score, automatic modifications, remote ingestion, hosted dashboards, a plugin marketplace, or all-language support merely to appear advanced. Those features add complexity without improving the core evidence promise enough for the competition deadline.

## 12. Constraints

- The competition deadline is a hard constraint; a reliable small product is more valuable than broad but shallow ecosystem coverage.
- The inspected repository is untrusted input.
- Normal operation must work without an external AI API.
- Static inspection must not modify or execute the inspected repository.
- Dependencies, runtime, Dockerfile, lockfile, and test command for ColdStart itself must be documented and reproducible before release.
- No secrets may be committed, emitted in example reports, or copied into project documentation.

## 13. Success metrics

These are target acceptance measures, not current results:

1. **Coverage:** all P0 checks produce a defined result for the representative Python fixtures.
2. **Evidence:** 100% of findings have a stable rule ID and evidence or an explicit absence/unknown reason.
3. **Safety:** 0 project commands run during a default static audit in the security test suite.
4. **Determinism:** repeated audits of an unchanged fixture produce equivalent normalized findings.
5. **Usability:** a reviewer can locate the first recommended fix from the terminal report without opening source code.
6. **Reproducibility:** a clean Linux checkout can set up ColdStart using only repository-documented instructions.
7. **Truthfulness:** no release test permits an execution-based `passed` result without an observed successful exit and cleanup.
8. **Performance target:** a typical Python repository of up to 10,000 bounded files completes the static audit within 30 seconds on the reference development machine, excluding Docker or test execution.

## 14. Buildathon positioning

ColdStart demonstrates the same reproducibility discipline that it recommends: pinned runtime, locked dependencies, a Docker build path, an offline test command, clean-checkout instructions, and evidence from actual verification. The demonstration must show a deliberate defect and a truthful before/after assessment rather than a simulated successful run.

## 15. Product risks

| Risk | Consequence | Response |
| --- | --- | --- |
| Scope expands to every language | Unfinished adapters and weak evidence | Keep Python first-class; defer others until P0 is stable |
| Static patterns produce false positives | Users stop trusting findings | Use applicability, evidence, indicator wording, and fixture tests |
| Execution security dominates the schedule | P0 static auditor is delayed | Make Docker/test verification P1 and keep a useful no-Docker path |
| A score hides unknowns | False confidence | Keep findings authoritative; make scoring optional and non-authoritative |
| Buildathon time is spent on platform features | Core workflow is incomplete | Defer hosted, AI, marketplace, and enterprise features |
| Users assume “pass” means universal reproducibility | Product overclaims | Use explicit limitations in reports, docs, and demo |
