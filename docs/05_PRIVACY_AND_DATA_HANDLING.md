# ColdStart Privacy and Data Handling

**Status:** Proposed for approval
**Version:** 0.2
**Default posture:** Local processing, no telemetry, no source upload

## 1. Data ColdStart reads

During a P0 audit, ColdStart may read bounded metadata and text from the supplied repository boundary, including:

- filenames, directory structure, file sizes, timestamps where needed for consistency checks, and symlink metadata;
- Python project files such as `pyproject.toml`, requirements files, common lockfiles, `.python-version`, `setup.cfg`, and package metadata;
- README/setup documentation and test/build configuration;
- bounded source/configuration text for path, environment-variable, and secret-risk indicators;
- Dockerfile and `.dockerignore` metadata for discovery and applicability.

It does not need to import or execute the repository. It must not read outside the boundary unless the user explicitly configures an additional bounded path, which is outside P0.

## 2. Data kept in memory

ColdStart may hold:

- the bounded file inventory;
- parsed metadata;
- normalized findings and evidence;
- bounded, redacted diagnostic data;
- P1 execution receipts, if P1 is enabled.

It must not retain a full source tree in an in-memory cache after report generation. Large files are skipped or sampled under a documented limit; full source excerpts are not needed for normal reports.

## 3. Files ColdStart may write

P0 may write only:

- a report to stdout or an explicit output path;
- optional bounded diagnostics to an explicit path outside the inspected repository.

P0 does not create a repository staging copy or execution workspace. P1 execution may create temporary staging data only after authorization.

ColdStart must not write remediation changes, generated files, caches, lockfiles, virtual environments, or build outputs into the inspected repository. Writing a report inside the repository requires an explicit output path and a warning because it changes the scanned tree.

## 4. Report location and retention

- Default terminal report: stdout; diagnostics/errors: stderr.
- JSON report: stdout or the user-supplied `--output` path.
- Default P0 temporary data: none. P1 temporary data uses a private OS temp directory and is deleted after the run.
- No automatic project copy, cloud retention, or report upload.
- The user owns any explicitly saved report and is responsible for its retention and access control.
- ColdStart should include a report note that a saved report may contain repository-relative filenames and sanitized metadata.

## 5. Data leaving the local machine

No data leaves the machine during the P0 audit. There is no telemetry, analytics, remote model call, account service, update check, or dependency download during normal audit operation. P1 network-enabled verification is outside the P0 default and requires separate explicit approval; when implemented, the report must record that network mode and limitation.

## 6. Logging restrictions

- Normal logs are the terminal report and bounded errors only.
- Do not log full source files, environment values, command output, tokens, private keys, or host usernames.
- Use project-relative paths and normalized labels.
- Escape terminal control characters.
- Redact secret-shaped values before logs, evidence, reports, and optional audit streams.
- If redaction is uncertain, omit the value and report only the type/location of the risk.

## 7. Secret detection and redaction

Secret checks are risk indicators, not proof of a live credential. ColdStart may identify a likely key/token shape or sensitive filename, but it must not print the candidate value. Report:

- check ID and severity;
- relative path and line range where safe;
- redacted description such as “token-shaped value detected”;
- remediation such as removing the value, rotating it, and adding a safe example.

Never include actual passwords, access tokens, private keys, cookies, or environment values in documentation examples or generated reports.

## 8. Temporary files and permissions

Temporary directories use the operating system's secure temporary-directory API and restrictive permissions. P1 staging copies must record ownership and a manifest. Cleanup runs on success, failure, cancellation, timeout, and process interruption where the platform allows. A cleanup failure is reported and never hidden.

## 9. File permission requirements

ColdStart needs read access to the selected repository and write access only to an explicitly selected report/diagnostic path or private temporary directory. It must not request administrator/root privileges. If a required file is unreadable, the report says which check lost evidence.

## 10. Failure handling

When a report cannot be written, ColdStart attempts a safe terminal message and returns the output error code. When a temporary cleanup fails, it reports the path only if it is safe to do so and gives the user a cleanup instruction. It never retries a project command automatically.

## 11. Privacy acceptance criteria

- A network-disabled P0 audit completes without external calls.
- A fixture containing fake credentials produces no credential value in terminal, JSON, error, or diagnostic output.
- A static audit leaves the repository file manifest unchanged.
- Output paths and report permissions are documented.
- Saved reports contain relative paths by default and no host username/home path.
- The documentation contains no real secret material.
