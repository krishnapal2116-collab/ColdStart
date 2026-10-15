# ColdStart Interface and Data Contract

**Status:** Proposed for approval
**Version:** 0.1
**Contract version:** `1.0`

## 1. CLI interface

The proposed primary command is:

```text
coldstart check PROJECT_PATH [OPTIONS]
```

The command always performs the safe static scan first.

### Core options

| Option | Meaning | Default |
| --- | --- | --- |
| `PROJECT_PATH` | Directory to inspect | Required |
| `--format terminal\|json` | Select output format | `terminal` |
| `--output FILE` | Write the selected report to a file | stdout |
| `--policy FILE` | Load a local policy file | Built-in policy |
| `--no-score` | Omit the optional readiness score | Score enabled if supported |
| `--max-seconds N` | Static scan time budget | Built-in safe limit |
| `--include PATH` | Add a bounded path within the root | None |
| `--exclude PATH` | Exclude a relative path | Built-in generated-directory exclusions |
| `--version` | Print ColdStart version and contract version | N/A |

### Verification options

| Option | Meaning | Safety rule |
| --- | --- | --- |
| `--verify tests` | Propose supported test verification | Shows plan and prompts |
| `--verify docker-build` | Propose a clean Docker build | Shows separate high-risk plan and prompts |
| `--verify tests,docker-build` | Propose both classes | Requires separate approval for each |
| `--non-interactive` | Disable prompts for CI | Denies execution unless explicit policy allows it |
| `--allow-execution` | Opt into policy-authorized execution in non-interactive mode | Never selects an arbitrary command by itself |
| `--network none\|default` | Requested network mode for approved execution | `none`; `default` requires separate approval |

The exact flag names may change during implementation only through an ADR and contract update. There must not be a hidden environment variable that enables execution.

## 2. Exit codes

| Code | Meaning | CI interpretation |
| --- | --- | --- |
| `0` | Scan completed and no configured blocking finding exists | Pass |
| `1` | Scan completed with a configured policy violation or an executed check failed | Fail |
| `2` | Invalid invocation, invalid policy, or invalid project path | Configuration error |
| `3` | Requested verification was denied, unavailable, or not verified | Review required; policy may choose fail or allow |
| `4` | ColdStart internal error or incomplete report | Fail and investigate |

Static `not_verified` results use code `0` under the permissive built-in policy but remain visible in the report. A strict CI policy may treat them as violations and return `1`.

## 3. Finding contract

Every check result MUST have these fields:

| Field | Type | Rule |
| --- | --- | --- |
| `id` | string | Stable namespaced identifier, for example `runtime.python.version` |
| `version` | string | Check logic version, incremented when semantics change |
| `category` | enum | `project`, `runtime`, `dependencies`, `documentation`, `build`, `portability`, `execution`, or `security` |
| `title` | string | Human-readable title |
| `status` | enum | `passed`, `failed`, `not_verified`, `skipped`, or `error` |
| `severity` | enum | `info`, `warning`, `error`, or `blocking` |
| `summary` | string | Concise explanation of the result |
| `evidence` | array | One or more safe references, or an explicit absence reason |
| `recommendations` | array | Zero or more actionable suggestions |
| `adapter` | string | `generic`, `python`, `node`, or another registered adapter |

An evidence item has:

| Field | Type | Rule |
| --- | --- | --- |
| `kind` | enum | `file`, `directory`, `command`, `metadata`, `execution`, `absence`, or `policy` |
| `path` | string/null | Project-relative and normalized; null when not applicable |
| `line_start` / `line_end` | integer/null | Optional 1-based range |
| `detail` | string | Redacted, bounded explanation; never a secret value |
| `digest` | string/null | Optional digest of bounded content or output |

## 4. Top-level JSON report contract

The JSON report is an object with the following required top-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | Report contract version, currently `1.0` |
| `report_id` | string | Unique local report identifier; not a user identity |
| `tool` | object | Name, version, and build metadata |
| `input` | object | Relative project label, scan options, and boundary summary |
| `project` | object | Ecosystems, confidence, and adapter coverage |
| `checks` | array | Stable ordered finding objects |
| `policy` | object | Policy name, score if enabled, violations, and final decision |
| `verification` | object | Requested, authorized, and executed actions |
| `redaction` | object | Redaction mode and counts, never secret values |
| `summary` | object | Counts by status and severity plus overall result |

### Required invariants

1. `checks` is present even when empty.
2. Every check `id` is unique within a report.
3. Evidence paths are relative to the declared project root or null.
4. `verification.executions` is empty when no execution was authorized.
5. An execution result cannot be `passed` without an observed exit status of zero and successful cleanup.
6. A static check cannot claim an execution result.
7. The summary counts equal the values derived from `checks`.
8. Any omitted capability appears in `verification` or a `not_verified` finding.
9. JSON key order is stable for snapshot tests, although consumers must use names rather than order.
10. Secret-shaped values and host identity are redacted before serialization.

## 5. Execution receipt contract

Each attempted action has:

- `execution_id`;
- `kind`: `tests` or `docker_build`;
- selected command or Docker operation, represented safely;
- candidate source and reason for selection;
- authorization state and timestamp;
- staged workspace identifier;
- network mode;
- resource limits;
- start/end time and duration;
- exit code or termination reason;
- output capture status and digest;
- cleanup result;
- source manifest-change result.

The receipt must not contain inherited environment values, credentials, or unrestricted command output. Bounded output may be included only after redaction.

## 6. Terminal report contract

The terminal report must present, in order:

1. Project label and detected type.
2. Overall status and optional score.
3. A compact count summary.
4. Findings ordered by severity, then stable check identifier.
5. Evidence and suggested fix for each warning or failure.
6. Verification plan/result and permission state.
7. A clear next-step section.

Project-provided text must be escaped so it cannot emit terminal control sequences.

## 7. Policy contract

The optional `.coldstart.toml` policy should define only review policy, limits, and explicit execution permissions. It must not contain secrets. Proposed fields are:

- `schema_version`;
- `name`;
- `fail_on` severity;
- `treat_not_verified_as` (`allow`, `warn`, or `fail`);
- `required_checks`;
- `excluded_checks` with a justification;
- static resource limits;
- verification permission and network mode;
- output format defaults.

Policy parsing is fail-closed: an invalid or ambiguous policy returns exit code `2` and does not run project code.

## 8. Compatibility policy

The report schema is versioned independently from the ColdStart executable. Additive fields are allowed within a major version. Removing or changing the meaning of an existing field requires a new major schema version and a migration note. Check logic changes use the individual check `version` field.
