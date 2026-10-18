# ColdStart CLI and Report Contracts

**Status:** M1/M2/M3/M4/M5/M6.1 contract, M7 explain, and M8 compare commands implemented; Docker execution gates remain open
**Version:** 0.9
**Report schema:** `1.0`

## 1. Program identity and invocation

Program name: `coldstart`

Primary invocation:

```text
coldstart audit REPOSITORY_PATH [OPTIONS]
```

P1 invocations are separate from the P0 audit:

```text
coldstart verify REPOSITORY_PATH --kind tests --offline
coldstart verify REPOSITORY_PATH --kind docker-build
coldstart verify REPOSITORY_PATH --kind tests --plan
coldstart verify REPOSITORY_PATH --kind tests --authorize
coldstart explain CHECK_ID
coldstart compare CURRENT_REPORT BASELINE_REPORT
```

The P0 `audit` command never executes repository code. `verify` is a distinct command and is not a hidden side effect of `audit`. `--plan` never starts a child process. A child process requires the explicit `--authorize` flag; without it, the command records a denied receipt and returns exit code `3`.

## 2. Global options

| Option | Meaning | Default |
| --- | --- | --- |
| `--help` | Show command help and examples | N/A |
| `--version` | Show tool, report schema, and catalog versions | N/A |
| `--format terminal\|json` | Select renderer | `terminal` |
| `--output PATH` | Write the selected report | stdout |
| `--config PATH` | Read a policy file | Search `.coldstart.toml` at repository root if present |
| `--strict` | Treat configured unknown/incomplete states as a policy failure | false |
| `--profile beginner\|strict\|ci` | Select a documented P1 policy preset | none |
| `--no-color` | Disable terminal styling | auto based on TTY |
| `--max-files N` | Bound file inventory | documented default |
| `--max-bytes N` | Bound bytes read | documented default |
| `--max-depth N` | Bound directory traversal depth | documented default |
| `--max-seconds N` | Bound static audit time | documented default |
| `--exclude PATH` | Add a relative exclusion inside the boundary | built-in generated-dir exclusions |

Security-sensitive execution options are not accepted by `audit`. P1 options are specified separately and require an approval plan.

## 3. Argument validation

- `REPOSITORY_PATH` must resolve to a readable directory.
- A path containing a symlink that resolves outside the boundary is rejected or reported before inventory.
- Options requiring numeric limits reject zero, negative, overflow, and non-integer values.
- `--output` must be a file path, not a directory; parent creation is not automatic in P0.
- An invalid configuration returns exit code `2` and executes no repository code.
- A path in error messages is normalized and does not disclose a host username by default.

## 4. Help and version output

Help is plain text, available without a repository, and includes safe examples. Version output contains:

- program name and ColdStart version;
- report schema version;
- P0 check-catalog version;
- supported primary project type (`python`);
- whether the optional P1 runner is available, without claiming that a verification ran.

## 5. Standard streams and output behavior

- stdout is reserved for the requested report when `--format` is selected.
- stderr carries usage errors, diagnostics, permission prompts, and bounded internal warnings.
- `--format json` sends only one JSON report to stdout unless `--output` is supplied.
- Terminal output is safe when redirected and remains understandable without color.
- Project-provided text is escaped; terminal control sequences are never emitted from repository content.
- A report write failure is reported on stderr and returns the output failure code; it must not silently claim that a JSON report was saved.

## 6. Exit codes

| Code | Name | Meaning |
| --- | --- | --- |
| `0` | `OK` | Audit completed; no failed/error result violates the active policy. `not_applicable`, `skipped`, and `not_verified` remain visible and are not passes. |
| `1` | `FINDINGS` | Audit completed with a failed/error finding or policy violation. |
| `2` | `USAGE` | Invalid arguments, path, configuration, or output selection; no project execution. |
| `3` | `INCOMPLETE` | Audit coverage or an explicitly requested verification could not complete due to limits, denial, unavailable capability, unsupported host network isolation, or cancellation. |
| `4` | `INTERNAL` | ColdStart internal error; the report is incomplete or unavailable. |

