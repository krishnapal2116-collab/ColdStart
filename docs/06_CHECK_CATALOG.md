# ColdStart P0 Check Catalog

**Status:** Proposed for approval
**Version:** 0.2
**Scope:** Complete P0 static audit catalog for the first Python-focused release

## 1. Common rule contract

Every check below is deterministic, non-executing, and registered with a stable ID. A rule may inspect metadata and bounded text but must not import the repository, install a package, run a shell, contact a network service, or modify the repository.

### Status semantics

- `passed`: applicable evidence satisfies the rule.
- `failed`: applicable evidence shows a defined reproducibility risk or missing required evidence.
- `not_applicable`: the detected project type/package manager/policy does not make the rule meaningful.
- `skipped`: the user policy intentionally excludes the rule; the report gives the reason.
- `not_verified`: the rule could not be evaluated because required evidence/capability was unavailable or the scan was incomplete.
- `error`: ColdStart itself could not evaluate the rule reliably.

`not_applicable`, `skipped`, and `not_verified` are never counted as `passed`.

### Common evidence requirements

Evidence uses project-relative paths, bounded details, optional line ranges, and redaction. Absence evidence describes where ColdStart looked. A risk indicator is labeled as an indicator, not proof of a defect.

## 2. Check index

| ID | Name | Default severity | Primary type |
| --- | --- | --- | --- |
| CS-PROJECT-001 | Project metadata discovery | warning | Generic/Python |
| CS-PROJECT-002 | Supported project type detection | warning | Generic/Python |
| CS-DEPS-001 | Dependency declaration discovery | error | Python |
| CS-DEPS-002 | Applicable lockfile presence | error | Python |
| CS-RUNTIME-001 | Runtime version declaration | error | Python |
| CS-DOCS-001 | Setup documentation presence | warning | Generic/Python |
| CS-DOCS-002 | Test command documentation | error | Generic/Python |
| CS-CONFIG-001 | Configuration example discovery | warning | Generic/Python |
| CS-CONFIG-002 | Environment-variable documentation | warning | Generic/Python |
| CS-PORT-001 | Developer-specific absolute paths | warning | Generic/Python |
| CS-SEC-001 | Potential secret exposure indicator | blocking/error | Generic/Python |
| CS-BUILD-001 | Container build configuration discovery | info | Generic/Python |
| CS-PATH-001 | Repository-contained path validation | error | Generic/Python |

## 3. CS-PROJECT-001 — Project metadata discovery

1. **Purpose:** Establish whether the repository contains recognizable project metadata or documentation from which other checks can begin.
2. **Severity:** `warning` when no useful metadata is found; `info` when discovery succeeds.
3. **Supported types:** Generic and Python.
4. **Preconditions:** A readable repository boundary and a bounded inventory.
5. **Inspected data:** Root and bounded subdirectory names; `pyproject.toml`, requirements files, `.python-version`, `README*`, test/config files, Docker files, and common Python packaging metadata.
6. **Detection algorithm:** Sort paths; classify recognized files by filename and parse only supported formats; record ignored/generated directories and unreadable paths; never execute content.
7. **Expected result:** `passed` if at least one recognized project/documentation signal is present; `not_verified` if inventory coverage is incomplete; `failed` if the root is readable but contains no recognized project signal.
8. **Positive test cases:** Python project with `pyproject.toml`; project with only a README and source directory.
9. **Negative test cases:** Empty directory; directory containing only unrelated binary files.
10. **Edge cases:** Monorepo with multiple metadata roots; generated `build/` tree; unreadable file; case variation on Windows.
11. **False-positive handling:** A single generic README is evidence of documentation, not proof of a runnable project; status remains limited to discovery.
12. **Evidence format:** Recognized relative paths, file categories, inventory limits, and any omitted path reason.
13. **Remediation:** Add a clear project metadata file and a setup README if the repository is intended to be runnable.
14. **Requirements:** FR-003, FR-004, FR-006, FR-008, NFR-005.
15. **Known limitations:** Discovery cannot understand every custom build system or prove that metadata is complete.

