"""Phase 1 command-line foundation for ColdStart."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .version import (
    CHECK_CATALOG_VERSION,
    REPORT_SCHEMA_VERSION,
    TARGET_PYTHON,
    __version__,
)


def _version_text() -> str:
    return "\n".join(
        (
            f"ColdStart {__version__}",
            f"Report schema: {REPORT_SCHEMA_VERSION}",
            f"Check catalog: {CHECK_CATALOG_VERSION}",
            f"Target Python: {TARGET_PYTHON}",
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coldstart",
        description=(
            "A local-first, evidence-based software-repository "
            "reproducibility auditor."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=_version_text(),
        help="show the ColdStart, report-schema, and catalog versions",
    )
    subparsers = parser.add_subparsers(dest="command")

    version_parser = subparsers.add_parser(
        "version", help="show the ColdStart version information"
    )
    version_parser.set_defaults(handler=_run_version)

    audit_parser = subparsers.add_parser(
        "audit", help="audit a local repository (static audit is coming next)"
    )
    audit_parser.add_argument("path", metavar="PATH")
    audit_parser.set_defaults(handler=_run_audit_placeholder)

    return parser


def _run_version(_args: argparse.Namespace) -> int:
    print(_version_text())
    return 0


def _run_audit_placeholder(args: argparse.Namespace) -> int:
    """Reserve the audit command without pretending that scanning exists yet."""

    repository = Path(args.path)
    if not repository.exists():
        print(f"ColdStart: repository path does not exist: {args.path}", file=sys.stderr)
        return 2
    if not repository.is_dir():
        print(f"ColdStart: repository path is not a directory: {args.path}", file=sys.stderr)
        return 2

    print("ColdStart Phase 1 foundation")
    print("Status: not_verified")
    print("The static audit engine is planned for the next implementation slice.")
    print("Repository files: not executed or modified.")
    return 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))
