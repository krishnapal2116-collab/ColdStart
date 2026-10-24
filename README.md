# ColdStart

[![CI](https://github.com/krishnapal2116-collab/ColdStart/actions/workflows/ci.yml/badge.svg)](https://github.com/krishnapal2116-collab/ColdStart/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

ColdStart is a local-first command-line auditor for software-repository
reproducibility. It checks whether a repository declares enough runtime,
dependency, setup, configuration, test, portability, security, and container
evidence for another environment to recreate it.

The safe default is a deterministic, read-only static audit. ColdStart does
not execute the inspected repository, install its dependencies, upload source,
or require an AI service. Optional test and Docker verification is a separate,
explicitly authorized operation with bounded receipts and no host fallback for
offline checks.

## What ColdStart checks

- Python runtime and dependency declarations;
- lockfile and setup-documentation evidence;
- test-command, configuration, environment-variable, and portability risks;
- secrets, local paths, build configuration, and container metadata;
- deterministic terminal or JSON reports with stable check IDs;
- optional explanations for each registered check; and
- deterministic comparison of two compatible audit reports.

ColdStart is a diagnostic tool, not a guarantee that a project works on every
computer, operating system, service, or future dependency state.

## Release scope

- **P0:** deterministic, read-only repository audit and terminal/JSON report;
- **P1:** explicitly authorized verification, rule explanations, and baseline
  comparison; and
- **P2/future:** automatic fixes, hosted dashboards, AI-generated judgments,
  broad language coverage, and enterprise policy management.

## Quick start

### Linux, macOS, or WSL

Prerequisites:

- Git;
- Python 3.12.x; Python 3.12.8 is the reference release; and
- GNU Make for the canonical test command.

```bash
git clone https://github.com/krishnapal2116-collab/ColdStart.git
cd ColdStart
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
make test
```

If the `python3.12` command is not available, install Python 3.12 through the
normal package manager for the operating system. Do not replace it with an
unrelated system Python just to make the command appear to work.

### Windows PowerShell

```powershell
git clone https://github.com/krishnapal2116-collab/ColdStart.git
Set-Location -LiteralPath .\ColdStart
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q
```

GNU Make is not required for the static CLI or the Windows test command. WSL
users can use the Linux commands after installing a WSL2 distribution and
running the repository from `/mnt/<drive>/ColdStart`.

## Run an audit

The audit command is safe by default and never runs repository code:

```bash
PYTHONPATH=src .venv/bin/python -m coldstart audit PATH --format terminal
PYTHONPATH=src .venv/bin/python -m coldstart audit PATH --format json --output report.json
```

The committed fixtures demonstrate both outcomes:

```bash
PYTHONPATH=src .venv/bin/python -m coldstart audit examples/clean-python --format terminal
PYTHONPATH=src .venv/bin/python -m coldstart audit examples/defective-python --format terminal
```

The clean fixture is expected to pass. The defective fixture intentionally
reports reproducibility findings and must not execute fixture code.

## Optional verification

Verification is separate from `audit`. Review a plan without starting a child
process:

```bash
PYTHONPATH=src .venv/bin/python -m coldstart verify PATH --kind tests --offline --plan
```

After reviewing the plan, explicitly authorize the Docker-isolated attempt:

```bash
PYTHONPATH=src .venv/bin/python -m coldstart verify PATH --kind tests --offline --authorize
```

Offline verification uses Docker with `--network=none`, a read-only repository
mount, fixed resource limits, and no host fallback. If Docker or its Linux
engine is unavailable, ColdStart returns `not_verified`; it does not silently
run the project tests on the host.

Other offline commands:

```bash
PYTHONPATH=src .venv/bin/python -m coldstart verify PATH --kind docker-build --offline --plan
PYTHONPATH=src .venv/bin/python -m coldstart explain CS-DEPS-001
PYTHONPATH=src .venv/bin/python -m coldstart compare current.json baseline.json --format terminal
```

## Docker image

The Dockerfile builds a Linux image containing the installed ColdStart package,
not a source-tree `PYTHONPATH` shortcut:

```bash
docker build --tag coldstart:dev .
docker run --rm --read-only --network none \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  coldstart:dev --help
```

The first build may download `python:3.12.8-slim-bookworm`. After that image is
cached, `docker build --pull=false --tag coldstart:offline .` checks the local
build path without requesting a new base image. Docker Desktop must be running
with its Linux engine enabled; installing the Docker CLI alone is not enough.

To audit a repository mounted read-only from Linux or WSL:

```bash
docker run --rm --read-only --network none \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  --volume "$PWD:/workspace:ro" \
  coldstart:dev audit /workspace --format terminal
```

On Windows PowerShell, use a Windows-compatible volume path or run this command
inside WSL. The static audit itself does not require Docker.

## Development and testing

`make test` is the canonical offline test command. The Makefile automatically
uses `.venv/bin/python` on Linux/WSL or `.venv/Scripts/python.exe` on Windows
when that environment exists; override it with `make test PYTHON=python3.12`
when necessary.

The direct equivalent is:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

If pytest is already installed, the repository also supports:

```bash
python -m pytest -q
```

Pytest is an optional collection runner. It is not a runtime dependency, and
the standard-library `unittest` suite remains the supported offline test path.
GitHub Actions runs Linux/Docker and Windows static smoke gates on every push
and pull request.

## Requirements and packaging

ColdStart currently has no third-party runtime or required development
dependencies. `requirements.lock` and `requirements-dev.lock` are intentionally
empty, documented lockfiles. If a dependency is added, it must be pinned with
hashes in the appropriate file and covered by the release checks.

The package uses a small dependency-free PEP 517/660 build backend under
`build_backend/`. The Docker image and editable installation build from the
same `pyproject.toml` metadata.

## Report meanings

- `passed`: the check found the expected evidence;
- `failed`: the check found a reproducibility risk;
- `not_applicable`: the check does not apply to the detected project;
- `skipped`: a local policy explicitly excluded the check;
- `not_verified`: bounded evidence was unavailable or incomplete; and
- `error`: ColdStart could not safely evaluate the check.

Static `passed` findings never mean that project tests or builds ran. A
verification `passed` result requires explicit authorization, an observed exit
code of zero, completed cleanup, and an unchanged source manifest.

## Project layout

```text
src/coldstart/       CLI, audit engine, checks, reports, and verification
tests/               Standard-library unit and integration tests
examples/             Clean and deliberately defective audit fixtures
docs/                  Requirements, contracts, architecture, and release notes
Dockerfile            Linux container image for the installed CLI
Makefile              Canonical offline test command
.github/workflows/    Linux and Docker continuous integration
```

## Documentation

- [Project charter](docs/00_PROJECT_CHARTER.md)
- [Product requirements](docs/01_PRODUCT_REQUIREMENTS.md)
- [MVP acceptance](docs/02_MVP_SCOPE_AND_ACCEPTANCE.md)
- [System architecture](docs/03_SYSTEM_ARCHITECTURE.md)
- [Threat model](docs/04_THREAT_MODEL.md)
- [Privacy and data handling](docs/05_PRIVACY_AND_DATA_HANDLING.md)
- [P0 check catalog](docs/06_CHECK_CATALOG.md)
- [CLI and report contracts](docs/07_CLI_AND_REPORT_CONTRACTS.md)
- [Test strategy](docs/09_TEST_STRATEGY.md)
- [Build and reproducibility](docs/10_BUILD_AND_REPRODUCIBILITY.md)
- [Implementation and release plan](docs/12_IMPLEMENTATION_AND_RELEASE_PLAN.md)
- [Documentation audit](docs/14_DOCUMENTATION_AUDIT.md)

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: coldstart` | Install the package in `.venv`, or run with `PYTHONPATH=src`. |
| `python3.12` is not found | Install Python 3.12.x and recreate `.venv`; the project does not require a global package install. |
| `make` is not found | Use WSL/Linux with GNU Make, or run the direct `unittest` command on Windows. |
| Docker CLI cannot connect to its daemon | Start Docker Desktop and select the Linux engine. The CLI being installed is not sufficient. |
| `wsl` says it is not installed | Enable Windows Subsystem for Linux and Virtual Machine Platform, restart Windows, then install a Linux distribution. |
| Offline verification returns `not_verified` | This is fail-closed behavior: Docker, the Linux engine, or the pinned image is unavailable. No host fallback is attempted. |
| Docker build cannot pull the base image | Run the first build with network access, then use `--pull=false` only after `python:3.12.8-slim-bookworm` is cached. |

## Current verification status

The repository records commands and results rather than simulating platform
success. The exact Python 3.12.8 suite and wheel smoke checks pass locally.
Docker CLI availability does not prove the Docker Linux engine is running, and
WSL is an optional host integration that must be installed separately. The
GitHub Actions workflow is the clean Linux/Docker release gate; its result is
visible in the repository's Actions tab after each push or pull request.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Keep changes focused, preserve the
read-only default, add tests for behavior changes, and report unavailable
platform services honestly.

## License

ColdStart is released under the [MIT License](LICENSE).