`--strict` may promote configured `not_verified` results to `1` rather than `0`, but it never hides the original status. A `skipped` or `not_applicable` check is not a pass and is counted separately in the report.

## 7. Configuration-file behavior

The optional `.coldstart.toml` policy contains:

- `schema_version`;
- `name`;
- `fail_on` severity;
- `treat_not_verified_as` (`allow`, `review`, or `fail`);
- `required_checks`;
- justified `excluded_checks`;
- bounded inventory limits;
- output defaults.

It must not contain secrets, arbitrary shell commands, executable paths, remote URLs, or a hidden execution enablement. Invalid/ambiguous configuration is fail-closed. Command-line display options may override policy presentation; required checks and security limits may not be weakened silently.

## 8. Finding schema

The following fields are authoritative for schema version `1.0`.

| Field | Required | Nullable | Type | Rules |
| --- | --- | --- | --- | --- |
| `schema_version` | yes, top-level | no | string | Exactly `1.0` for this contract |
| `check_id` | yes | no | string | Stable ID from `docs/06_CHECK_CATALOG.md` |
| `severity` | yes | no | enum | `info`, `warning`, `error`, `blocking` |
| `status` | yes | no | enum | `passed`, `failed`, `not_applicable`, `skipped`, `not_verified`, `error` |
| `title` | yes | no | string | Short, stable human label |
| `message` | yes | no | string | Plain-language result, bounded and redacted |
| `evidence` | yes | no | array | One or more evidence/absence objects, unless an internal error has a safe error object |
| `remediation` | yes | yes | array/string/null | Actionable guidance; null when no safe fix can be inferred |
| `affected_path` | yes | yes | string/null | Project-relative normalized path or null |
| `category` | yes | no | enum | `project`, `dependencies`, `runtime`, `documentation`, `configuration`, `portability`, `security`, `build`, `execution` |
| `applicability` | yes | no | object | Applicable/`not_applicable` reason and adapter |
| `rule_version` | yes | no | string | Algorithm version |
| `evidence_strength` | yes | no | enum | `direct`, `derived`, `indicator`, `absence`, `unverified` |

An evidence object contains:

```json
{
  "kind": "file|directory|metadata|command|absence|execution|policy|error",
  "path": "relative/path-or-null",
  "line_start": 1,
  "line_end": 1,
  "detail": "redacted bounded explanation",
  "digest": "optional digest or null"
}
```

Line fields and `path` are nullable. Secret values, usernames, home directories, and unrestricted source snippets are omitted or redacted.

## 9. Top-level JSON report

Required fields:

```text
schema_version
tool
invocation
repository
detection
findings
policy
verification
redaction
summary
```

`tool` contains name/version/catalog version. `invocation` contains safe options and boundary limits. `repository` contains a local label, scan-boundary summary, and required `audit_fingerprint`, not an absolute path by default. `detection` contains candidates, bounded inventory statistics, the relative `file_inventory`, applicability decisions, detection limitations, and fingerprint inputs. `policy` contains policy name, decision, configured unknown handling, and violations. `verification` contains requested/authorized/executed actions. `redaction` contains mode and counts, never values. `summary` contains counts by status/severity and overall decision.

### Audit fingerprint

`audit_fingerprint` is a lowercase SHA-256 digest over a canonical serialization of:

- ColdStart tool version;
- check-catalog version;
- normalized policy and applicable limits;
- normalized relative paths and bounded file metadata/content digests;
- project-detection and applicability inputs.

The fingerprint excludes report IDs, timestamps, absolute paths, terminal formatting, and unbounded source content. It identifies the audited evidence state; it does not prove that the project is universally reproducible.

The companion JSON Schema and sanitized example are stored in `docs/contracts/report-v1.schema.json` and `docs/contracts/report-v1.example.json`; they must be updated whenever this contract changes.

## 10. Human-readable report layout

