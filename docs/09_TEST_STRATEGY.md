# ColdStart Test Strategy

**Status:** M1/M2/M3/M4/M5/M6/M6.1/M7/M8 tests implemented and passing in the available environment; target-runtime execution tests remain open
**Version:** 1.0
**Canonical command after implementation:** `make test`

## 1. Purpose and principles

The test strategy verifies user-visible behavior, security boundaries, report contracts, and ColdStart's own reproducibility. It does not treat test coverage as proof that arbitrary repositories are safe or universally reproducible.

1. Keep the P0 core offline and independent of inspected-project dependencies.
2. Use real clean and defective Python fixtures, not only mocked strings.
3. Verify denial and unknown states as carefully as successful paths.
4. Check terminal and JSON outputs against one normalized result.
5. Do not claim a test or build has passed until the command actually runs and its output is recorded.

## 2. Test layers

### Unit tests

Cover boundary normalization, file limits, discovery, project detection, applicability, each rule algorithm, evidence redaction, status semantics, policy calculation, exit codes, path normalization, command parsing, and deterministic serialization.

Advanced P0 unit coverage also includes evidence-strength classification and canonical audit-fingerprint calculation. Fingerprint tests must exclude timestamps, run IDs, absolute paths, and renderer formatting.

### Integration tests

Run the P0 engine over checked-in fixtures. Verify clean/defective findings, parser isolation, repository immutability, partial inventory, and cross-module lifecycle.

### CLI tests

Invoke the real CLI in temporary directories. Cover help/version, valid/invalid paths, terminal/JSON output, output paths, configuration, no-color output, stderr, and every exit code.

P1 CLI tests cover the implemented `explain CHECK_ID` command in `tests/test_phase7_m7_explain.py` and `compare CURRENT_REPORT BASELINE_REPORT` in `tests/test_phase8_m8_compare.py`, plus planned policy profiles and `verify --plan` coverage. Plan-only tests must prove that no child process starts. Explanation tests must prove complete offline metadata; comparison tests must prove compatibility validation, all change categories, fingerprint handling, deterministic ordering, safe diagnostics, and audit-pipeline isolation.

### Report-schema tests

Validate required fields, status/severity enums, relative paths, redaction, summary counts, deterministic ordering, version compatibility, and terminal/JSON parity. The example report must validate against the authoritative schema.

### Security tests

Exercise malicious filenames, shell metacharacters, argument injection, path traversal, symlinks, huge/malformed files, parser denial, secret-shaped values, terminal control sequences, output paths, temporary permissions, and no-default-execution instrumentation.

### P1 execution tests

Only after P0 is stable and Docker is available: test explicit authorization, offline test pass/fail, Docker build pass/fail, network denial, timeout, output truncation, process cleanup, source-manifest comparison, Docker unavailable, and user cancellation. These tests never become a prerequisite for P0 static usefulness.

### Offline and clean-environment tests

The canonical `make test` command must work without a network service after dependencies are installed in the project environment. A clean Linux checkout must build/run ColdStart using only documented setup. Docker build tests are separate but required for release readiness.

## 3. Fixtures

| Fixture | Purpose | Expected evidence |
| --- | --- | --- |
| `clean-python` | Minimal healthy P0 Python repository | Applicable checks pass or are explicitly `not_applicable` |
| `defective-python` | Missing pin/lockfile/docs/config issue | Stable failures with remediation |
| `conflicting-python` | README/runtime/lockfile disagreement | Conflict findings, no silent selection |
| `python-no-lock-required` | Documented pinned requirements policy | Lockfile `not_applicable`, not failed |
| `unknown-project` | No supported ecosystem | Generic results and explicit unknowns |
| `mixed-project` | Multiple metadata roots | Candidate list and applicability warnings |
| `malformed-metadata` | Invalid TOML/requirements text | Isolated error and partial report |
| `large-project` | File/byte/depth limits | Bounded incomplete result |
| `symlink-project` | Internal and external links | External link not followed |
| `path-escape-project` | `..`, absolute, missing resource references | Path findings with relative evidence |
| `secret-indicator-project` | Fake key/token and placeholders | Indicator without raw value |
| `terminal-control-project` | Escape/control characters | Safe terminal rendering |
| `p1-docker-project` | Dockerfile pass/fail build | Execution receipt only after approval |

