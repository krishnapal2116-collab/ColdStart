# ColdStart Requirements Traceability

**Status:** Proposed for approval
**Version:** 0.1

This matrix connects the product requirements to the design and the planned verification evidence. Test IDs are planned identifiers for the implementation phase; their presence in this document is not a claim that the tests already exist.

## 1. Functional traceability

| Requirements | Design location | Planned verification |
| --- | --- | --- |
| CS-F-001–006 | Product scope; architecture sections 3–4; security sections 6–7 | T-BOUND-01..06; A-001; large/symlink fixtures |
| CS-F-010–015 | Requirements support matrix; architecture adapter model | T-DETECT-01..06; mixed and unsupported fixtures |
| CS-F-020–028 | Requirements static checks; architecture pipeline; contract finding model | T-STATIC-01..09; clean/missing/mismatch fixtures |
| CS-F-030–038 | Contract sections 3–6; audit rules AR-001..015 | T-REPORT-01..08; terminal/JSON parity tests |
| CS-F-040–049 | Architecture execution flow; security authorization protocol; failure state model | T-EXEC-01..14; A-004..006; Docker-enabled suite |
| CS-F-050–055 | Product CI journey; architecture baseline; verification section 2 | T-CI-01..06; packaging and offline build gate |

## 2. Non-functional traceability

| Requirement | Design evidence | Planned verification |
| --- | --- | --- |
| CS-N-001 Safety | Security objectives 1–3; execution broker boundary | T-SEC-01..12; A-001 and A-004 |
| CS-N-002 Privacy | Security privacy rules; contract redaction object | T-PRIV-01..08 |
| CS-N-003 Determinism | Audit integrity and serializer rules | T-DET-01..04; repeated fixture runs |
| CS-N-004 Portability | Architecture baseline and initial support matrix | T-PLAT-01..06 on supported OS matrix |
| CS-N-005 Recoverability | Failure state model and cleanup policy | T-RES-01..08 |
| CS-N-006 Usability | Product principles and terminal contract | T-UX-01..05; beginner review |
| CS-N-007 Performance | Requirements target; inventory limits | T-PERF-01..04 with representative fixtures |
| CS-N-008 Resource safety | Security controls and failure matrix | T-RESOURCE-01..08 |
| CS-N-009 Maintainability | Adapter model and planned repository shape | T-ARCH-01..04; adapter contract tests |
| CS-N-010 Auditability | Audit rules AR-001..015 and execution receipt contract | T-AUDIT-01..10 |

## 3. User-outcome traceability

| User outcome | Requirements | Evidence expected |
| --- | --- | --- |
| Know what project type is present | CS-F-010–015 | Detector evidence and confidence |
| Find missing dependencies/runtime/setup/test information | CS-F-020–025 | Check findings with relative paths and fixes |
| Detect documentation disagreement | CS-F-026–027 | Paired file/metadata evidence |
| Receive a useful terminal report | CS-F-030–036 | Terminal contract tests |
| Automate review in CI | CS-F-031, CS-F-050, CS-F-054 | JSON, policy, exit-code, and offline tests |
| Verify rather than assume | CS-F-040–049 | Execution receipts and actual exit status |
| Stay safe by default | CS-F-040–048, CS-N-001–002 | Denial, redaction, sandbox, and no-network tests |

## 4. Traceability maintenance rule

Any implementation change that adds, removes, or changes a check must update the check registry, this matrix, the report contract if needed, at least one fixture or unit test, and the user-facing documentation. A changed requirement cannot be silently implemented without updating its evidence path.
