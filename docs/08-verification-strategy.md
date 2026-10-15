# ColdStart Verification Strategy

**Status:** Proposed for approval
**Version:** 0.1
**Current phase:** Documentation only; application checks do not exist yet

## 1. Verification principles

1. Test behavior at the boundary the user experiences, not only internal functions.
2. Keep static analysis tests offline and independent of the user's project dependencies.
3. Treat every fixture project as untrusted input.
4. Verify both positive evidence and honest unknown states.
5. Test that permission denial is safe, not merely that permission approval works.
6. Test the terminal and JSON reports as two views of the same normalized result.
7. Record actual commands and results; never replace a failing check with a no-op.

## 2. Required project checks after implementation approval

The implementation repository must provide one canonical offline command:

```text
make test
```

`make test` must run the complete local test suite without downloading dependencies or requiring a network service. It may call the project test runner internally, but contributors and reviewers must have one documented command.

The implementation README must also document exact commands for setup, normal use, test, package/build, Docker build, and deployment/distribution. A missing runtime or dependency is a setup failure, not permission to install globally.

## 3. Test pyramid

### 3.1 Unit tests

Cover pure logic including:

- path normalization and boundary enforcement;
- file inventory limits and exclusions;
- ecosystem detection and confidence;
- runtime and lockfile parsing;
- dependency/documentation consistency rules;
- command candidate parsing and unsafe syntax rejection;
- status/severity/policy evaluation;
- score calculation if enabled;
- redaction and terminal escaping;
- stable JSON serialization;
- exit-code selection.

Unit tests must use in-memory or small fixture inputs and must not run project code.

### 3.2 Contract tests

Cover:

- required report fields and enum values;
- top-level and finding invariants;
- summary counts matching findings;
- execution receipt rules;
- schema compatibility and additive-field behavior;
- terminal/JSON status agreement.

At least one valid report, one report with unknowns, one report with execution failure, and one report with an internal error must be checked against the contract.

### 3.3 Integration tests

Use checked-in fixture projects with known content and expected results. Integration tests must run offline and must not require the fixture's dependencies to be installed.

Required fixture families:

| Fixture | Expected coverage |
| --- | --- |
| Clean Python project | Pinned runtime, dependency declaration, lockfile, setup/test docs |
| Python missing runtime | `runtime` failure or warning and actionable fix |
| Python missing dependency declaration | Dependency failure with file evidence |
| Python README mismatch | Documentation consistency finding |
| Clean Node.js project | Runtime, scripts, dependency lockfile, documentation |
| Node.js conflicting lockfiles | Dependency consistency failure |
| Mixed project | Multiple ecosystem candidates and no silent selection |
| Unsupported Go/Rust/Java project | Generic findings plus `not_verified` adapter results |
| Absolute/local path project | Portability and local-assumption findings |
| Ignored-but-referenced file project | Missing-file/local-state finding |
| Large and binary-file project | Bounded inventory behavior |
| Malicious filename/content project | No command execution, safe rendering |
| Symlink escape project | External link not followed by default |
| Secret-bearing project | Values excluded from evidence and reports |

### 3.4 Execution integration tests

These tests require an approved local Docker capability and are separate from the offline suite. They must cover:

- approved test pass;
- approved test failure;
- timeout and process cleanup;
- output truncation;
- network denied;
- network approval path, if implemented;
- Docker build pass;
- Docker build failure;
- Docker unavailable;
- user denial;
- source manifest change during execution;
- cleanup failure reporting.

The tests must assert that the original fixture remains unchanged.

### 3.5 End-to-end CLI tests

Run the real CLI in temporary directories and verify:

- help/version behavior;
- terminal report ordering and key text;
- JSON output path and stdout behavior;
- exit codes;
- non-interactive execution denial;
- policy file parsing;
- Windows and Unix path handling where the CI matrix permits.

### 3.6 Security and abuse tests

Security tests must include shell metacharacters, command substitution, path traversal, symlink races where feasible, terminal control characters, malformed TOML/JSON, long strings, deeply nested directories, large output, fork/child-process behavior, and Docker context secret exclusions.

Property or fuzz testing is recommended for parsers, path handling, report serialization, and redaction.

## 4. Acceptance scenarios

### A-001: Safe first scan

**Given** a project directory with a README, manifests, and source files
**When** the user runs the default check command
**Then** ColdStart reads bounded files, does not execute project code, and reports evidence-backed results.

### A-002: Missing reproducibility evidence

**Given** a project without a pinned runtime or lockfile
**When** ColdStart scans it
**Then** the report identifies each missing item, explains why it matters, and suggests a specific fix.

### A-003: Documentation disagreement

**Given** a README command or runtime claim that conflicts with project metadata
**When** ColdStart scans it
**Then** it reports both evidence sources and does not choose silently.

### A-004: Permission denial

**Given** a project with a supported test command
**When** the user declines verification
**Then** no test runs, the report marks execution `not_verified`, and static findings remain available.

### A-005: Actual failed test

**Given** an approved sandbox and a test command that exits nonzero
**When** ColdStart runs it
**Then** the report records the actual exit code and failure without claiming the project passed.

### A-006: Clean Docker build attempt

**Given** a Dockerfile and explicit Docker-build approval
**When** the build is attempted
**Then** ColdStart records the build result, network mode, output limits, cleanup status, and any failure evidence.

### A-007: Unsupported environment

**Given** a project type or required runtime not supported by the available capability
**When** ColdStart checks it
**Then** it provides generic evidence, marks unsupported checks `not_verified`, and does not claim success.

## 5. Quality gates

The first release requires:

- `make test` passing offline;
- all contract and security tests passing;
- fixture-based findings reviewed for correctness;
- Docker verification tests passing in a Docker-enabled environment or explicitly marked as an environment gap;
- no known high-severity secret, command-injection, path-escape, or cleanup defect;
- documentation and report schema updated for any changed behavior;
- pinned runtime, lockfile, Dockerfile, and reproducible setup steps present;
- a release evidence record containing actual commands and results.

## 6. Current planning-phase verification

Because implementation has not been approved, there is no application test command to run. This documentation phase is checked with:

- `git diff --check` for whitespace errors;
- staged document review;
- cross-document consistency audit;
- confirmation that no application source or execution configuration was added.

These checks validate the specification, not ColdStart itself.
