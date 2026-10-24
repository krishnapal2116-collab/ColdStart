# Contributing to ColdStart

Thank you for helping improve ColdStart. The project values small, reviewable
changes and evidence-backed behavior over broad feature expansion.

## Development setup

ColdStart targets Python 3.12.x and uses only the Python standard library at
runtime. Python 3.12.8 is the reference release used by the repository and
Docker image.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

On Windows PowerShell, use `py -3.12` and `.\.venv\Scripts\python.exe`.
WSL users can follow the Linux commands from `/mnt/<drive>/ColdStart`.

## Checks before opening a pull request

Run the canonical offline suite:

```bash
make test
```

The direct equivalent is:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

If `pytest` is already installed, the repository also supports the convenient
collection smoke check:

```bash
python -m pytest -q
```

Do not treat an optional pytest run as a replacement for `make test`.

For container changes, run:

```bash
docker build --tag coldstart:dev .
docker run --rm --read-only --network none \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  coldstart:dev --help
```

If Docker Desktop or the WSL engine is unavailable, report that environment
limitation rather than changing the code to use an unsafe host fallback.

## Change expectations

- Keep the default `audit` command read-only and non-executing.
- Preserve deterministic report ordering, stable check IDs, and bounded output.
- Add or update a focused test for behavior changes.
- Keep secrets, tokens, private paths, generated reports, and virtual
  environments out of commits.
- Update the README or the relevant document when a user-visible command,
  limitation, or release gate changes.

## Pull requests

Explain the user-visible result, list the checks you ran, and call out any
platform-specific verification that was unavailable. Do not claim Docker,
WSL, Linux, or network-isolated execution passed unless the command actually
ran and produced the recorded result.
