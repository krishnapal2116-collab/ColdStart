# ColdStart Build and Reproducibility Specification

**Status:** Planned commands; not yet executed
**Version:** 0.2
**Build baseline:** Clean Linux first, Windows/macOS static smoke support

## 1. Purpose

ColdStart must reproduce itself before it asks other projects to reproduce. This document defines the intended runtime, dependencies, setup, test, Docker, and clean-checkout procedure. Commands are plans until implementation exists and OmniRush executes them; no command below is being claimed as passed.

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

The initial P0 runtime should have no third-party dependency beyond the approved packaging/runtime baseline where practical. `pytest` and `ruff` are development dependencies. Any new dependency requires:

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
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

`make test` is the single canonical offline command. It must run the complete local suite and must not download packages or contact a service. The direct pytest command is documented for troubleshooting, not as a second competing standard.

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

Expected outcomes are a documented successful setup, passing offline tests, a successful ColdStart Docker build, and usable help output. These are future acceptance steps, not current results.

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

## 12. Release reproducibility checklist

- [ ] Exact Python runtime is pinned.
- [ ] Runtime and development lockfiles are committed and hash-checked.
- [ ] Dockerfile and base image choice are documented.
- [ ] `make test` works offline after setup.
- [ ] Clean Linux checkout instructions were actually run.
- [ ] Docker build/run was actually run.
- [ ] No global dependency is required by the instructions.
- [ ] README setup/run/test/build/deploy/limitations steps match the implementation.
- [ ] Actual output and exit codes are recorded.
- [ ] No unsupported “fully reproducible everywhere” claim appears.
