# Prefer the project virtual environment, then fall back to a platform Python.
# Override explicitly when needed: ``make test PYTHON=python3.12``.
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,$(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,python3))
PYTHONPATH_VALUE := src

.PHONY: test help

help:
	@printf '%s\n' 'make test     Run the offline test suite'
	@printf '%s\n' 'make test PYTHON=...  Select the Python interpreter'

test:
	@PYTHONPATH=$(PYTHONPATH_VALUE) "$(PYTHON)" -m unittest discover -s tests -p 'test_*.py' -v
