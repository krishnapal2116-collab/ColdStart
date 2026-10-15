# ColdStart Failure Modes and Resilience

**Status:** Proposed for approval
**Version:** 0.1

## 1. Resilience goals

ColdStart should fail safely, explain what happened, preserve evidence already collected, and avoid leaving processes or temporary resources behind. A failure of one adapter or check should not erase results from independent checks.

## 2. Scan state model

The scan lifecycle is:

```text
created → boundary_validated → inventorying → detecting → checking → policy_evaluated → reporting → completed
                                      └────────────── error / cancelled / limit_exceeded ──────────────┘
```

Execution adds a separate lifecycle after `policy_evaluated`:

```text
proposed → awaiting_authorization → authorized → staging → running → collecting → cleaning → receipt_recorded
             ├── denied
             ├── unavailable
             └── invalid
```

The static result is retained when execution is denied or unavailable.

## 3. Failure handling matrix

| Failure | Detection | Result | Recovery |
| --- | --- | --- | --- |
| Project path does not exist | Boundary validation | Exit `2`; no report unless an error report is requested | Correct the path |
| Project path is a file | Boundary validation | Exit `2` | Supply a directory |
| Root cannot be read | Boundary validation | Exit `2` or `not_verified` with path evidence | Fix permission or choose another path |
| One file cannot be read | Inventory exception | Continue other files; add bounded `not_verified` or `error` finding | Review permission or file type |
| File is too large | Limit check | Exclude and report `not_verified` | Increase an explicit limit or split the project |
| File count/bytes/time limit reached | Resource guard | Stop inventory safely; report incomplete coverage and exit `3` or policy failure | Narrow scope or raise a reviewed limit |
| Malformed manifest | Parser exception | Adapter check `error`; generic checks continue | Fix manifest syntax |
| Unknown ecosystem | Detection | Generic checks; adapter-specific checks `not_verified` | Add a supported adapter or review manually |
| Conflicting runtime declarations | Detector comparison | `failed` or `warning` with both evidence sources | Align and pin versions |
| README command cannot be parsed safely | Command parser | Candidate `not_verified`; never execute | Document a simple command or approve a future safe mechanism |
| User denies tests | Authorization | Execution `not_verified`; static report remains valid | Run later with explicit permission |
| Docker is not installed or daemon unavailable | Capability preflight | Execution `not_verified`; no host fallback | Install/start Docker or review manually |
| Docker build requires network but network is denied | Build result | Actual build failure with network policy evidence | Review Dockerfile or separately approve network |
| Test process times out | Watchdog | Execution `error`/`failed` with timeout reason; cleanup required | Fix test hang or adjust reviewed limit |
| Output exceeds capture limit | Output guard | Execution result preserved; output marked truncated with digest | Inspect locally or raise limit deliberately |
| Container cleanup fails | Cleanup check | Execution `error` and warning about residual resource | Display cleanup command or require manual cleanup |
| Source changes during scan | Manifest comparison | Warning or `not_verified` for affected results | Re-run against a stable checkout |
| Report output path is unwritable | Report writer | Terminal fallback if safe; nonzero exit if JSON was required | Choose a writable output path |
| Internal exception | Top-level handler | Sanitized error report and exit `4`; no false pass | Capture diagnostic ID and fix the defect |
| User cancels after authorization | Cancellation handler | Cancelled execution, cleanup, exit `3` | Re-run when ready |

## 4. Retry policy

ColdStart must not automatically retry project commands or Docker builds. Retrying code can repeat side effects and obscure flakiness. A user may invoke a new run after reviewing the first receipt.

Safe internal retries are limited to non-side-effecting operations such as reading stable metadata, and only if the retry is bounded and recorded. A repeated read that gives different content becomes a consistency warning.

## 5. Cancellation and cleanup

Cancellation must:

1. stop accepting new work;
2. signal the child process or container;
3. wait for a bounded grace period;
4. force terminate if required by the runner;
5. remove temporary staging and known resources;
6. write a cleanup result;
7. report that verification was incomplete.

Cleanup errors must never be hidden to make a run look successful.

## 6. Error message requirements

An error shown to a user must contain:

- what ColdStart was trying to do;
- whether the original project was changed;
- whether execution occurred;
- the safe reason for failure;
- the next practical action;
- a stable error code where a caller may automate on it.

It must not contain secret environment values, raw tokens, or an unbounded stack trace in normal output.

## 7. Reliability targets

The implementation should target:

- no false `passed` result after a runner or parser exception;
- no orphaned verification process in normal timeout/cancellation tests;
- a useful partial report for isolated file and adapter failures;
- deterministic static findings across repeated runs on an unchanged fixture;
- bounded memory and disk use under hostile fixture tests.
