# ColdStart Requirement Traceability

**Status:** M1/M2/M3/M4/M5/M6/M6.1 verification slices implemented and tested; target execution gates remain open
**Version:** 0.8

This matrix is the authoritative link between requirements, modules, checks/contracts, tests, acceptance criteria, and verification method. Rows are implemented only where the corresponding code, tests, and actual command output exist; documentation does not count as implementation evidence. M1/M2 cover the safe audit/report foundation and bounded discovery/applicability. M3 covers dependency, lockfile, runtime, and setup-documentation checks. M4 completes the remaining seven P0 static catalog checks. M6 implements the explicit plan/authorization/receipt slice for P1 verification. M6.1 adds Docker-backed offline test isolation; target-runtime and Docker image execution remain unverified.

## 1. Functional requirements

| ID | Summary | Priority | Responsible module | Check/contract | Required test | Acceptance criterion | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FR-001 | Accept local path without persistent copy | P0 | `cli`, `boundary` | CLI intake | `test_valid_path_intake` | Valid path enters audit; no snapshot | CLI/integration |
| FR-002 | Validate boundary | P0 | `boundary` | `CS-PATH-001` | `test_boundary_escape_inputs` | Invalid/escape paths stop safely | Security/integration |
| FR-003 | Discover files/metadata | P0 | `discovery` | `CS-PROJECT-001` | `test_deterministic_inventory` | Stable bounded inventory | Unit/integration |
| FR-004 | Detect type/applicability | P0 | `discovery`, `checks` | `CS-PROJECT-002` | `test_python_and_unknown_detection` | Python and ambiguity are explicit | Integration |
| FR-005 | Run static checks only | P0 | `checks` | P0 catalog | `test_static_audit_never_executes` | No project process | Security |
| FR-006 | Stable finding identity | P0 | `findings` | Finding schema | `test_required_finding_fields` | Valid IDs/fields | Contract |
| FR-007 | Distinct statuses | P0 | `findings`, `policy` | Status enum | `test_all_status_semantics` | Unknowns not passes | Unit/contract |
| FR-008 | Evidence/remediation | P0 | `findings`, `reporting` | Evidence schema | `test_defect_evidence_and_fix` | Relative evidence and fix | Integration |
| FR-009 | Terminal report | P0 | `reporting` | Terminal layout | `test_terminal_report_layout` | Readable no-color report | CLI |
| FR-010 | JSON report | P0 | `reporting` | JSON schema 1.0 | `test_report_schema` | Schema-valid JSON | Contract |
| FR-011 | Exit codes | P0 | `policy`, `cli` | Exit table | `test_exit_code_matrix` | Code matches policy/result | CLI |
| FR-012 | Local configuration | P0 | `config`, `policy` | TOML policy | `test_policy_parse_fail_closed` | Valid changes policy; invalid stops | Unit/CLI |
| FR-013 | No AI/network/deps in P0 | P0 | `cli`, `checks` | Privacy contract | `test_p0_offline_no_network` | P0 works without services | Offline/security |
| FR-014 | Repository read-only | P0 | `boundary`, `reporting` | Privacy contract | `test_static_manifest_unchanged` | No source mutation | Integration |
| FR-015 | P0 staging-free; P1 temp cleanup | P0 | `boundary` | Cleanup rules | `test_p0_no_staging_and_p1_cleanup` | No P0 staging; no unreported P1 temp | Integration |
| FR-016 | Python P0 adapter | P0 | `checks/python` | P0 catalog | `test_python_fixture_catalog` | Python fixture checks work | Integration |
| FR-017 | ColdStart setup docs | P0 | repository docs | Build contract | `test_clean_checkout_procedure` | Exact commands documented | Build/review |
| FR-018 | Authorized offline tests | P1 | `execution` | Verify receipt | `test_execution_authorization` | Actual receipt or unknown | Docker/integration |
| FR-019 | Authorized Docker build | P1 | `execution` | Verify receipt | `test_docker_build_receipt` | Actual build result | Docker/integration |
| FR-020 | SARIF export | P1 | `reporting` | SARIF contract | `test_sarif_output_if_enabled` | Valid or clearly deferred | Contract |
| FR-021 | Baseline comparison | P1 | `policy`, `reporting` | Baseline format | `test_baseline_diff` | Stable changes | Integration |
| FR-022 | Additional adapter | P1 | `checks/<adapter>` | New catalog | `test_second_adapter_contract` | Full adapter evidence | Integration |
| FR-023 | AI fixes/judgments | P2 | none | Explicit non-goal | `test_no_ai_dependency` | No P0 path requires AI | Review |
| FR-024 | Auto-modification | P2 | none | Read-only contract | `test_no_repository_write_path` | No write API | Security |
| FR-025 | Remote/hosted service | P2 | none | Local-only contract | `test_no_remote_ingestion` | Local path only | Review |
| FR-026 | Agents/distributed/plugins | P2 | none | Scope boundary | `test_mvp_dependency_inventory` | No framework required | Review |
| FR-027 | Universal guarantee | P2 | `reporting`, docs | Limitation text | `test_report_has_limitations` | No overclaim | Contract/review |
| FR-028 | Evidence-strength taxonomy | P0 | `findings`, `reporting` | Finding schema | `test_evidence_strength_contract` | Stable class, no invented percentage | Contract |
| FR-029 | Audit fingerprint | P0 | `findings`, `reporting` | Report repository field | `test_fingerprint_stability` | Equivalent inputs yield same fingerprint | Determinism |
| FR-030 | ColdStart self-audit | P0 | release process, `cli` | Release gate | `test_self_audit_fixture` | Release evidence contains actual self-audit | Release/integration |
| FR-031 | Baseline comparison | P1 | `policy`, `reporting` | Compare command | `test_baseline_diff` | Added/resolved/changed findings are stable | Integration |
| FR-032 | Rule explanation | P1 | `cli`, `checks` | Explain command | `test_explain_check` | Catalog explanation is complete and offline | CLI |
| FR-033 | Policy profiles | P1 | `config`, `policy` | Profile option | `test_policy_profiles` | Profiles preserve rule/status semantics | Contract/CLI |
| FR-034 | Plan-only verification | P1 | `execution`, `cli` | Verify plan | `test_verify_plan_no_child` | Plan displays constraints without execution | Security/CLI |

