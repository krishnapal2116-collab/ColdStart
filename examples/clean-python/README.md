# Clean Python fixture

This is a small, dependency-free Python package used by ColdStart's P0 demo.

## Prerequisites

Use Python 3.12.8, as declared by `.python-version` and `pyproject.toml`.

## Installation

No third-party packages are required. The checkout is directly runnable, so no
dependency installation step is needed. Keep `requirements.lock` as the empty
lockfile policy for this dependency-free project.

## Configuration

No external configuration is required.

## Run

```text
python -m clean_python
```

## Test

```text
python -m unittest discover -s tests -p 'test_*.py'
```