## 4. CS-PROJECT-002 — Supported project type detection

1. **Purpose:** Identify Python, unknown, or mixed project candidates and expose confidence/evidence.
2. **Severity:** `warning` when no supported type is detected; `info` for a clear candidate; `warning` for ambiguity.
3. **Supported types:** Python first; generic fallback for all repositories.
4. **Preconditions:** Completed or partial metadata discovery.
5. **Inspected data:** `pyproject.toml`, `setup.py`/`setup.cfg` as text only, requirements/lockfiles, Python source suffixes, README claims, and configured project roots.
6. **Detection algorithm:** Assign deterministic weights to recognized signals; sort ties by stable signal ID; emit all candidates above the documented threshold; never silently discard mixed candidates.
7. **Expected result:** `passed` for one high-confidence Python candidate; `not_applicable` for an intentionally generic-only policy; `not_verified` for insufficient/partial inventory; `failed` only when a configured required type is contradicted.
8. **Positive test cases:** Valid `pyproject.toml`; Python package with `src/` layout.
9. **Negative test cases:** JavaScript-only project; empty repository; conflicting Python roots.
10. **Edge cases:** Monorepo; Python source without metadata; README says Python but no Python files.
11. **False-positive handling:** A `.py` file alone is a candidate signal, not proof of a package or supported workflow.
12. **Evidence format:** Candidate ID, confidence class (`high`, `medium`, `low`), signal paths, and ambiguity reason.
13. **Remediation:** Add unambiguous metadata and document the supported entry point.
14. **Requirements:** FR-003, FR-004, FR-016, NFR-001, NFR-012.
15. **Known limitations:** Confidence is a deterministic classification, not a probability or proof of correctness.

## 5. CS-DEPS-001 — Dependency declaration discovery

1. **Purpose:** Determine whether the applicable Python dependency declarations are present and discoverable.
2. **Severity:** `error` when a recognized Python project has imports/package metadata but no usable declaration; `warning` when evidence is incomplete.
3. **Supported types:** Python.
4. **Preconditions:** Python candidate with readable relevant files.
5. **Inspected data:** `pyproject.toml` dependency tables, `requirements*.txt`, supported setup metadata, and bounded Python import statements for indicators only.
6. **Detection algorithm:** Parse declarations; normalize package names; compare only high-confidence top-level imports against declarations using a maintained standard-library and local-module exclusion list; mark dynamic/optional imports as uncertain rather than failed.
7. **Expected result:** `passed` when declarations exist and no high-confidence undeclared import is found; `failed` when no declaration exists for a packaged Python project or a high-confidence dependency is missing; `not_verified` on incomplete parsing.
8. **Positive test cases:** `pyproject.toml` with dependencies; requirements file matching a non-stdlib import.
9. **Negative test cases:** Python package with third-party import and no dependency declaration.
10. **Edge cases:** Optional imports; extras; dynamic imports; vendored code; namespace packages; local modules sharing a package name.
11. **False-positive handling:** Do not fail on a string that resembles an import, a standard-library module, or a clearly local module; report uncertain imports separately.
12. **Evidence format:** Declaration path/line, normalized package name, import path only when safe, and parser coverage.
13. **Remediation:** Declare runtime and development dependencies in the project’s supported metadata and document the install command.
14. **Requirements:** FR-005, FR-008, FR-016, NFR-001, NFR-005.
15. **Known limitations:** Static import mapping cannot resolve every dynamic or generated dependency.

## 6. CS-DEPS-002 — Applicable lockfile presence

