# ColdStart Build and Reproducibility

**Status:** Python 3.12.8 source, test, and wheel checks pass locally; the
current Windows host does not have a working Docker Linux engine, WSL
distribution, or GNU Make
**Version:** 1.1
**Reference runtime:** Python 3.12.8
**Release gate:** Clean Linux checkout plus Docker smoke test in GitHub Actions

## 1. Purpose

ColdStart applies the same reproducibility discipline to itself that it applies
to inspected repositories. This document defines the supported setup, the
canonical commands, the Docker contract, and the evidence boundary between a
working code path and an unavailable host service.

The static CLI is useful without Docker, WSL, or Make. Those tools are release
and verification conveniences, not hidden runtime dependencies.

## 2. Supported environments

| Environment | Role | Requirement |
| --- | --- | --- |
| Linux | Reference development and release environment | Python 3.12.x; GNU Make for `make test` |
| WSL2 | Windows-hosted Linux development | A WSL2 distribution; Python 3.12.x; GNU Make |
| Windows PowerShell | Static CLI and direct test development | Python 3.12.x; Make is optional |
| macOS | Static CLI and direct test development | Python 3.12.x; Make is optional |
| Docker Linux container | Installed-package smoke and optional P1 verification | Docker Desktop/Engine with the Linux backend |

The project metadata supports `>=3.12,<3.13`. Python 3.12.8 is the pinned
reference runtime in `.python-version`, the Docker base image, and the release
examples.

## 3. Dependency policy

ColdStart has no third-party runtime dependency and no required third-party
development dependency. The two lockfiles are intentionally empty but
committed so dependency policy is visible:

- `requirements.lock` is the runtime lockfile;
- `requirements-dev.lock` is the required development/test lockfile; and
- any future dependency must be pinned with hashes in the appropriate file.

The package uses the dependency-free PEP 517/660 backend in
`build_backend/backend.py`. The backend reads the public project metadata from
`pyproject.toml` so wheel metadata does not silently drift from the package
configuration.

## 4. Setup

### Linux, macOS, or WSL

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
```

The commands install only repository-declared dependencies. Because the lockfiles
are empty, setup does not need a package index after Python and pip are present.

## 5. Canonical checks

On Linux or WSL, run:

```bash
make test
```

The Makefile chooses `.venv/bin/python` when it exists. An explicit interpreter
can be selected with `make test PYTHON=python3.12`.

The direct equivalent, usable on every supported host, is:

```text
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

On Windows, use:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

The optional `pytest.ini` makes `python -m pytest -q` collect the project and
fixture tests when pytest is already installed. Pytest is not required by the
supported lockfile or by `make test`.

## 6. Docker image contract

`Dockerfile` builds an installed, pure-Python ColdStart image from
`python:3.12.8-slim-bookworm`. It does not rely on a host `PYTHONPATH`, copy
virtual environments, install untracked packages, or require the inspected
repository during the image build.

First build and smoke test:

```bash
docker build --tag coldstart:dev .
docker run --rm --read-only --network none \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  coldstart:dev --help
```

After the base image is cached, the local/offline repeat is:

```bash
docker build --pull=false --tag coldstart:offline .
```

The first build may need network access to obtain the base image. A Docker CLI
without a running Linux engine is not sufficient; Docker Desktop must be
started and configured for Linux containers.

## 7. WSL guidance

WSL is optional. It is useful when a Windows developer wants the same GNU Make
and Linux command behavior used by the release gate.

After WSL2 and a distribution are installed, clone or access the repository
from `/mnt/<drive>/ColdStart`, install Python 3.12 and GNU Make inside the
distribution, then run the Linux setup and `make test` commands. Docker Desktop
users should enable the same WSL distribution under Docker Desktop's WSL
integration settings before using Docker from WSL.

If `wsl.exe` reports that WSL is not installed, the repository is not broken:
the Windows optional features and a Linux distribution still need to be
installed and Windows may require a restart.

## 8. Optional authorized verification

The normal audit is read-only and non-executing. The separate verification
command is explicit:

```text
PYTHONPATH=src .venv/bin/python -m coldstart verify PATH --kind tests --offline --plan
PYTHONPATH=src .venv/bin/python -m coldstart verify PATH --kind tests --offline --authorize
```

Offline tests use Docker `network=none`, a read-only repository mount, fixed
CPU/memory/process limits, bounded output, and no host fallback. If Docker or
the pinned image is unavailable, the receipt is `not_verified`; that result is
not a pass and does not claim that the project tests ran.

## 9. Clean-checkout release procedure

On a clean Linux checkout:

```text
git clone <repository-url> ColdStart
cd ColdStart
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
make test
docker build --tag coldstart:clean .
docker run --rm --read-only --network none \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  coldstart:clean --help
```

The expected result is a passing offline suite, a successful installed-package
Docker build, and usable help output. This sequence is the Linux/Docker gate in
`.github/workflows/ci.yml`.

## 10. Current evidence

The following results were actually observed in the current workspace on
October 24, 2026. They are evidence for this checkout and host only:

| Command | Result |
| --- | --- |
| `.venv3128/Scripts/python.exe --version` | Python 3.12.8 |
| `PYTHONPATH=src .venv3128/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -q` | 151 tests collected: 148 passed and 3 platform-expected skips |
| `python -m pytest -q` | 150 tests passed; 3 skipped; 12 subtests passed |
| `py -3.12 -m pip wheel --no-deps --no-build-isolation .` | `coldstart-0.1.0-py3-none-any.whl` built successfully |
| `docker version` | Docker CLI 29.8.2 is installed; the Docker Desktop Linux daemon could not start |
| `wsl.exe --list --verbose` | WSL is not installed on this Windows host |
| `make --version` | GNU Make is unavailable in the current shell |

The Docker build and clean Linux checkout were not marked as passed because
the Docker daemon and WSL environment were unavailable. GitHub Actions is the
repeatable place to execute those gates on a clean Linux runner.

## 11. Release checklist

- [x] Runtime is declared in `.python-version`, `pyproject.toml`, and Dockerfile.
- [x] Runtime and development lockfiles are committed and intentionally empty.
- [x] Static CLI, exact Python 3.12.8 test suite, and wheel smoke pass locally.
- [x] Dockerfile installs the package rather than relying on source-path state.
- [x] README, contribution guidance, and CI workflow document the supported paths.
- [ ] `make test` has run in a clean Linux/WSL environment in this workspace.
- [ ] Docker build/run has run against a working Linux Docker daemon in this workspace.
- [ ] A clean Linux checkout has been executed outside this Windows host.
- [x] Unavailable platform services are reported as unavailable, never simulated as passed.
- [x] No claim of universal reproducibility appears in the project documentation.

## 12. Troubleshooting

| Symptom | Action |
| --- | --- |
| `python3.12` is unavailable | Install Python 3.12.x and recreate `.venv`. |
| `make` is unavailable | Use WSL/Linux with GNU Make or the direct Python test command. |
| Docker cannot connect to its daemon | Start Docker Desktop and select the Linux engine. |
| WSL is not installed | Enable WSL and Virtual Machine Platform, restart Windows, then install a distribution. |
| The first Docker build cannot pull the base image | Run the first build with network access; use `--pull=false` only after the image is cached. |
| Offline verification returns `not_verified` | Check Docker Desktop, the Linux engine, and the pinned image; do not use host fallback. |
