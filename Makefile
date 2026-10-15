PYTHON ?= python
PYTHONPATH_VALUE := src

.PHONY: test help

help:
	@printf '%s\n' 'make test     Run the offline Phase 1 test suite'

test:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
