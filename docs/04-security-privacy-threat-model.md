# ColdStart Security, Privacy, and Threat Model

**Status:** Proposed for approval
**Version:** 0.1
**Security posture:** Treat every inspected project as untrusted input

## 1. Security objectives

ColdStart must protect the developer's computer, project contents, credentials, and the integrity of its own findings while still providing useful evidence.

The security objectives are:

1. A default scan cannot execute project code or modify the inspected project.
2. A user understands and authorizes any operation that could execute code or access a network.
3. Project content cannot cause command injection, path escape, unbounded resource use, or report corruption.
4. Secrets are not copied into reports, logs, Docker build contexts, or test environments by default.
5. A failed or interrupted verification does not leave unbounded child processes or temporary resources.
6. Security restrictions produce an honest `not_verified` or `error` result rather than an optimistic pass.

## 2. Assets

| Asset | Impact if exposed or damaged |
| --- | --- |
| Source code and proprietary project files | Confidentiality and intellectual-property loss |
| `.env`, credentials, tokens, SSH material, cloud configuration | Account compromise or data loss |
| Host filesystem and processes | Unauthorized modification or code execution |
| Docker daemon and socket | Container escape or host compromise if misused |
| Report evidence and audit records | Leakage, misleading review, or loss of accountability |
| ColdStart policy and exit result | CI bypass or false confidence |
| Temporary staging directory | Secret persistence or cleanup failure |

## 3. Actors and assumptions

- **Developer:** trusted to choose the project and explicitly authorize described operations.
- **Project author:** may be benign, careless, or malicious; project content is untrusted.
- **CI runner:** may have fewer interactive controls and must use an explicit non-interactive policy.
- **Docker daemon:** an external privileged service whose security is outside ColdStart's complete control.
- **Local operating system:** provides file and process permissions but may differ by platform.

ColdStart does not assume that a README, package script, Dockerfile, filename, or environment variable is safe merely because it is present in the project.

## 4. Threats and controls

| ID | Threat | Control | Residual risk |
| --- | --- | --- | --- |
| T-001 | README or manifest attempts command injection | Parse command candidates as data; reject shell operators, substitutions, pipes, redirection, and chaining in v1 | A user can still manually approve a command outside the safe grammar in a later feature |
| T-002 | Symlink escapes scan root | Do not follow external symlinks by default; resolve and verify paths before reading | Files can change during a scan; report consistency warnings |
| T-003 | Malicious or huge file causes resource exhaustion | File count, file size, total-byte, recursion, output, and time limits; skip binary/unknown data | Limits may prevent analysis of legitimate large repositories |
| T-004 | Project mutates itself during execution | Execute from a staging copy; snapshot before and after; never write to the original project | Docker or host behavior can still mutate external services if the user approves network access |
| T-005 | Docker build reads secrets from context | Use a sanitized temporary context, built-in secret exclusions, no host mounts, and a preflight warning | A Dockerfile may intentionally read files that are not recognizable as secrets |
| T-006 | Docker build reaches the network | Default `network=none`; require separate approval for network-enabled verification | Approved network access can contact arbitrary endpoints from the build |
| T-007 | Test process forks or consumes excessive resources | Run in a container with timeout, CPU/memory/process/output limits; kill the process group/container on timeout | Container isolation depends on Docker and host configuration |
| T-008 | Environment secrets leak to tests | Pass only an explicit minimal environment allowlist; do not inherit the host environment wholesale | A user-approved project may require a secret; v1 should classify it as unsupported rather than pass it silently |
| T-009 | Report includes credentials or host identity | Redact secret-shaped values, omit environment values, use relative paths, and suppress usernames/home paths | Heuristic redaction cannot prove that every secret pattern is found |
| T-010 | Malformed file crashes ColdStart | Bounded parsers, exception isolation per check, and an `error` result with evidence | A core bug may still terminate the process; crash tests are required |
| T-011 | CI bypasses an important check | Versioned policy, stable exit codes, explicit unknown handling, and tests for fail-open behavior | A poorly written local policy can intentionally weaken its own gate |
| T-012 | Docker socket is exposed to the project | Never mount the socket or host filesystem into verification containers; document daemon privilege assumptions | The Docker daemon itself may be privileged and compromised independently |
| T-013 | Time-of-check/time-of-use race | Record file metadata/hash where possible and stage before execution; warn if the source changes | A hostile local process can race the scan |
| T-014 | Terminal control sequences corrupt the report | Escape or strip control characters from project-provided text before rendering | Terminal implementations differ; renderer tests are required |

