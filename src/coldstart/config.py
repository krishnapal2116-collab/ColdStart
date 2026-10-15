"""Fail-closed parsing for the optional ``.coldstart.toml`` policy.

Configuration is a data-only input.  The parser accepts the small documented
policy surface and rejects unknown keys, executable/remote settings, unsafe
paths, malformed values, and ambiguous aliases before discovery starts.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .boundary import (
    BoundaryLimits,
    BoundaryValidationError,
    normalize_exclusions,
    validate_limits,
)
from .catalog import CATALOG_CHECK_IDS


CONFIG_FILENAME = ".coldstart.toml"
CONFIG_MAX_BYTES = 64 * 1024
CONFIG_SCHEMA_VERSIONS = {"1", "1.0"}
POLICY_NAMES = {"default", "strict", "beginner", "ci"}
UNKNOWN_BEHAVIORS = {"allow", "review", "fail"}
FAIL_ON_VALUES = {"info", "warning", "error", "blocking"}
OUTPUT_FORMATS = {"terminal", "json"}


class ConfigValidationError(BoundaryValidationError):
    """A local policy is absent, malformed, unsafe, or ambiguous."""


@dataclass(frozen=True)
class ColdStartConfig:
    """Validated policy values used by the static audit composition root."""

    schema_version: str = "1.0"
    name: str = "default"
    strict: bool = False
    treat_not_verified_as: str = "review"
    fail_on: str = "error"
    required_checks: tuple[str, ...] = ()
    excluded_checks: tuple[str, ...] = ()
    limits: BoundaryLimits = BoundaryLimits()
    excludes: tuple[str, ...] = ()
    output_format: str = "terminal"
    source_path: str | None = None
    configured: bool = False

    def __post_init__(self) -> None:
        if self.schema_version not in CONFIG_SCHEMA_VERSIONS:
            raise ConfigValidationError("unsupported .coldstart.toml schema_version")
        if self.name not in POLICY_NAMES:
            raise ConfigValidationError("policy name is not supported")
        if not isinstance(self.strict, bool):
            raise ConfigValidationError("policy strict must be a boolean")
        if self.treat_not_verified_as not in UNKNOWN_BEHAVIORS:
            raise ConfigValidationError(
                "treat_not_verified_as must be allow, review, or fail"
            )
        if self.strict and self.treat_not_verified_as != "fail":
            raise ConfigValidationError(
                "strict policy must use treat_not_verified_as = 'fail'"
            )
        if self.fail_on not in FAIL_ON_VALUES:
            raise ConfigValidationError(
                "fail_on must be info, warning, error, or blocking"
            )
        if self.output_format not in OUTPUT_FORMATS:
            raise ConfigValidationError("output format must be terminal or json")
        object.__setattr__(self, "limits", validate_limits(self.limits))
        object.__setattr__(self, "excludes", normalize_exclusions(self.excludes))
        _validate_check_ids(self.required_checks, "required_checks")
        _validate_check_ids(self.excluded_checks, "excluded_checks")
        if set(self.required_checks) & set(self.excluded_checks):
            raise ConfigValidationError(
                "a check cannot be both required and excluded"
            )

    def as_dict(self) -> dict[str, object]:
        """Return safe, deterministic policy provenance for reports."""

        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "strict": self.strict,
            "treat_not_verified_as": self.treat_not_verified_as,
            "fail_on": self.fail_on,
            "required_checks": list(self.required_checks),
            "excluded_checks": list(self.excluded_checks),
            "limits": self.limits.as_dict(),
            "excludes": list(self.excludes),
            "output_format": self.output_format,
            "configured": self.configured,
        }


def _validate_check_ids(values: tuple[str, ...], field_name: str) -> None:
    if any(not isinstance(value, str) or not value for value in values):
        raise ConfigValidationError(f"{field_name} must contain non-empty strings")
    unknown = sorted(set(values) - set(CATALOG_CHECK_IDS))
    if unknown:
        raise ConfigValidationError(
            f"{field_name} contains unknown check ID: {unknown[0]}"
        )


def _require_table(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ConfigValidationError(f"{name} must be a TOML table")
    return value


def _require_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigValidationError(f"{name} must be a boolean")
    return value


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigValidationError(f"{name} must be an array of strings")
    return tuple(value)


def _reject_unsafe_keys(table: Mapping[str, object], *, context: str) -> None:
    dangerous_fragments = (
        "command",
        "exec",
        "executable",
        "network",
        "remote",
        "shell",
        "url",
        "run",
        "script",
        "process",
    )
    for key in table:
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in dangerous_fragments):
            raise ConfigValidationError(
                f"unsupported executable or remote setting: {context}.{key}"
            )


def _merge_aliases(table: Mapping[str, object], first: str, second: str) -> object | None:
    first_present = first in table
    second_present = second in table
    if first_present and second_present:
        raise ConfigValidationError(f"use only one of {first} and {second}")
    return table[first] if first_present else table.get(second)


def parse_config(text: str, *, source_path: str | None = None) -> ColdStartConfig:
    """Parse and validate bounded TOML text without touching repository code."""

    if not isinstance(text, str) or len(text.encode("utf-8")) > CONFIG_MAX_BYTES:
        raise ConfigValidationError(".coldstart.toml exceeds the bounded size")
    try:
        raw = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError) as error:
        raise ConfigValidationError(".coldstart.toml is malformed") from error
    if not isinstance(raw, dict):  # pragma: no cover - tomllib always returns dict
        raise ConfigValidationError(".coldstart.toml must contain a table")

    allowed = {
        "schema_version",
        "name",
        "policy",
        "strict",
        "treat_not_verified_as",
        "fail_on",
        "required_checks",
        "excluded_checks",
        "exclude",
        "excludes",
        "limits",
        "output",
    }
    _reject_unsafe_keys(raw, context="root")
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigValidationError(f"unsupported configuration key: {unknown[0]}")

    policy_values: dict[str, object] = {}
    if "policy" in raw:
        policy_table = _require_table(raw["policy"], "policy")
        _reject_unsafe_keys(policy_table, context="policy")
        policy_allowed = {
            "name",
            "strict",
            "treat_not_verified_as",
            "fail_on",
            "required_checks",
            "excluded_checks",
        }
        unknown_policy = sorted(set(policy_table) - policy_allowed)
        if unknown_policy:
            raise ConfigValidationError(
                f"unsupported policy key: {unknown_policy[0]}"
            )
        policy_values.update(policy_table)

    def choose(name: str, default: object) -> object:
        if name in raw and name in policy_values and raw[name] != policy_values[name]:
            raise ConfigValidationError(f"ambiguous duplicate policy setting: {name}")
        return raw.get(name, policy_values.get(name, default))

    schema_value = raw.get("schema_version", "1.0")
    if isinstance(schema_value, int) and not isinstance(schema_value, bool):
        schema_value = str(schema_value)
    schema_version = _require_string(schema_value, "schema_version")
    if schema_version not in CONFIG_SCHEMA_VERSIONS:
        raise ConfigValidationError("unsupported .coldstart.toml schema_version")

    name = _require_string(choose("name", "default"), "policy name")
    if name not in POLICY_NAMES:
        raise ConfigValidationError("policy name is not supported")
    strict = _require_bool(choose("strict", False), "strict")
    unknown_behavior = _require_string(
        choose("treat_not_verified_as", "review"), "treat_not_verified_as"
    )
    fail_on = _require_string(choose("fail_on", "error"), "fail_on")

    required = _string_list(choose("required_checks", []), "required_checks")
    excluded_checks = _string_list(
        choose("excluded_checks", []), "excluded_checks"
    )

    exclusion_value = _merge_aliases(raw, "exclude", "excludes")
    excludes = normalize_exclusions(
        [] if exclusion_value is None else _string_list(exclusion_value, "excludes")
    )

    limits_value = raw.get("limits", {})
    limits_table = _require_table(limits_value, "limits")
    _reject_unsafe_keys(limits_table, context="limits")
    allowed_limits = {"max_files", "max_bytes", "max_total_bytes", "max_depth", "max_seconds"}
    unknown_limits = sorted(set(limits_table) - allowed_limits)
    if unknown_limits:
        raise ConfigValidationError(f"unsupported limit: {unknown_limits[0]}")
    limits_mapping = dict(limits_table)
    try:
        limits = validate_limits(limits_mapping)
    except BoundaryValidationError as error:
        raise ConfigValidationError(str(error)) from error

    output_value = raw.get("output", "terminal")
    if isinstance(output_value, dict):
        _reject_unsafe_keys(output_value, context="output")
        unknown_output = sorted(set(output_value) - {"format"})
        if unknown_output:
            raise ConfigValidationError(
                f"unsupported output setting: {unknown_output[0]}"
            )
        output_value = output_value.get("format", "terminal")
    output_format = _require_string(output_value, "output format")

    return ColdStartConfig(
        schema_version=schema_version,
        name=name,
        strict=strict,
        treat_not_verified_as=unknown_behavior,
        fail_on=fail_on,
        required_checks=tuple(sorted(set(required))),
        excluded_checks=tuple(sorted(set(excluded_checks))),
        limits=limits,
        excludes=excludes,
        output_format=output_format,
        source_path=source_path,
        configured=True,
    )


def _read_bounded(path: Path) -> str:
    try:
        if path.is_symlink():
            raise ConfigValidationError("configuration symlinks are not followed")
        with path.open("rb") as handle:
            data = handle.read(CONFIG_MAX_BYTES + 1)
    except ConfigValidationError:
        raise
    except (OSError, UnicodeError) as error:
        raise ConfigValidationError("configuration file cannot be read") from error
    if len(data) > CONFIG_MAX_BYTES:
        raise ConfigValidationError(".coldstart.toml exceeds the bounded size")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConfigValidationError(".coldstart.toml must be UTF-8 text") from error


def load_config(
    repository_root: Path | str,
    config_path: Path | str | None = None,
) -> ColdStartConfig:
    """Load the explicit policy or the repository-root ``.coldstart.toml``.

    An absent optional file is the safe default.  An explicitly requested file
    must exist and pass all validation; no parent directories are created.
    """

    root = Path(repository_root)
    explicit = config_path is not None
    candidate = Path(config_path) if explicit else root / CONFIG_FILENAME
    if not explicit and not candidate.exists():
        return ColdStartConfig()
    try:
        if not candidate.is_file():
            raise ConfigValidationError("configuration path is not a file")
    except OSError as error:
        raise ConfigValidationError("configuration path cannot be inspected") from error
    # Keep report provenance safe even when an explicit config is outside the
    # repository; the file itself is still bounded and data-only.
    source_label = CONFIG_FILENAME if candidate == root / CONFIG_FILENAME else "<provided-config>"
    return parse_config(_read_bounded(candidate), source_path=source_label)


__all__ = [
    "CONFIG_FILENAME",
    "CONFIG_MAX_BYTES",
    "ColdStartConfig",
    "ConfigValidationError",
    "load_config",
    "parse_config",
]