1. **Purpose:** Check for a lockfile only when the detected Python package manager or project policy makes one applicable.
2. **Severity:** `error` when applicable and absent; `warning` when manager evidence conflicts; `info` when not applicable.
3. **Supported types:** Python package managers recognized by the adapter and an explicit project policy.
4. **Preconditions:** A dependency declaration or package-manager signal is present.
5. **Inspected data:** `pyproject.toml` build/dependency metadata, requirements/constraint files, known lockfile names, README setup commands, and `.coldstart.toml` policy.
6. **Detection algorithm:** Identify the declared manager; consult the adapter’s applicability table; consider a lockfile present only when its format matches the manager; treat a fully pinned requirements file as a policy-specific alternative only when documented.
7. **Expected result:** `passed` when an applicable matching lockfile/pinned policy is present; `failed` when applicable and absent; `not_applicable` when the project’s supported workflow does not require one; `not_verified` when manager evidence conflicts or is incomplete.
8. **Positive test cases:** Python project with matching lockfile; project policy explicitly documents hashed pinned requirements instead.
9. **Negative test cases:** Poetry/uv-style metadata with no matching lockfile; unrelated `package-lock.json` in a Python project.
10. **Edge cases:** Multiple competing lockfiles; stale lockfile; monorepo with per-package locks; generated lockfile ignored by Git.
11. **False-positive handling:** Never treat absence as universal failure; never accept an unrelated ecosystem lockfile as Python evidence.
12. **Evidence format:** Manager/applicability reason, candidate lockfiles, selected lockfile, and conflict details.
13. **Remediation:** Generate and commit the lockfile used by the documented setup workflow, or document the approved fully pinned alternative.
14. **Requirements:** FR-005, FR-008, FR-016, NFR-001, NFR-009.
15. **Known limitations:** ColdStart cannot prove a lockfile is semantically fresh without running the package manager.

## 7. CS-RUNTIME-001 — Runtime version declaration

1. **Purpose:** Find and evaluate the Python runtime declaration used by the project.
2. **Severity:** `error` when a Python project has no runtime declaration; `warning` for a broad range; `info` for an exact supported pin.
3. **Supported types:** Python.
4. **Preconditions:** Python candidate.
5. **Inspected data:** `.python-version`, `pyproject.toml` requires-python, runtime/toolchain files, Dockerfile base image, README setup text, and CI metadata if present.
6. **Detection algorithm:** Parse all declarations; normalize versions/ranges; report conflicts; classify exact pin, bounded range, broad range, inferred, or absent.
7. **Expected result:** `passed` for one consistent exact or policy-approved bounded declaration; `failed` for absent/conflicting declarations under the default policy; `not_verified` for malformed or incomplete evidence.
8. **Positive test cases:** `.python-version` plus matching `requires-python`; exact Docker base image.
9. **Negative test cases:** README says Python 3.11 while metadata says 3.12; no runtime evidence.
10. **Edge cases:** Multiple subprojects; architecture-specific Docker tags; version range valid but not reproducible.
11. **False-positive handling:** A README sentence is evidence of a claim, not a pin; report it separately from machine-readable declarations.
12. **Evidence format:** File/line, normalized version or range, conflict list, and pin classification.
13. **Remediation:** Pin the supported Python runtime and align README, packaging, CI, and Docker declarations.
14. **Requirements:** FR-005, FR-008, FR-016, NFR-001, NFR-007, NFR-011.
15. **Known limitations:** A declaration cannot prove the interpreter binary or native dependencies on a host.

## 8. CS-DOCS-001 — Setup documentation presence