## 5. Authorization protocol

### Static scan

No authorization prompt is needed because the default static operation is read-only within the declared boundary. The CLI must still display the boundary and exclusions.

### Test verification

Before execution, ColdStart must display:

- the exact command and argument vector;
- the staged working directory;
- the selected container image and runtime;
- whether the original project will be copied or mounted;
- network mode;
- environment variables passed by name, never secret values;
- timeout, CPU, memory, process, disk, and output limits;
- the reason the command was selected;
- possible side effects and cleanup behavior.

Approval must be explicit. Closing the prompt, an empty response, or an unknown response means denial.

### Docker build

Docker build is a separate high-risk class. It requires its own approval even if test verification was approved. The user must be told that a Dockerfile can execute arbitrary build instructions and that a Docker daemon is a privileged service.

In non-interactive mode, execution is denied unless the user supplies an explicit execution policy and an `allow_execution` setting. A checked-in policy must not silently enable host execution.

## 6. Command safety policy for v1

V1 may execute only a single executable plus arguments represented as an argument vector. The candidate is rejected when it contains shell syntax such as `|`, `>`, `<`, `&&`, `||`, `;`, backticks, `$()`, variable expansion, backgrounding, or command substitution. A command with an unknown executable, an absolute path outside the staged workspace, or an unbounded wrapper is `not_verified`.

The broker must use a process API without shell interpolation. The README is a source of evidence and candidate commands, never an authority to execute arbitrary text.

## 7. Filesystem and staging policy

- The original project is read-only during all ColdStart operations.
- Symlinks are listed as evidence and not followed outside the root by default.
- Temporary directories use restrictive permissions and are removed after use.
- The staging copy includes only the declared scan boundary and safe, non-secret context files needed for the approved action.
- `.git`, `.env*`, credential stores, private keys, and host configuration are excluded from Docker context by default; exclusions are reported so a user can understand a failed build.
- Reports use project-relative paths. Absolute paths appear only in an explicitly requested local diagnostic mode.

## 8. Privacy rules

ColdStart is local-only in the first release:

- no analytics, telemetry, remote callback, or automatic upload;
- no dependency download during static scans;
- no source content in reports unless the user explicitly requests a diagnostic excerpt;
- no environment values in reports or logs;
- no absolute path, username, or home-directory disclosure by default;
- output truncation with a digest when command output exceeds the configured limit.

If a future feature sends reports remotely, it requires a separate product and privacy review and must not be inferred from this specification.

## 9. Security acceptance gates

Before release, the implementation must pass:

- command-injection and shell-metacharacter tests;
- path traversal and symlink tests on Windows and Unix-like systems;
- secret-redaction tests using representative tokens and `.env` files;
- output-control and terminal-escape tests;
- timeout, process-tree cleanup, and resource-limit tests;
- Docker-context exclusion tests;
- non-interactive execution-denial tests;
- malformed-input and fuzz/property tests for filenames, manifests, and reports;
- dependency and container image review recorded in the release evidence.

## 10. Residual-risk disclosure

No local verifier can guarantee that an arbitrary Dockerfile, build tool, or operating system is safe. ColdStart reduces risk through explicit authorization and isolation but must clearly state that Docker-backed verification still invokes project-defined build instructions. A user who grants network or host execution permission accepts risks outside ColdStart's static guarantees.