Fixtures are synthetic and contain no real credentials or external data.

## 4. Naming and isolation conventions

- Unit: `test_<behavior>_<case>`.
- Integration: `test_fixture_<fixture>_<expected_result>`.
- CLI: `test_cli_<command>_<behavior>`.
- Security: `test_security_<threat_id>_<behavior>`.
- Contract: `test_contract_<schema_or_field>`.
- Every test gets a private temporary directory and restores process state.
- No test uses the user's home directory, real network, or real credentials.
- P1 Docker tests are marked separately and are not required by the offline P0 suite.

## 5. Acceptance-test matrix for P0 requirements

| Requirement | Acceptance test | Planned test ID |
| --- | --- | --- |
| FR-001 | Valid local path enters audit without persistent copy | AT-FR-001 |
| FR-002 | Invalid and escaping paths are rejected safely | AT-FR-002 |
| FR-003 | Inventory is stable and bounded | AT-FR-003 |
| FR-004 | Python/unknown/mixed applicability is explicit | AT-FR-004 |
| FR-005 | Default audit executes no project code | AT-FR-005 |
| FR-006 | Finding contract requires stable IDs/fields | AT-FR-006 |
| FR-007 | All six statuses are distinct and counted separately | AT-FR-007 |
| FR-008 | Defect evidence and remediation are actionable | AT-FR-008 |
| FR-009 | Terminal report is complete without color | AT-FR-009 |
| FR-010 | JSON report validates and matches terminal | AT-FR-010 |
| FR-011 | Exit codes match normalized policy result | AT-FR-011 |
| FR-012 | Invalid policy fails closed; valid policy is visible | AT-FR-012 |
| FR-013 | P0 works without network/AI/project deps | AT-FR-013 |
| FR-014 | Repository manifest is unchanged after audit | AT-FR-014 |
| FR-015 | P0 creates no staging workspace and P1 temp cleanup is verified | AT-FR-015 |
| FR-016 | Python fixture covers the full P0 catalog | AT-FR-016 |
| FR-017 | Clean setup/test/build docs are present and exact | AT-FR-017 |
| FR-028 | Evidence strength | Every finding uses one documented evidence-strength class | AT-FR-028 |
| FR-029 | Audit fingerprint | Equivalent normalized inputs produce the same fingerprint | AT-FR-029 |
| FR-030 | Self-audit | ColdStart audits its own release candidate | AT-FR-030 |
| NFR-001 | Repeated normalized reports are equivalent | AT-NFR-001 |
| NFR-002 | Instrumented static path has no execution/mutation | AT-NFR-002 |
| NFR-003 | Fake secrets and network data stay local/redacted | AT-NFR-003 |
| NFR-004 | Canonical test runs offline | AT-NFR-004 |
| NFR-005 | Malformed/unreadable files produce truthful partial results | AT-NFR-005 |
| NFR-006 | Resource limits terminate boundedly | AT-NFR-006 |
| NFR-007 | Windows/Unix/macOS path cases normalize | AT-NFR-007 |
| NFR-008 | Plain redirected output remains readable | AT-NFR-008 |
| NFR-009 | Schema/check versions are enforced | AT-NFR-009 |
| NFR-010 | Forbidden module dependencies are absent | AT-NFR-010 |
| NFR-011 | Clean Linux rebuild uses documented files | AT-NFR-011 |
| NFR-012 | Report contains provenance and limitations | AT-NFR-012 |
| NFR-015 | Evidence wording | Evidence class and wording are deterministic | AT-NFR-015 |

## 6. Acceptance-test matrix for P0 audit rules