```text
ColdStart <version> | schema <version> | catalog <version>
Repository: <safe label> | Type: <candidate/confidence>
Result: <pass / needs attention / incomplete>

Summary: passed=N failed=N not_applicable=N skipped=N not_verified=N error=N

[SEVERITY] CHECK-ID — Title
  Status: <status>
  Evidence strength: <direct / derived / indicator / absence / unverified>
  Message: <plain-language explanation>
  Evidence: <relative path/line or explicit absence>
  Fix: <actionable remediation>

Verification: not requested / denied / unavailable / actual receipt
Limitations: <unknowns and skipped coverage>
Next step: <highest-value action>
Exit code: <number>
```

Findings sort by severity rank, then category, then `check_id`. The renderer never changes status or policy semantics.

## 11. Path normalization and deterministic ordering

- Evidence paths are relative to the repository boundary.
- Use `/` as the report separator on every operating system.
- Normalize `.` and reject external `..` traversal.
- Sort file paths, candidate types, findings, and evidence deterministically.
- Exclude run ID and timestamps from normalized-result comparisons.
- Calculate `audit_fingerprint` only from the canonical normalized inputs defined above.

## 12. Compatibility and versioning

The major report schema version changes when required fields or status meaning changes. Additive optional fields are compatible within `1.x`; removals or semantic changes require `2.0` and a migration note. Check algorithm changes increment `rule_version`. Terminal text may improve without changing the JSON contract, but exit-code meaning cannot change silently.

## 13. P1 execution receipt contract

The M6 runner implements the first bounded form of this contract. Every P1 attempt contains:

- `execution_id`, kind, authorization state, and candidate source;
- safe structured argv/build request and repository working-directory label;
- network mode and resource/time/output limits;
- observed exit code or termination reason;
- output truncation/digest state;
- cleanup status and source-manifest comparison;
- actual result status and limitation.

No receipt with no observed execution may claim `passed`.

The current runner accepts only direct Python `unittest`/`pytest` commands or a fixed Docker build command; shell operators, arbitrary scripts, Make recipes, and absolute command paths are rejected. Offline test plans use Docker's `--network=none`, `--pull=never`, a read-only `/workspace` bind mount, fixed `tmpfs`/CPU/memory/process limits, and no host fallback. If Docker is missing or cannot start, the attempt returns `not_verified` without executing the test command on the host.

## 14. Advanced P1 command contracts

### `coldstart explain CHECK_ID`

Implemented. This command reads only bundled reviewed check metadata and prints the check purpose, applicability, algorithm summary, evidence-strength semantics, limitations, test references, and remediation guidance. It does not require a repository, inspect project files, call an AI service, or execute code. `CHECK_ID` must exactly match one of the 13 registered P0 catalog IDs; an unknown ID returns usage exit code `2` and writes no report to stdout.

### `coldstart compare CURRENT_REPORT BASELINE_REPORT`

Implemented. This command compares compatible local JSON reports by stable finding ID and audit fingerprint. The first argument is the current report and the second is the baseline. It reports `added`, `resolved`, `unchanged`, and `changed` findings, including changed fields and a conservative `worsened`, `improved`, or `changed` direction. Finding-array order does not affect the result. A changed audit fingerprint is reported separately and does not replace per-finding comparison. Compatible differences return exit code `0`; malformed, invalid, or incompatible reports return usage exit code `2` without comparison JSON on stdout.

The dedicated comparison contract is documented in `docs/contracts/comparison-v1.schema.json` with a sanitized example in `docs/contracts/comparison-v1.example.json`. Comparison output is separate from the audit report schema and contains no input report paths or raw report documents.

### `--profile`

The `beginner`, `strict`, and `ci` profiles are policy presets. They may change display detail, unknown handling, and exit policy, but they must not remove findings, change rule algorithms, or turn a non-pass status into `passed`.

### `verify --plan`

The plan-only flag renders the proposed P1 operation and constraints, returns without launching a child process, and records no execution receipt claiming that a command ran. Use `--authorize` only after reviewing that plan.
