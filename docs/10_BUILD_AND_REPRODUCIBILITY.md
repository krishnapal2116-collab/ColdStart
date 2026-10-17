# ColdStart Build and Reproducibility Specification

**Status:** Phase 6.1 Docker-isolation slice tested under the available interpreter; target-runtime/build verification pending
**Version:** 0.8
**Build baseline:** Clean Linux first, Windows/macOS static smoke support

## 1. Purpose

ColdStart must reproduce itself before it asks other projects to reproduce. This document defines the intended runtime, dependencies, setup, test, Docker, and clean-checkout procedure. Planned target-environment commands are not claims of success until OmniRush executes them; the verification record below distinguishes actual local checks from unavailable acceptance checks.

## 2. Supported operating systems

- **Release baseline:** Linux x86_64 in a clean machine/container with Python 3.12.8 and Docker for P1 checks.
- **Developer static CLI:** Windows 11, macOS 13+, and current supported Linux distributions with Python 3.12.8.
- **Platform behavior:** path separators, symlinks, permissions, process groups, and line endings are tested explicitly. P1 Docker behavior may be limited by the local Docker installation.

## 3. Runtime and dependency choice

The proposed pinned runtime is Python `3.12.8`:

- `.python-version` will contain exactly `3.12.8`;
- the Dockerfile will use `python:3.12.8-slim-bookworm` unless an availability review approves an equivalent digest-pinned image;
- the implementation will use `pathlib`, `argparse`, `tomllib`, `json`, `hashlib`, and other standard-library modules for the P0 core;
- development dependencies will be pinned in a committed hash-checked lockfile;
- no runtime dependency may require a generative AI API or a network service for P0.

The final image/tag availability and hashes must be checked during Phase 1. If the exact base image is unavailable, update this document and the decision log before changing it.

## 4. Dependency and lockfile strategy

Use `pyproject.toml` for package metadata and a committed, hash-pinned `requirements.lock` for runtime/build dependencies plus `requirements-dev.lock` for test/lint tooling. The lockfiles are generated in a project virtual environment, reviewed, and installed with `--require-hashes`. No global package installation is part of the supported setup.

The Phase 1 foundation has no third-party runtime or development dependency: its smoke tests use `unittest` from the Python standard library, and its small PEP 517/660 backend is vendored under `build_backend/`. `pytest` and `ruff` remain optional future tooling, not hidden requirements. Any new dependency requires:

1. a reason tied to a requirement;
2. license and supply-chain review;
3. a pinned version and hashes;
4. an offline test plan;
5. a lockfile update and Git checkpoint.

## 5. Planned setup commands

### Linux/macOS

```text
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
```

### Windows PowerShell

