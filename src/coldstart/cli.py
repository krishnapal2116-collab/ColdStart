"""Command-line entry point for ColdStart."""

from __future__ import annotations

import argparse
from dataclasses import replace
import sys
from typing import Sequence

from .audit import run_audit
from .boundary import (
    BoundaryValidationError,
    OutputValidationError,
    safe_text,
    validate_output_path,
)
from .execution import (
    MAX_OUTPUT_LIMIT_BYTES,
    MAX_TIMEOUT_SECONDS,
    ExecutionValidationError,
    build_execution_plan,
    execute_execution_plan,
)
from .explanation import UnknownCheckError, explanation_for, render_explanation
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
            "P1 Docker verification: optional authorized runner (availability checked at verify time)",
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

    explain_parser = subparsers.add_parser(
        "explain", help="explain one registered P0 check without auditing a repository"
    )
    explain_parser.add_argument("check_id", metavar="CHECK_ID")
    explain_parser.set_defaults(handler=_run_explain)

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

    verify_parser = subparsers.add_parser(
        "verify", help="propose or explicitly authorize one bounded P1 verification"
    )
    verify_parser.add_argument("path", metavar="PATH")
    verify_parser.add_argument(
        "--kind",
        choices=("tests", "docker-build"),
        required=True,
        help="verification kind to propose or run",
    )
    verify_parser.add_argument(
        "--format",
        dest="verify_format",
        choices=("terminal", "json"),
        default=None,
        help="select terminal or JSON report output (default: terminal)",
    )
    verify_parser.add_argument(
        "--output",
        dest="verify_output",
        metavar="PATH",
        default=None,
        help="write the selected report to an existing parent directory",
    )
    verify_parser.add_argument(
        "--config",
        dest="verify_config",
        metavar="PATH",
        default=None,
        help="read a local .coldstart.toml policy for the static preflight",
    )
    verify_parser.add_argument(
        "--strict",
        dest="verify_strict",
        action="store_true",
        default=None,
        help="apply strict policy to the static preflight",
    )
    verify_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "run tests through Docker network isolation with no host-runner fallback "
            "(or use the existing offline Docker-build mode)"
        ),
    )
    verify_parser.add_argument(
        "--timeout",
        dest="verify_timeout",
        type=int,
        default=30,
        metavar="SECONDS",
        help="bound the authorized process duration",
    )
    verify_parser.add_argument(
        "--output-limit",
        dest="verify_output_limit",
        type=int,
        default=65_536,
        metavar="BYTES",
        help="bound captured process output per stream",
    )
    authorization = verify_parser.add_mutually_exclusive_group()
    authorization.add_argument(
        "--authorize",
        action="store_true",
        help="explicitly authorize execution after reviewing the printed plan",
    )
    authorization.add_argument(
        "--plan",
        action="store_true",
        help="print the plan only; never launch a child process",
    )
    verify_parser.set_defaults(handler=_run_verify)

    return parser


def _run_version(_args: argparse.Namespace) -> int:
    print(_version_text())
    return 0


def _run_explain(args: argparse.Namespace) -> int:
    """Render one bundled check explanation without touching a repository."""

    try:
        explanation = explanation_for(args.check_id)
    except UnknownCheckError:
        print(
            f"ColdStart: unknown check ID: {safe_text(args.check_id)}",
            file=sys.stderr,
        )
        return 2
    sys.stdout.write(render_explanation(explanation))
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


def _verification_exit_code(static_exit_code: int, status: str, *, plan_only: bool) -> int:
    """Combine static preflight and explicit verification without false passes."""

    if static_exit_code in {2, 4}:
        return static_exit_code
    if plan_only or status == "passed":
        return static_exit_code
    if status == "failed":
        return static_exit_code if static_exit_code != 0 else 1
    if status in {"denied", "not_verified", "unavailable", "timeout", "incomplete"}:
        return static_exit_code if static_exit_code != 0 else 3
    return 4


def _verification_mapping(
    *,
    kind: str,
    plan: object | None = None,
    receipt: object | None = None,
    status: str,
    reason: str | None = None,
) -> dict[str, object]:
    """Build the additive verification section without changing P0 findings."""

    verification: dict[str, object] = {
        "requested": [kind],
        "authorized": [kind] if receipt is not None and getattr(receipt, "authorized", False) else [],
        "executions": [receipt.to_dict()] if receipt is not None else [],
        "status": status,
    }
    if plan is not None:
        verification["plan"] = plan.to_dict()
    if reason:
        verification["reason"] = safe_text(reason)
    return verification


def _run_verify(args: argparse.Namespace) -> int:
    """Run a static preflight, then optionally execute one reviewed plan."""

    output_format = args.verify_format or args.global_format or "terminal"
    output = args.verify_output or args.global_output
    config_path = args.verify_config or args.global_config
    strict = bool(args.verify_strict or args.global_strict)
    plan_only = bool(args.plan)
    authorize = bool(args.authorize)
    try:
        if args.verify_timeout <= 0:
            raise ExecutionValidationError("timeout must be a positive integer")
        if args.verify_timeout > MAX_TIMEOUT_SECONDS:
            raise ExecutionValidationError(
                f"timeout exceeds the safe maximum of {MAX_TIMEOUT_SECONDS}"
            )
        if args.verify_output_limit <= 0:
            raise ExecutionValidationError("output-limit must be a positive integer")
        if args.verify_output_limit > MAX_OUTPUT_LIMIT_BYTES:
            raise ExecutionValidationError(
                f"output-limit exceeds the safe maximum of {MAX_OUTPUT_LIMIT_BYTES}"
            )
        output_path = validate_output_path(output)
        static_result = run_audit(
            args.path,
            output_format=output_format,
            strict=strict,
            config_path=config_path,
        )
        plan = None
        receipt = None
        try:
            plan = build_execution_plan(
                static_result.boundary.root,
                args.kind,
                offline=bool(args.offline),
                timeout_seconds=args.verify_timeout,
                output_limit_bytes=args.verify_output_limit,
            )
        except ExecutionValidationError as error:
            verification = _verification_mapping(
                kind=args.kind,
                status="not_verified",
                reason=str(error),
            )
            report = replace(static_result.report, verification=verification)
            exit_code = _verification_exit_code(
                static_result.exit_code,
                "not_verified",
                plan_only=False,
            )
        else:
            if plan_only:
                verification = _verification_mapping(
                    kind=args.kind,
                    plan=plan,
                    status="planned",
                    reason="Plan-only preview; no child process was started.",
                )
                report = replace(static_result.report, verification=verification)
                exit_code = _verification_exit_code(
                    static_result.exit_code,
                    "planned",
                    plan_only=True,
                )
            else:
                receipt = execute_execution_plan(plan, authorize=authorize)
                verification = _verification_mapping(
                    kind=args.kind,
                    plan=plan,
                    receipt=receipt,
                    status=receipt.status,
                    reason=receipt.reason,
                )
                report = replace(static_result.report, verification=verification)
                exit_code = _verification_exit_code(
                    static_result.exit_code,
                    receipt.status,
                    plan_only=False,
                )

        rendered = serialize_report(report, output_format, exit_code=exit_code)
        if output_path is None:
            sys.stdout.write(rendered)
        else:
            write_report(rendered, output_path)
        return exit_code
    except (BoundaryValidationError, OutputValidationError, ExecutionValidationError) as error:
        print(f"ColdStart: {safe_text(error)}", file=sys.stderr)
        return 2
    except OSError:
        print("ColdStart: could not write the requested report output", file=sys.stderr)
        return 2
    except Exception:
        print("ColdStart: internal error while verifying", file=sys.stderr)
        return 4


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))