1. **Purpose:** Determine whether another developer can find instructions for installing and starting the project.
2. **Severity:** `warning` when absent or incomplete; `info` when a usable entry point exists.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Readable repository boundary.
5. **Inspected data:** README files, `docs/`, setup scripts as text, packaging metadata, and declared environment/configuration files.
6. **Detection algorithm:** Locate a primary README; detect headings or command blocks for prerequisites, installation, configuration, and run/start; compare referenced files/commands with discovered paths without executing them.
7. **Expected result:** `passed` when a primary setup path includes prerequisites/install/config/run guidance; `failed` when the repository is intended to run but no setup path exists; `not_verified` when documentation is unreadable or references cannot be resolved.
8. **Positive test cases:** README with Python version, install, env example, and run command.
9. **Negative test cases:** README contains only a project description; referenced script is absent.
10. **Edge cases:** Documentation in a nested directory; multiple READMEs; non-English headings; shell commands with unsupported composition.
11. **False-positive handling:** A README's existence alone is insufficient; headings and referenced paths must support the finding.
12. **Evidence format:** Documentation path/line and missing section/file references.
13. **Remediation:** Add a short clean-checkout setup sequence with prerequisites, installation, configuration, run, and troubleshooting.
14. **Requirements:** FR-005, FR-008, FR-017, NFR-008.
15. **Known limitations:** Natural-language completeness is bounded pattern analysis, not human comprehension.

## 9. CS-DOCS-002 — Test command documentation

1. **Purpose:** Determine whether a reviewer can identify the intended test command and whether its declaration is consistent with project metadata.
2. **Severity:** `error` when no test command is documented for a test-bearing project; `warning` for a contradiction; `info` for a clear command.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Repository discovery and setup-documentation scan.
5. **Inspected data:** README/docs command blocks, `pyproject.toml` scripts/tool configuration, `Makefile`, CI metadata, and test directories.
6. **Detection algorithm:** Extract simple single-command candidates; detect test files/config; compare command names with configured scripts and test roots; reject shell pipelines as executable candidates but retain them as documentation evidence.
7. **Expected result:** `passed` when a clear command and test evidence agree; `failed` when test files exist but no usable command is documented or a command references a missing tool; `not_verified` when parsing is incomplete.
8. **Positive test cases:** README `python -m pytest` with test files and a dev dependency declaration.
9. **Negative test cases:** README says `pytest` but no pytest declaration or test files exist.
10. **Edge cases:** Multiple test commands; platform-specific commands; command with environment prefix; shell chain.
11. **False-positive handling:** Do not execute or claim the command works; classify documentation consistency only.
12. **Evidence format:** Command text as redacted bounded data, source path/line, test metadata, and contradiction reason.
13. **Remediation:** Document one portable test command and declare its test dependency/configuration.
14. **Requirements:** FR-005, FR-008, FR-017, NFR-001.
15. **Known limitations:** Only supported simple command forms can be compared; actual test success is P1.

## 10. CS-CONFIG-001 — Configuration example discovery

1. **Purpose:** Find a safe example of required configuration without requiring real credentials.
2. **Severity:** `warning` when configuration is referenced but no example exists; `info` when an example is present.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Documentation or source indicators of configuration.
5. **Inspected data:** `.env.example`, `.env.sample`, config templates, README references, and known configuration filenames; never report values from `.env` as evidence.
6. **Detection algorithm:** Identify configuration references and compare them with safe template files; check that candidate templates contain placeholders rather than credential-shaped values.
7. **Expected result:** `passed` when required configuration has a safe example; `failed` when documentation/source clearly requires configuration but no safe example exists; `not_applicable` when no configuration indicator is found.
8. **Positive test cases:** README documents `DATABASE_URL` and `.env.example` lists a placeholder.
9. **Negative test cases:** README requires `.env` but only a real `.env` exists; no example.
10. **Edge cases:** Template in `config/`; values encoded in JSON/YAML; example intentionally empty.
11. **False-positive handling:** Presence of `.env` alone is never a pass; do not quote its values.
12. **Evidence format:** Template path, variable/key names only, and source reference.
13. **Remediation:** Add a sanitized example with placeholders and explain how values are supplied securely.
14. **Requirements:** FR-005, FR-008, NFR-003.
15. **Known limitations:** ColdStart cannot infer every runtime configuration mechanism.

## 11. CS-CONFIG-002 — Environment-variable documentation