## 2. Non-functional requirements

| ID | Summary | Priority | Responsible module | Check/contract | Required test | Acceptance criterion | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NFR-001 | Deterministic findings | P0 | all core | Ordering rules | `test_repeat_normalized_report` | Equivalent repeated result | Determinism |
| NFR-002 | Safe default | P0 | `boundary`, `checks` | Threat model | `test_no_default_execution` | No subprocess/mutation | Security |
| NFR-003 | Local privacy/redaction | P0 | `findings`, `reporting` | Privacy contract | `test_secret_redaction` | No value/upload | Security/privacy |
| NFR-004 | Offline core | P0 | packaging/tests | Build contract | `test_offline_suite` | No network service | Offline |
| NFR-005 | Partial truthful failure | P0 | `checks`, `findings` | Error model | `test_parser_isolation` | No false pass | Integration |
| NFR-006 | Bounded resources | P0 | `boundary`, `discovery` | Limit options | `test_file_and_time_limits` | Bounded termination | Resource |
| NFR-007 | Cross-platform static CLI | P0 | `boundary`, `cli` | Path rules | `test_platform_path_matrix` | Supported OS behavior | Platform |
| NFR-008 | Accessible plain output | P0 | `reporting` | Terminal layout | `test_no_color_and_redirect` | Meaning survives plain text | CLI |
| NFR-009 | Versioned compatibility | P0 | `reporting`, `version` | Schema 1.0 | `test_schema_version_rules` | Contract changes gated | Contract |
| NFR-010 | Maintainable modules | P0 | package structure | Dependency rules | `test_module_dependency_boundaries` | No forbidden imports | Architecture |
| NFR-011 | Reproducible ColdStart | P0 | packaging/docs | Build plan | `test_clean_linux_build` | Pinned setup works | Clean build |
| NFR-012 | Auditable results | P0 | `findings`, `reporting` | Provenance fields | `test_report_provenance` | Options/status/versions present | Contract |
| NFR-013 | Constrained P1 execution | P1 | `execution` | Receipt contract | `test_timeout_output_network_controls` | Limits recorded/enforced | Docker/security |
| NFR-014 | Docker optional for P0 | P1 | `execution`, `cli` | Unavailable semantics | `test_static_without_docker` | Static report still useful | Integration |
| NFR-015 | Deterministic evidence wording | P0 | `findings`, `reporting` | Evidence-strength enum | `test_evidence_wording` | Same evidence yields same class/text | Determinism |

