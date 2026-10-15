# ColdStart Architecture

**Status:** Proposed for approval
**Version:** 0.1
**Implementation status:** Design only; no application source has been written

## 1. Architectural direction

ColdStart is proposed as a cross-platform command-line application with a local-first, standard-library-first core. The recommended implementation baseline is Python 3.12. The core should keep third-party runtime dependencies small and use ecosystem adapters so that adding support for a project type does not change the report contract or safety model.

The tool has two deliberately separate operating planes:

1. **Inspection plane:** deterministic, read-only analysis of project files.
2. **Verification plane:** explicitly authorized execution through a policy-controlled broker.

The inspection plane must work without Docker, a network connection, or project dependencies. The verification plane may require Docker and must report `not_verified` rather than silently weakening safety when its prerequisites are absent.

## 2. Logical components

| Component | Responsibility | Trust level |
| --- | --- | --- |
| CLI and invocation validator | Parse arguments, validate paths/options, render the permission plan | Trusted ColdStart code |
| Workspace boundary manager | Canonicalize root, enforce traversal limits, identify symlinks and exclusions | Trusted boundary code |
| File inventory | Enumerate eligible files and bounded metadata without executing them | Trusted, handles untrusted input |
| Project detector | Produce evidence-backed ecosystem candidates and confidence | Trusted, handles untrusted input |
| Adapter registry | Load built-in ecosystem adapters and their check definitions | Trusted code/configuration |
| Static check engine | Run pure checks over the inventory and parsed metadata | Trusted, handles untrusted input |
| Documentation consistency engine | Compare documented commands and claims with detected configuration | Trusted, handles untrusted input |
| Evidence and finding model | Normalize status, severity, evidence, recommendations, and provenance | Trusted internal model |
| Policy evaluator | Turn findings into a score and exit-code decision without changing evidence | Trusted configuration boundary |
| Execution broker | Require authorization, build a constrained plan, and invoke approved runners | High-risk trusted boundary |
| Docker runner | Perform containerized test or build verification with explicit limits | High-risk external process |
| Report renderer | Produce terminal output and versioned JSON without leaking secrets | Trusted output boundary |
| Audit recorder | Record lifecycle and execution receipt events with redaction | Trusted local record |

## 3. End-to-end data flow

### 3.1 Static scan

1. Validate the supplied path and resolve the scan boundary.
2. Load built-in defaults and an optional project policy without executing project files.
3. Enumerate files with limits, no external symlink traversal, and built-in generated-directory exclusions.
4. Parse only supported formats and bounded text content.
5. Detect ecosystems and select applicable adapters.
6. Run generic and adapter-specific checks in stable identifier order.
7. Normalize evidence and redact sensitive values.
8. Evaluate policy and optional score.
9. Render terminal output and, when requested, the JSON contract.

### 3.2 Authorized verification

1. Complete the static scan first.
2. Derive candidate commands only from supported metadata and documentation patterns.
3. Reject commands containing unsupported shell composition or unsafe path semantics.
4. Show the user an exact plan: command, working directory, image, network mode, timeout, resource limits, output limits, and expected side effects.
5. Require explicit approval for each execution class.
6. Create a temporary staging copy and a manifest of the approved input snapshot.
7. Execute through the Docker runner or return `not_verified` when the runner is unavailable.
8. Capture bounded output, exit status, duration, timeout, and cleanup result.
9. Compare the staged project manifest after execution and report unexpected changes.
10. Merge execution receipts into the report without replacing static evidence.

## 4. Trust boundaries

The project being inspected is untrusted input. Its README, manifests, scripts, Dockerfile, filenames, symlinks, and configuration can be deliberately malicious or merely malformed.

Trust boundaries are:

