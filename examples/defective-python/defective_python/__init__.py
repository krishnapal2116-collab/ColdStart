"""A source file that must never be imported by the static audit."""

from pathlib import Path


# The marker makes accidental execution observable without containing a secret.
Path("defective-python-execution.marker").write_text("executed", encoding="utf-8")