1. **Purpose:** Identify environment variables that appear required but are not explained to a new developer.
2. **Severity:** `warning` for high-confidence undocumented variables; `info` when documented; `not_verified` for dynamic access.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Bounded source/configuration scan.
5. **Inspected data:** High-confidence `os.environ`/`os.getenv` patterns, configuration templates, README/docs, and policy files.
6. **Detection algorithm:** Extract variable names only; exclude common optional/system variables and local test fixtures; compare with documented names and safe examples.
7. **Expected result:** `passed` when required/high-confidence variables have documentation/example; `failed` when a required-looking variable has no explanation; `not_applicable` when none are found; `not_verified` for dynamic access.
8. **Positive test cases:** `os.environ["DATABASE_URL"]` plus README and `.env.example`.
9. **Negative test cases:** Required-looking `SECRET_KEY` access with no documentation.
10. **Edge cases:** Prefix-based configuration; defaults; secrets intentionally injected by CI; variables assembled dynamically.
11. **False-positive handling:** Report names, never values; classify optional/defaulted variables as lower severity.
12. **Evidence format:** Relative source/template path, variable name, access classification, and documentation path if present.
13. **Remediation:** Document purpose, required/optional status, safe example, and how to provide the value without committing it.
14. **Requirements:** FR-005, FR-008, NFR-003, NFR-008.
15. **Known limitations:** Static analysis cannot prove runtime necessity or secret validity.

## 12. CS-PORT-001 — Developer-specific absolute paths

1. **Purpose:** Detect likely machine-specific paths that prevent another environment from using the repository.
2. **Severity:** `warning`; `error` when a path appears in a required setup/build command.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Bounded text/configuration scan.
5. **Inspected data:** Text/config files, scripts as data, Docker/CI metadata, and known path syntaxes for Windows, macOS, and Unix.
6. **Detection algorithm:** Match absolute path forms and home-directory references outside approved system/toolchain examples; normalize and record only a redacted path category.
7. **Expected result:** `passed` when no suspicious path is found; `failed`/`warning` when a repository-relative replacement is likely; `not_verified` when parsing is incomplete.
8. **Positive test cases:** `C:\Users\name\project` or `/home/name/project` in a setup script.
9. **Negative test cases:** `/usr/bin/python` in a documented system prerequisite; URL or regex text that is not a filesystem path.
10. **Edge cases:** Docker absolute paths inside the container; escaped Windows paths; test fixtures intentionally containing path examples.
11. **False-positive handling:** Use context and filename classification; label as “suspicious indicator,” not proof of failure.
12. **Evidence format:** Relative file/line and redacted category such as `host-home-path`; never include the username.
13. **Remediation:** Use project-relative paths, environment configuration, or documented tool discovery.
14. **Requirements:** FR-005, FR-008, NFR-003, NFR-007.
15. **Known limitations:** A legitimate absolute container/system path may be flagged for review.

## 13. CS-SEC-001 — Potential secret exposure indicator

1. **Purpose:** Identify likely committed credentials or sensitive files without exposing their values.
2. **Severity:** `blocking` for high-confidence private-key material; `error` for high-confidence token/password patterns; `warning` for weaker indicators.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Bounded text/file-name scan with redaction enabled.
5. **Inspected data:** File names, bounded text, `.env*`, key/certificate markers, and common provider token shapes; not binary contents by default.
6. **Detection algorithm:** Apply narrowly scoped, documented patterns plus context; suppress placeholders/test fixtures; emit a digest/line reference without the value.
7. **Expected result:** `passed` when no high-confidence indicator is found; `failed` when a high-confidence indicator is found; `not_verified` when content was excluded by limits.
8. **Positive test cases:** Fake private-key marker; fake token-shaped value in a tracked config file.
9. **Negative test cases:** `EXAMPLE_TOKEN=replace-me`; documentation placeholder; random long string without secret context.
10. **Edge cases:** Encoded values; secrets split across lines; generated files; encrypted data; false provider-like strings.
11. **False-positive handling:** Require context and placeholder suppression; label medium-confidence matches as indicators and never claim credential validity.
12. **Evidence format:** Relative path/line, indicator type, redaction count, and remediation; no raw value.
13. **Remediation:** Remove and rotate exposed credentials, add a safe example, update ignore rules, and review repository history.
14. **Requirements:** FR-005, FR-008, NFR-003, NFR-012.
15. **Known limitations:** No static pattern set proves absence of secrets or compromise.

