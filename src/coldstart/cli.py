"""Command-line entry point for ColdStart."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .audit import run_audit
from .boundary import (
    BoundaryValidationError,
    OutputValidationError,
    safe_text,
    validate_output_path,
)
from .reporting import serialize_report, write_report
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
            "P1 Docker verification: unavailable (not implemented)",
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
    # Accept the display flags both before and after ``audit``.  The command
    # parser below owns the post-command forms used in the documented examples.
    parser.add_argument("--format", dest="global_format", choices=("terminal", "json"))
    parser.add_argument("--output", dest="global_output", metavar="PATH")
    parser.add_argument("--config", dest="global_config", metavar="PATH")
    parser.add_argument("--strict", dest="global_strict", action="store_true", default=None)
    parser.add_argument("--max-files", dest="global_max_files", type=int, metavar="N")
    parser.add_argument("--max-bytes", dest="global_max_bytes", type=int, metavar="N")
    parser.add_argument("--max-depth", dest="global_max_depth", type=int, metavar="N")
    parser.add_argument("--max-seconds", dest="global_max_seconds", type=int, metavar="N")
    parser.add_argument(
        "--exclude",
        dest="global_excludes",
        action="append",
        metavar="PATH",
        help="exclude a repository-relative path in addition to built-in exclusions",
    )
    subparsers = parser.add_subparsers(dest="command")

    version_parser = subparsers.add_parser(
        "version", help="show the ColdStart version information"
    )
    version_parser.set_defaults(handler=_run_version)

    audit_parser = subparsers.add_parser(
        "audit", help="run a safe, non-executing static audit"
    )
    audit_parser.add_argument("path", metavar="PATH")
    audit_parser.add_argument(
        "--format",
        dest="audit_format",
        choices=("terminal", "json"),
        default=None,
        help="select terminal or JSON report output (default: terminal)",
    )
    audit_parser.add_argument(
        "--output",
        dest="audit_output",
        metavar="PATH",
        default=None,
        help="write the selected report to an existing parent directory",
    )
    audit_parser.add_argument(
        "--config",
        dest="audit_config",
        metavar="PATH",
        default=None,
        help="read a local .coldstart.toml policy (default: repository root if present)",
    )
    audit_parser.add_argument(
        "--strict",
        dest="audit_strict",
        action="store_true",
        default=None,
        help="treat not-verified findings as policy failures",
    )
    audit_parser.add_argument("--max-files", dest="audit_max_files", type=int, metavar="N")
    audit_parser.add_argument("--max-bytes", dest="audit_max_bytes", type=int, metavar="N")
    audit_parser.add_argument("--max-depth", dest="audit_max_depth", type=int, metavar="N")
    audit_parser.add_argument("--max-seconds", dest="audit_max_seconds", type=int, metavar="N")
    audit_parser.add_argument(
        "--exclude",
        dest="audit_excludes",
        action="append",
        metavar="PATH",
        help="exclude a repository-relative path in addition to built-in exclusions",
    )
    audit_parser.set_defaults(handler=_run_audit)

    return parser


def _run_version(_args: argparse.Namespace) -> int:
    print(_version_text())
    return 0


def _run_audit(args: argparse.Namespace) -> int:
    """Compose validation, bounded M2 discovery, and the requested serializer."""

    output_format = args.audit_format or args.global_format
    output = args.audit_output or args.global_output
    strict = bool(args.audit_strict or args.global_strict)
    config_path = args.audit_config or args.global_config
    limits = {
        "max_files": (
            args.audit_max_files
            if args.audit_max_files is not None
            else args.global_max_files
        ),
        "max_bytes": (
            args.audit_max_bytes
            if args.audit_max_bytes is not None
            else args.global_max_bytes
        ),
        "max_depth": (
            args.audit_max_depth
            if args.audit_max_depth is not None
            else args.global_max_depth
        ),
        "max_seconds": (
            args.audit_max_seconds
            if args.audit_max_seconds is not None
            else args.global_max_seconds
        ),
    }
    limits = {name: value for name, value in limits.items() if value is not None}
    excludes = list(args.global_excludes or ()) + list(args.audit_excludes or ())
    try:
        output_path = validate_output_path(output)
        result = run_audit(
            args.path,
            output_format=output_format,
            strict=strict,
            config_path=config_path,
            limits=limits or None,
            excludes=excludes,
        )
        selected_format = str(result.report.invocation.get("format", "terminal"))
        rendered = serialize_report(
            result.report,
            selected_format,
            exit_code=result.exit_code,
        )
        if output_path is None:
            sys.stdout.write(rendered)
        else:
            write_report(rendered, output_path)
        return result.exit_code
    except (BoundaryValidationError, OutputValidationError) as error:
        print(f"ColdStart: {safe_text(error)}", file=sys.stderr)
        return 2
    except OSError:
        print("ColdStart: could not write the requested report output", file=sys.stderr)
        return 2
    except Exception:
        # Do not expose repository content or host paths when an unexpected
        # ColdStart failure occurs.  An internal error can never look like pass.
        print("ColdStart: internal error while auditing", file=sys.stderr)
        return 4


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))