## 3. P0 check traceability

| Check ID | Requirement(s) | Required test |
| --- | --- | --- |
| CS-PROJECT-001 | FR-003, FR-004, NFR-005 | `test_project_metadata_discovery` |
| CS-PROJECT-002 | FR-003, FR-004, NFR-001 | `test_project_detection_confidence` |
| CS-DEPS-001 | FR-005, FR-008, FR-016 | `test_dependency_declaration_cases` |
| CS-DEPS-002 | FR-005, FR-008, FR-016, NFR-009 | `test_lockfile_applicability` |
| CS-RUNTIME-001 | FR-005, FR-008, FR-016, NFR-007 | `test_runtime_declaration_cases` |
| CS-DOCS-001 | FR-005, FR-008, FR-017 | `test_setup_documentation_cases` |
| CS-DOCS-002 | FR-005, FR-008, FR-017 | `test_test_command_consistency` |
| CS-CONFIG-001 | FR-005, FR-008, NFR-003 | `test_config_example_cases` |
| CS-CONFIG-002 | FR-005, FR-008, NFR-003 | `test_environment_documentation_cases` |
| CS-PORT-001 | FR-005, FR-008, NFR-007 | `test_absolute_path_cases` |
| CS-SEC-001 | FR-005, FR-008, NFR-003 | `test_secret_indicator_redaction` |
| CS-BUILD-001 | FR-005, FR-008, FR-019, NFR-014 | `test_container_discovery_cases` |
| CS-PATH-001 | FR-002, FR-005, FR-014, NFR-002 | `test_contained_path_cases` |

## 4. State rule

Every row above remains `specified/not implemented` unless the implementation, appropriate tests, and actual command output exist. A future audit must use `implemented`, `tested`, `verified`, `deferred`, or `blocked` only with evidence. The implementation-state sections below narrow that rule without claiming target-runtime, Make, Docker, or clean-Linux verification that has not run.

## 5. M1 implementation state

The following requirements now have implementation and test evidence in the M1 slice:

- `FR-001`, `FR-002`, `FR-006`, `FR-007`, `FR-009`, `FR-010`, `FR-011`, `FR-028`, and `FR-029` — implemented and tested under Python 3.14.7.
- `NFR-001`, `NFR-002`, and `NFR-015` — implemented and tested under Python 3.14.7.

The M1 evidence does not verify the pinned Python 3.12.8 environment, Make, Docker, or the later catalog requirements. Those remain explicitly unverified or specified-only until their corresponding commands and slices run.

## 6. M2 implementation state

The following requirements now have implementation and test evidence in the M2 slice:

- `FR-003`, `FR-004`, `FR-012`, `FR-014`, and `FR-015` — bounded deterministic inventory, Python/Node/unknown/mixed detection, fail-closed `.coldstart.toml` policy parsing, read-only inventory, and no P0 staging workspace.
- `NFR-005`, `NFR-006`, `NFR-007`, and `NFR-012` — partial-coverage findings, file/byte/depth/time bounds, exclusion and symlink handling, and report provenance for limits, policy, inventory, detection, applicability, and limitations.
- M2 report behavior is covered by `tests/test_phase3_m2_discovery.py`: 19 tests, with 17 executed successfully and 2 platform-expected skips on the current Windows environment.