## 14. CS-BUILD-001 — Container build configuration discovery

1. **Purpose:** Identify whether a Docker/OCI build configuration exists and whether basic supporting files are discoverable.
2. **Severity:** `info` for discovery; `warning` when documentation promises a container but no Dockerfile is found.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Repository inventory.
5. **Inspected data:** `Dockerfile*`, `.dockerignore`, compose files as bounded data, README container instructions, and base-image declarations.
6. **Detection algorithm:** Locate likely build files; resolve their referenced local paths without executing them; compare README claims with files; do not build in P0.
7. **Expected result:** `passed` when a claimed/required container configuration is present; `not_applicable` when no container workflow is claimed; `failed` only for a documented required container with missing configuration; `not_verified` for incomplete inventory.
8. **Positive test cases:** Dockerfile and README build command.
9. **Negative test cases:** README says “run with Docker” but no Dockerfile or compose configuration exists.
10. **Edge cases:** Multiple Dockerfiles; generated Dockerfile; remote base image; compose-only workflow.
11. **False-positive handling:** Discovery is not a build result; never claim that the image builds.
12. **Evidence format:** Relative build-file paths, referenced local paths, and documentation comparison.
13. **Remediation:** Add or correct the documented container configuration; run P1 verification when available.
14. **Requirements:** FR-005, FR-008, FR-019, NFR-014.
15. **Known limitations:** Static inspection cannot prove base-image availability or build success.

## 15. CS-PATH-001 — Repository-contained path validation

1. **Purpose:** Detect references that resolve outside the repository boundary or depend on undeclared external files.
2. **Severity:** `error` for a required path escape; `warning` for an uncertain local dependency.
3. **Supported types:** Generic and Python.
4. **Preconditions:** Boundary established and path-bearing metadata discovered.
5. **Inspected data:** Local path references in config, packaging metadata, scripts as text, Docker `COPY`/`ADD` sources, README file references, and symlink targets.
6. **Detection algorithm:** Resolve only lexically/canonically within the staged read boundary; reject `..` and external symlink targets; compare referenced paths with inventory; do not open an external target.
7. **Expected result:** `passed` when required local references are contained and present; `failed` for an external/missing required path; `not_verified` for dynamic path construction or incomplete inventory.
8. **Positive test cases:** Project-relative package data file exists inside root.
9. **Negative test cases:** Absolute developer path; `../shared-config` required by setup; Dockerfile copies a missing file.
10. **Edge cases:** Symlink inside root to inside root; Windows drive paths; case-insensitive collisions; generated files.
11. **False-positive handling:** Report a missing/external reference only when context identifies it as a required project resource; otherwise use an indicator warning.
12. **Evidence format:** Referencing file/line, normalized target category, containment result, and missing/external reason.
13. **Remediation:** Move required resources inside the project or document an explicit portable external prerequisite.
14. **Requirements:** FR-002, FR-005, FR-008, FR-014, NFR-002, NFR-006.
15. **Known limitations:** Dynamic runtime path creation cannot be fully resolved statically.

## 16. Catalog maintenance

Adding or changing a check requires:

1. a unique ID and algorithm version;
2. applicability and status semantics;
3. positive, negative, edge, and false-positive fixtures;
4. evidence and remediation behavior;
5. a traceability update;
6. terminal/JSON contract review;
7. a release note if the result can change a process exit code.
