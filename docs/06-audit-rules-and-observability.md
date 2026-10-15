# ColdStart Audit Rules and Observability

**Status:** Proposed for approval
**Version:** 0.1

## 1. Purpose

ColdStart's central promise is that its report can be trusted. A reviewer must be able to see what ColdStart inspected, which rule produced a result, what evidence supports it, and whether an execution actually occurred. This document defines the audit rules that preserve that promise without collecting telemetry or leaking project data.

## 2. Audit rules

| Rule | Requirement |
| --- | --- |
| AR-001 | Every check has a stable identifier and check logic version. |
| AR-002 | Every `passed`, `failed`, `skipped`, and `error` result has evidence or a precise reason. |
| AR-003 | Every `not_verified` result states which capability, evidence, or authorization was missing. |
| AR-004 | Evidence paths are relative to the declared project root unless the user explicitly requests diagnostic absolute paths. |
| AR-005 | Evidence is bounded in size and redacted before report serialization. |
| AR-006 | Static findings and execution findings are represented separately. |
| AR-007 | An execution result includes the observed exit status or termination reason, not an inferred result. |
| AR-008 | The report records the tool version, report schema version, adapter versions, and effective options. |
| AR-009 | The report records the scan boundary, exclusions, resource limits, and symlink policy. |
| AR-010 | The report records whether execution was requested, authorized, denied, unavailable, or completed. |
| AR-011 | The report is ordered deterministically by category, severity, and stable check identifier. |
| AR-012 | A report cannot silently drop a check because a parser or adapter failed; it records `error` or `not_verified`. |
| AR-013 | Policy violations include the policy rule and justification for the resulting exit code. |
| AR-014 | A user can distinguish a finding generated from a file from one generated from an execution receipt. |
| AR-015 | Report generation itself does not alter the inspected project. |

## 3. Provenance model

Each finding carries enough provenance to answer:

- Which check implementation produced it?
- Which adapter, if any, was active?
- Which files or metadata were considered?
- What scan options and limits applied?
- Was the result static or execution-derived?
- What authorization state existed at the time?

The report may include a `provenance` object with tool and adapter versions, but it must not include a full source snapshot. A content digest can establish that bounded evidence was based on a particular input without disclosing the input.

## 4. Lifecycle events

An optional local audit stream uses one JSON object per line. Event names are stable and ordered:

1. `scan.started`
2. `boundary.resolved`
3. `inventory.completed`
4. `detection.completed`
5. `check.completed` (one per check)
6. `policy.evaluated`
7. `authorization.requested`
8. `authorization.decided`
9. `execution.started`
10. `execution.completed`
11. `cleanup.completed`
12. `report.written`
13. `scan.completed`

Each event contains:

- `event_version`;
- `event_name`;
- `sequence`;
- `report_id`;
- redacted timestamp or duration fields as appropriate;
- safe identifiers and outcome;
- an optional `error_code`.

The audit stream does not include raw environment values, credentials, unrestricted command output, or arbitrary project text. It is disabled by default in the first release unless the user selects an output path.

## 5. Logging levels

- **Default:** terminal summary and findings only.
- **Verbose:** bounded parser and execution diagnostics, still redacted.
- **Audit:** lifecycle JSONL plus the normal report.
- **Debug:** local developer diagnostics only; must display a warning that it can reveal more project metadata and must still apply secret redaction.

There is no remote logging level.

## 6. Evidence quality rules

Evidence should prefer, in order:

1. A precise project-relative file and line range.
2. A normalized metadata fact with a safe file reference.
3. An observed execution receipt.
4. A bounded absence statement describing the search performed.

Evidence must not quote a whole file by default. If a line excerpt is ever implemented, it must be bounded, escaped, and redacted. A suggestion is not evidence and must be stored separately.

## 7. Integrity and determinism

The implementation must:

- sort directory entries and check identifiers;
- normalize path separators in reports;
- normalize line endings before parsing text;
- avoid timestamps in score or static finding values;
- include timestamps only as metadata;
- use stable JSON serialization for snapshot tests;
- record if a file changes while being read;
- include a report digest only if it is computed after redaction and serialization.

The report ID may be unique per run, but it must not be used as a source of findings or policy decisions.

## 8. Operational metrics without telemetry

ColdStart may calculate local metrics for a report, such as:

- files considered and excluded;
- bytes read and parse failures;
- check counts by status;
- scan duration;
- execution duration and output truncation;
- cleanup success.

These metrics stay in the local report or terminal output. ColdStart must not transmit them. A future organization or hosted feature would require a separate consent and privacy design.

## 9. Audit review checklist

Before a release, reviewers must confirm:

- every check ID is documented and tested;
- unsupported results do not become passes through renderer defaults;
- terminal and JSON reports agree on status and counts;
- policy and exit code are derived from the same normalized findings;
- execution receipts identify permission and actual result;
- redaction tests cover output, evidence, audit events, and errors;
- no log path accidentally writes inside the inspected project;
- cleanup events occur for success, failure, timeout, cancellation, and internal error.