| Check | Positive case | Negative/edge case | Planned test ID |
| --- | --- | --- | --- |
| CS-PROJECT-001 | `clean-python` discovery | empty/unreadable root | AT-CS-001 |
| CS-PROJECT-002 | Python metadata | mixed/unknown project | AT-CS-002 |
| CS-DEPS-001 | declared import | undeclared third-party import | AT-CS-003 |
| CS-DEPS-002 | applicable lockfile | no-lock-required policy / missing applicable lock | AT-CS-004 |
| CS-RUNTIME-001 | aligned pin | conflicting/absent runtime | AT-CS-005 |
| CS-DOCS-001 | complete setup sections | README-only description | AT-CS-006 |
| CS-DOCS-002 | documented pytest command | missing/contradictory command | AT-CS-007 |
| CS-CONFIG-001 | safe `.env.example` | required `.env` without template | AT-CS-008 |
| CS-CONFIG-002 | documented variable | undocumented required variable | AT-CS-009 |
| CS-PORT-001 | no suspicious paths | host-specific absolute path | AT-CS-010 |
| CS-SEC-001 | placeholder suppressed | fake private-key/token indicator | AT-CS-011 |
| CS-BUILD-001 | Dockerfile discovery | documented Docker workflow missing file | AT-CS-012 |
| CS-PATH-001 | contained resource | external/missing/`..` resource | AT-CS-013 |

## 7. Advanced improvement acceptance matrix

| Improvement | Release | Acceptance test |
| --- | --- | --- |
| Audit fingerprint | P0 | Reordered directory entries and equivalent policy serialization yield the same digest; changed evidence changes it |
| ColdStart self-audit | P0 | A release-candidate checkout produces a real report with reviewed findings and no simulated result |
| Baseline/diff | P1 | Added, resolved, unchanged, and severity/status-changed findings are identified by stable check ID |
| `explain CHECK_ID` | P1 | Every registered P0 check has purpose, applicability, algorithm, evidence, limitations, remediation, and test references; `tests/test_phase7_m7_explain.py` |
| `compare CURRENT_REPORT BASELINE_REPORT` | P1 | Compatible reports produce deterministic added/resolved/unchanged/changed categories and fingerprint comparison; `tests/test_phase8_m8_compare.py` |
| Policy profiles | P1 | Beginner, strict, and CI profiles produce documented policy differences without hiding or reclassifying findings |
| `verify --plan` | P1 | The plan shows command, working directory, network, limits, and side effects and launches no child process |

## 8. Regression and failure triage

Every fixed defect adds a minimal fixture or regression test with the original failure and expected status. Triage records:

1. command and fixture;
2. expected versus actual report/exit code;
3. whether the defect is in discovery, rule, normalization, renderer, policy, or runner;
4. security/privacy impact;
5. smallest fix and regression test;
6. actual re-run output.

Never change a fixture to make a failed test green without first recording why the expected behavior changed.

## 9. Coverage versus proof

Line/branch coverage measures which implementation paths tests visited; it does not prove that all repository formats, operating systems, package managers, hostile inputs, or external environments are safe. ColdStart's stronger evidence is the combination of boundary tests, deliberately broken repositories, contract tests, actual clean builds, and explicit limitations. No coverage percentage justifies a universal reproducibility claim.

## 10. Current test status

The current offline application suite is implemented and runs with the standard library. The latest command was:

```text
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

It ran 151 tests under Python 3.14.7: 148 passed and 3 platform-expected cases were skipped because Windows symlink/unreadable-file semantics cannot provide the portable fixture behavior. The M2-specific module ran 19 tests with 17 passes and the same 2 skips. The M3-specific modules ran 26 tests with 26 passes. The M4-specific modules ran 38 tests with 37 passes and one symlink skip. The M5 hardening module ran 7 tests with 7 passes. The M6 execution module ran 13 tests with 13 passes, the M6 CLI module ran 5 tests with 5 passes, the committed example-fixture module ran 2 tests with 2 passes, the M6 contract module ran 3 tests with 3 passes, the M7 explanation module ran 9 tests with 9 passes, and the M8 comparison module ran 15 tests with 15 passes. Compile checks also passed with `python -m compileall -q src build_backend tests examples`.

The exact Python 3.12.8 environment, `make test`, Docker build/run, clean Linux checkout, and actual Docker image execution remain unverified or planned. A compatible Python 3.12.10 run now passes the same 151-test suite, but it is not evidence that the exact `.python-version` pin or Linux/Docker release gate passed. The M6.1 tests verify the Docker isolation plan, read-only mount, fixed resource limits, no-host-fallback rule, and missing-Docker `not_verified` behavior.