The integrated offline command currently passes 94 executed tests with 3 platform-expected skips under Python 3.14.7. M2 exposes bounded discovery and applicability; M3 evaluates `CS-DEPS-001`, `CS-DEPS-002`, `CS-RUNTIME-001`, and `CS-DOCS-001`; M4 evaluates the remaining seven catalog checks. Python 3.12.8, Make, Docker, clean-Linux verification, and P1 project test/build execution remain unverified.

## 7. M3 implementation state

The following requirements now have implementation and test evidence in the M3 slice:

- `FR-005`, `FR-008`, and `FR-016` for dependency declaration, applicable lockfile, runtime declaration, and setup-documentation findings that use bounded static evidence and never execute repository code.
- `NFR-012` for M3 rule versions, applicability, evidence, remediation, limitations, and report provenance.
- M3 coverage is provided by `tests/test_phase3_m3_dependencies.py`, `tests/test_phase3_m3_runtime_docs.py`, and `tests/test_phase3_m3_integration.py`: 26 tests passed under Python 3.14.7.

The M3 slice by itself did not implement `CS-DOCS-002` or the remaining configuration, portability, security, and build-discovery checks; M4 now supplies those static findings. Exact Python 3.12.8, Make, Docker, and clean-Linux verification remain open.

## 8. M4 implementation state

The following requirements now have implementation and test evidence in the M4 slice:

- `FR-005`, `FR-008`, `FR-016`, and `FR-027` for test-command documentation, configuration examples, environment-variable documentation, portability indicators, redacted security indicators, container configuration discovery, and repository-contained path validation.
- `NFR-003`, `NFR-008`, and `NFR-012` for secret-safe evidence, plain terminal/JSON visibility, bounded redaction, applicability, remediation, and report provenance.
- M4 coverage is provided by `tests/test_phase4_m4_docs_config.py`, `tests/test_phase4_m4_quality.py`, and `tests/test_phase4_m4_integration.py`: 38 tests, with 37 executed successfully and one platform-expected symlink skip on the current Windows environment.

All 13 P0 catalog IDs now produce one static finding each in a complete report. A static result does not claim that a project test or container build executed; those remain P1 verification work.

## 9. M5 hardening and release-candidate state

M5 adds `tests/test_phase5_m5_hardening.py`, covering:

- complete 13-check self-audit coverage and one-finding-per-catalog-ID behavior;
- safe output/redaction and absence of staging or repository execution;
- repeated report/fingerprint stability;
- terminal/JSON semantic parity and finding-contract enums;
- release-file presence and canonical Makefile/Dockerfile/runtime documentation;
- malicious-fixture non-execution and control-like/secret-shaped evidence handling.

The M5 module has 7 passing tests under Python 3.14.7. The integrated offline suite has 101 passing tests with 3 platform-expected skips. Exact Python 3.12.8, GNU Make, Docker, clean Linux, and authorized project test/build execution remain unverified.

## 10. M6/M6.1 verification slice

M6 adds `src/coldstart/execution.py`, the distinct `verify` CLI command, receipt rendering, and:

- `verify --plan` with no child-process launch;
- explicit `--authorize` gating and denied receipts;
- structured direct Python `unittest`/`pytest` argv validation without shell execution;
- bounded timeout/output capture, source-manifest comparison, cleanup status, and safe receipt redaction;
- fixed Docker build planning and truthful Docker-unavailable receipts;
- Docker-backed handling for `tests --offline` with `network=none`, read-only mount, fixed resource limits, and no host fallback; missing Docker remains `not_verified`.

The committed `examples/clean-python` and `examples/defective-python` fixtures complete the P0 demo-input requirement. `tests/test_phase6_m6_examples.py` verifies their expected CLI statuses and read-only behavior.

Coverage is provided by `tests/test_phase6_m6_execution.py` (13 tests), `tests/test_phase6_m6_cli.py` (5 tests), `tests/test_phase6_m6_examples.py` (2 tests), and `tests/test_phase6_m6_contract.py` (3 tests). The latest integrated suite has 124 passing tests with 3 platform-expected skips under Python 3.14.7. This is not evidence for Python 3.12.8, Make, Docker image execution, or a clean Linux environment.
