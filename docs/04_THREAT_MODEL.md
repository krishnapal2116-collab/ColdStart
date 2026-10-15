# ColdStart Threat Model

**Status:** Proposed for approval
**Version:** 0.2
**Security principle:** Treat all repository content as untrusted input.

## 1. Assets being protected

- Developer workstation filesystem and processes.
- Inspected source code, private project files, and intellectual property.
- Environment variables, credentials, tokens, private keys, and local configuration.
- Docker daemon, image cache, build context, and temporary staging directories.
- Report integrity and the user's trust in a verification result.
- ColdStart's policy, exit status, and check catalog.

## 2. Trust boundaries and data flow

```text
User/CI arguments
      ↓ validation boundary
ColdStart static engine ← untrusted repository files
      ↓ report redaction boundary
Terminal/JSON output

Explicit user approval
      ↓ execution boundary
Staged repository → constrained runner → Docker daemon/process receipt
```

The repository may contain a malicious README, filename, manifest, package script, Dockerfile, symlink, or malformed file. It is not a trusted instruction source.

## 3. Attacker capabilities

Assume an attacker can:

- commit arbitrary text, filenames, symlinks, and configuration to the repository;
- attempt to influence a parser or documented command;
- include secret-shaped strings designed to evade or trigger redaction;
- create deeply nested, huge, malformed, or rapidly changing files;
- provide a Dockerfile that executes arbitrary build instructions;
- rely on differences between Windows and Unix path/shell behavior;
- exploit a user's desire for a convenient “run the tests” action.

The attacker does not automatically control the user's explicit approval decision, Docker daemon configuration, or operating-system permissions, but ColdStart must not assume those controls are perfect.

## 4. Threat rating

Likelihood and impact use `Low`, `Medium`, or `High`. Severity is `Blocker`, `High`, `Medium`, or `Low`.

| ID | Threat scenario | Likelihood | Impact | Severity | Mitigation | Residual risk |
| --- | --- | --- | --- | --- | --- | --- |
| T-001 | Malicious repository causes a README/manifest command to run during static audit | Medium | High | Blocker | P0 has no project execution; P1 requires plan and approval | A user can approve a risky P1 action |
| T-002 | Path traversal escapes the supplied repository boundary | Medium | High | Blocker | Canonicalize paths, reject `..` escapes, use relative evidence paths, test Windows/Unix semantics | TOCTOU races require staging and manifest checks |
| T-003 | Symlink traversal reads outside the repository | Medium | High | High | Do not follow external symlinks by default; record link as evidence; verify resolved path | A source process can race a link during inspection |
| T-004 | Malicious filename breaks terminal output or report parsing | Medium | Medium | High | Escape control characters, normalize paths, bound names, JSON-encode safely | Terminal behavior varies by host |
| T-005 | Huge or malformed file exhausts memory/CPU | High | Medium | High | File size/count/depth/byte/time limits, bounded reads, parser exception isolation | Legitimate large repositories may need reviewed limits |
| T-006 | Parser denial of service via nested or pathological metadata | Medium | Medium | High | Use bounded standard-library parsing, maximum nesting/bytes, time budget | Parser implementation bugs can remain |
| T-007 | Shell injection through a documented command | Medium | High | Blocker | P0 never executes; P1 uses structured argv, rejects shell operators, never uses `shell=True` | A future advanced shell mode would need a new review |
| T-008 | Command argument injection through a path or option | Medium | High | High | Construct argv elements separately, allowlist working directory and executable candidates | Tool-specific argument semantics remain complex |
| T-009 | Sensitive data appears in logs or reports | Medium | High | High | Relative paths, no inherited env, redaction, bounded evidence, secret fixtures | Heuristic redaction cannot prove all secrets found |
| T-010 | Secret enters a Docker build context | Medium | High | High | Sanitized staging context, built-in `.env`/key exclusions, preflight review, no host mounts | A project-defined secret format may be unrecognized |
| T-011 | Unsafe temporary files remain or are predictable | Medium | Medium | High | Private OS temp directory, restrictive permissions, ownership manifest, cleanup on every exit path | Cleanup can fail due to external process behavior |
| T-012 | Verification reaches the network unexpectedly | Medium | High | High | Network disabled by default, explicit mode in plan, integration test, no host fallback | Approved network access can contact arbitrary services |
| T-013 | Docker is treated as a complete security boundary | Medium | High | High | Warn that Docker daemon is privileged; no socket/host mounts/privileged mode; prefer rootless | Host daemon/container runtime vulnerabilities remain |
| T-014 | Permission or privilege mistake grants excess host access | Low/Medium | High | High | Least-privilege process, no elevated execution, explicit directory and env allowlist | User-run Docker daemon may have broad privilege |
| T-015 | Dependency or supply-chain risk compromises ColdStart | Medium | High | High | Minimal runtime dependencies, pinned hashes, lockfile, review updates, clean build | Third-party packages can still contain defects |
| T-016 | Repository changes during scan create false evidence | Medium | Medium | Medium | Snapshot metadata/digests, stage before P1, warn on changes, rerun recommendation | A hostile local process can race reads |
| T-017 | Policy or renderer hides unknowns as passes | Medium | High | Blocker | Normalized status model, contract tests, explicit counts, fail-closed policy parsing | A user can choose a permissive policy intentionally |
| T-018 | Child process ignores timeout or forks | Medium | High | High | Process-group/container termination, process/output limits, cleanup receipt | OS/container behavior differs by platform |

## 5. Required subprocess controls

When P1 execution exists:

- pass an argument list, never a shell command string;
- set an explicit staged working directory;
- pass a minimal environment allowlist, not the host environment;
- set a timeout and terminate the process group/container on expiry;
- cap stdout/stderr bytes and record truncation plus a digest;
- record the observed exit code, signal/termination reason, and cleanup status;
- default to no network;
- do not mount the host filesystem, Docker socket, credentials, or arbitrary project parent directories;
- run with the least privilege available and make privilege limitations visible.

## 6. Docker boundary limitations

Docker can isolate files and processes better than direct host execution, but it is not a complete security guarantee. The Docker daemon may run with host-level privilege; kernel vulnerabilities, daemon configuration, image supply chain, build cache, network approval, and resource limits remain host risks. ColdStart must display this limitation before Docker verification and must never describe a Docker build as proof of universal safety or reproducibility.

## 7. Security verification tests

The implementation must include tests for:

- malicious README/package metadata with shell operators;
- argv injection and absolute executable paths;
- `..` traversal and platform-specific path forms;
- external and internal symlinks;
- malicious/control-character filenames;
- huge, malformed, deeply nested, and binary files;
- parser exception isolation;
- default no-subprocess static audit;
- secret-shaped values, `.env`, private-key text, and report/log redaction;
- temporary-file permissions and cleanup after failure/cancellation;
- network-disabled verification and Docker-unavailable behavior;
- timeout, output truncation, process-tree cleanup, and nonzero exit status;
- policy attempts to hide `not_verified` or `skipped` as pass;
- locked dependency/build reproducibility for ColdStart itself.

## 8. Residual-risk policy

ColdStart reports remaining limitations instead of hiding them. If a capability is missing, permission is denied, Docker is unavailable, a check is not applicable, or coverage is incomplete, the result says so. The product cannot guarantee every external environment, service, dependency mirror, operating-system behavior, or Docker daemon state.