- **B1: User input to ColdStart.** Arguments and policy files are validated; no shell interpolation is used.
- **B2: Project files to parser.** Parsers are bounded, non-executing, and resilient to malformed content.
- **B3: Project-derived command to execution broker.** A command is data until selected, reviewed, and authorized; unsafe shell grammar is rejected.
- **B4: ColdStart to Docker daemon.** The Docker runner uses a temporary context, no host mounts or secrets, default network denial, resource limits, and explicit approval.
- **B5: Internal results to report.** Evidence is normalized and redacted before it leaves the process.

## 5. Adapter model

An adapter owns ecosystem knowledge, not security policy. Each adapter provides:

- detection signals and confidence rules;
- supported runtime files and version semantics;
- dependency and lockfile candidates;
- test/build command candidates as data;
- documentation consistency rules;
- static check definitions and suggested fixes;
- fixture identifiers for verification.

Adapters MUST NOT execute arbitrary project code, install dependencies, access the network, or write to the inspected project. The core execution broker remains the only path to verification.

The first full adapters are Python and Node.js. Generic checks and safe unsupported results remain active for all projects.

## 6. Storage and report flow

The first implementation is stateless by default. It writes a report only when the user requests an output path or the CI workflow captures stdout. Temporary staging material is created under a private temporary directory and removed after execution or failure.

An optional local audit JSONL file may be enabled later. It must never be required for a static scan and must use the same redaction policy as the primary report.

## 7. Recommended implementation baseline

| Decision | Recommendation | Reason |
| --- | --- | --- |
| Runtime | Python 3.12, pinned in `.python-version` | Accessible to the intended users and strong standard-library support |
| CLI | `argparse` or a small maintained CLI layer | Stable, scriptable, clear non-interactive behavior |
| Parsing | Standard-library parsers first (`tomllib`, `json`, bounded text) | Fewer dependencies and better offline behavior |
| Packaging | `pyproject.toml` with a committed lockfile | Reproducible installation of ColdStart itself |
| Testing | `pytest` in the development environment, wrapped by `make test` | Familiar test discovery and one mandated project command |
| Reports | Hand-built normalized model plus versioned JSON serialization | Stable contract without coupling checks to presentation |
| Execution | Docker CLI/API behind a single broker | Explicit isolation boundary and auditable controls |
| Config | Optional `.coldstart.toml` with schema version | Local policy without remote configuration |

The implementation must verify the exact tool versions available in the target development environment before dependency installation. Missing runtimes are a setup gap, not a reason to install globally.

## 8. Planned repository shape after approval

This is a target layout, not a request to create source files during the planning phase:

```text
ColdStart/
├── README.md
├── .python-version
├── pyproject.toml
├── uv.lock                         # or the approved equivalent lockfile
├── Dockerfile
├── Makefile
├── src/coldstart/
│   ├── cli/
│   ├── core/
│   ├── adapters/
│   ├── execution/
│   ├── reporting/
│   └── security/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── security/
│   └── fixtures/
└── docs/
```

The source layout is intentionally not present yet because implementation requires owner approval.

## 9. Architectural trade-offs

- **Python over a single native binary:** faster development and easier adapter work, at the cost of requiring a pinned Python runtime. The ColdStart build itself must address that reproducibility problem with a lockfile and Dockerfile.
- **Docker-backed verification over direct host execution:** slower and dependent on Docker, but significantly reduces accidental host mutation and makes the execution boundary explicit.
- **Static generic checks over ecosystem-wide completeness:** initial coverage is narrower but honest. Unsupported ecosystems receive useful generic findings and `not_verified` statuses rather than false passes.
- **Versioned JSON over an ad hoc output format:** more design work now, but enables CI, diffing, and future reporting interfaces without breaking consumers.

## 10. Architectural invariants

1. The static scan can run without project dependencies.
2. No component other than the execution broker can launch a project-derived process.
3. A report can represent uncertainty without converting it into a pass.
4. Reports do not require absolute paths or secrets to be useful.
5. Adding an adapter cannot bypass global resource or authorization controls.