```text
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

The implementation README must explain how to obtain the pinned Python runtime without silently installing global software. If a developer lacks Python 3.12.8, that is a setup gap to resolve through the documented environment procedure.

## 6. Development commands

The exact commands below are the intended interface after implementation:

```text
make test
python -m unittest discover -s tests -p 'test_*.py' -v
```

`make test` is the single canonical offline command. It runs the complete local suite with the standard library and must not download packages or contact a service. The direct `unittest` command is documented for troubleshooting, not as a second competing standard.

## 7. Docker build and run procedures

Planned clean build:

```text
docker build --pull=false --tag coldstart:dev .
docker run --rm --read-only --network none --tmpfs /tmp:rw,nosuid,size=64m coldstart:dev --help
```

The Dockerfile must install only repository-declared, locked dependencies and must run the CLI without assuming a host path. A clean build is not a claim that the inspected repository is reproducible; it verifies ColdStart itself.

P1 verification of an inspected project is a separate operation and must use a sanitized staging context, explicit authorization, documented network mode, limits, and cleanup. Docker is not treated as a complete security boundary.

## 8. Offline verification procedure

After the project environment has been set up:

1. Disconnect or deny network access.
2. Run `make test`.
3. Run the clean and defective fixture audits.
4. Confirm reports and normalized findings match expected snapshots.
5. Confirm no test attempts an external service.
6. Record command, exit code, and artifact paths in the release evidence.

The first setup may need access to obtain pinned dependencies; “offline test” begins after the documented environment is installed.

## 9. Clean-checkout procedure

On a clean Linux machine:

```text
git clone <approved-repository-location> ColdStart
cd ColdStart
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
make test
docker build --pull=false --tag coldstart:clean .
docker run --rm --read-only --network none coldstart:clean --help
```

Expected outcomes are a documented successful setup, passing offline tests, a successful ColdStart Docker build, and usable help output. The current development machine does not provide Python 3.12.8, Docker, or Make; those target checks remain unverified until run in a suitable environment.

## 10. Environment-variable policy

ColdStart P0 reads no required secret environment variables. Optional debug settings must be documented and must not carry credentials. The process must not pass the host environment to a P1 runner wholesale.

## 11. Troubleshooting

| Symptom | Diagnostic action |
| --- | --- |
| Python version mismatch | Confirm `python --version` and the pinned `.python-version`; use the documented project environment |
| Lockfile install fails | Verify the interpreter, lockfile integrity, platform tags, and clean network/setup prerequisites; do not install unpinned packages globally |
| `make` unavailable on Windows | Use the documented direct Python commands for local development; Linux `make test` remains the release command |
| Docker unavailable | Run P0 static tests; record P1 verification as unavailable rather than using host fallback |
| Offline test tries network | Treat as a defect in ColdStart or a fixture; do not mark offline verification passed |
| Report differs across runs | Compare normalized JSON, tool/schema/catalog versions, options, filesystem changes, and platform-specific evidence |
| P1 execution remains separate | `coldstart audit PATH` evaluates all 13 P0 checks statically, but it does not run project tests or container builds; those require a separate authorized verification flow |

## 12. Release reproducibility checklist

- [x] Exact Python runtime is declared in `.python-version`.
- [x] Runtime and development lockfiles are committed; Phase 1 contains no third-party entries requiring hashes.
- [x] Dockerfile and base image choice are documented.
- [ ] `make test` works offline after setup; Make is unavailable in the current environment (`make: command not found`).
- [ ] Clean Linux checkout instructions were actually run.
- [ ] Docker build/run was actually run.
- [ ] No global dependency is required by the instructions.
- [ ] README setup/run/test/build/deploy/limitations steps match the implementation.
- [x] Available-environment output and exit codes are recorded; unavailable target-tool outcomes remain open.
- [ ] No unsupported “fully reproducible everywhere” claim appears.

## 13. M1/M2/M3/M4/M5/M6 verification record

The following checks were actually run in the current workspace:

- `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v` — passed under Python 3.14.7; this is not the pinned Python 3.12.8 acceptance environment.
- `PYTHONPATH=src python -m coldstart --help` — passed under Python 3.14.7.
- `PYTHONPATH=src python -m coldstart version` — passed under Python 3.14.7.
- During M1, `PYTHONPATH=src python -m coldstart audit .` — returned the intentional reserved-command exit code `3` and reported `not_verified` without executing or modifying repository files; M2/M3/M4 now perform bounded discovery and complete static catalog checks for the same command without executing project code.
- `python -m pip wheel --no-deps --no-build-isolation .` — correctly refused the current Python 3.14.7 environment because the project requires `>=3.12,<3.13`; this is a real environment mismatch, not a passing build.
- `python -m pip wheel --no-deps --no-build-isolation --ignore-requires-python . --wheel-dir <approved temporary directory>` — passed as a dependency-free backend smoke check; the override means this is not proof under Python 3.12.8.
- `python -m compileall -q src build_backend tests` — passed under Python 3.14.7.
- `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v` after M1 integration — 14 tests passed under Python 3.14.7.
- `PYTHONPATH=src python -m unittest tests.test_phase3_m2_discovery -v` — 19 M2 tests passed with 2 platform-expected skips under Python 3.14.7.
- `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v` after M2 integration — 31 tests passed with 2 platform-expected skips under Python 3.14.7.
- `PYTHONPATH=src python -m unittest tests.test_phase3_m3_dependencies tests.test_phase3_m3_runtime_docs tests.test_phase3_m3_integration -v` — 26 M3 tests passed under Python 3.14.7.
- `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v` after M3 integration — 57 tests passed with 2 platform-expected skips under Python 3.14.7.
- `PYTHONPATH=src python -m unittest tests.test_phase4_m4_docs_config tests.test_phase4_m4_quality tests.test_phase4_m4_integration -v` — 38 M4 tests ran with 37 passes and 1 platform-expected symlink skip under Python 3.14.7.
- `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v` after M4 integration — 94 tests passed with 3 platform-expected skips under Python 3.14.7.
- `PYTHONPATH=src python -m unittest tests.test_phase5_m5_hardening -v` — 7 M5 hardening/self-audit tests passed under Python 3.14.7.
- `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v` after M5 hardening — 101 tests passed with 3 platform-expected skips under Python 3.14.7.
- `PYTHONPATH=src python -m unittest tests.test_phase6_m6_execution tests.test_phase6_m6_cli -v` — 18 M6/M6.1 tests passed under Python 3.14.7.
- `PYTHONPATH=src python -m unittest tests.test_phase6_m6_examples -v` — 2 committed clean/defective fixture acceptance tests passed under Python 3.14.7.
- `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v` after M6.1/fixtures — 121 tests passed with 3 platform-expected skips under Python 3.14.7.
- `PYTHONPATH=src python -m coldstart audit examples/clean-python --format json` — exited `0` with no failed/error findings.
- `PYTHONPATH=src python -m coldstart audit examples/defective-python --format json` — exited `1` with expected static findings and no fixture execution.
- `PYTHONPATH=src python -m coldstart verify . --kind tests --offline --plan --format json` — produced a Docker-isolated plan with `network_mode=none`, `--pull=never`, read-only `/workspace` mount, fixed resource limits, explicit authorization, and no execution receipt; the current repository static preflight returned its own findings exit code.
- `PYTHONPATH=src python -m coldstart verify . --kind docker-build --offline --authorize --format json` — exited `3`, produced a truthful `not_verified` receipt because Docker is unavailable; no host fallback was attempted.
- `PYTHONPATH=src python -m coldstart verify . --kind tests --offline --authorize --format json` — Docker-backed offline execution is fail-closed and returns `not_verified` because Docker is unavailable; no host fallback was attempted.
- `PYTHONPATH=src python -m coldstart audit . --format terminal` — exited `0`, reported a high-confidence Python candidate, bounded inventory with no staging, all 13 catalog IDs, and bounded `not_verified` evidence for oversized/dynamic local files.
- `python -m compileall -q src build_backend tests` after M5 hardening — passed under Python 3.14.7.
- `git diff --check` after M5 hardening — passed.
- `python -m pip wheel --no-deps --no-build-isolation .` after M5 hardening — refused because Python 3.14.7 does not satisfy the pinned `>=3.12,<3.13` requirement.
- `make test` — unavailable: `make: command not found`.
- `docker --version` and `docker build --pull=false --tag coldstart:m5 .` — unavailable: `docker: command not found`.
- `python3.12 --version` — unavailable: `python3.12: command not found`.
- `py -3.12 --version` — unavailable: the Python launcher reported no suitable runtime.

The following target checks remain unverified because the current machine does not provide them:

- Python 3.12.8 (`python3.12` and `py -3.12` were unavailable).
- GNU Make (`make` was unavailable).
- Docker (`docker` was unavailable).
- Docker-backed network-isolated test execution (the M6.1 runner is implemented and reports `not_verified` until Docker and the pinned image are available).
