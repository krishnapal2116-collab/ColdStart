"""Allow ``python -m coldstart`` to run the ColdStart CLI."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
