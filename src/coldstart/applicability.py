"""Applicability planning for the stable P0 catalog.

This module answers which adapter could evaluate each catalog entry.  It does
not run a rule and therefore cannot claim a catalog check passed or failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .catalog import CATALOG, CatalogEntry
from .discovery import DetectionResult


@dataclass(frozen=True)
class ApplicabilityDecision:
    check_id: str
    applicable: bool
    reason: str
    adapter: str
    status: str = "applicable"

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "applicable": self.applicable,
            "reason": self.reason,
            "adapter": self.adapter,
            "status": self.status,
        }


def _candidate_ids(detection: DetectionResult | Mapping[str, object]) -> tuple[str, ...]:
    if isinstance(detection, DetectionResult):
        ids = {
            member
            for candidate in detection.candidates
            for member in (candidate.members or (candidate.id,))
        }
        return tuple(sorted(ids))
    candidates = detection.get("candidates", [])
    ids: set[str] = set()
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            candidate_id = candidate.get("id")
            if isinstance(candidate_id, str):
                ids.add(candidate_id)
            members = candidate.get("members")
            if isinstance(members, list):
                ids.update(item for item in members if isinstance(item, str))
    return tuple(sorted(ids))


def _primary_id(detection: DetectionResult | Mapping[str, object]) -> str:
    if isinstance(detection, DetectionResult):
        return detection.primary
    primary = detection.get("primary")
    return primary if isinstance(primary, str) else (_candidate_ids(detection) or ("unknown",))[0]


def plan_applicability(
    detection: DetectionResult | Mapping[str, object],
    *,
    excluded_checks: Iterable[str] = (),
    catalog: Iterable[CatalogEntry] = CATALOG,
) -> tuple[ApplicabilityDecision, ...]:
    """Return one deterministic applicability decision for every catalog check."""

    candidate_ids = set(_candidate_ids(detection))
    primary = _primary_id(detection)
    excluded = set(excluded_checks)
    has_python = "python" in candidate_ids
    has_node = "node" in candidate_ids
    mixed = primary == "mixed" or (has_python and has_node)
    decisions: list[ApplicabilityDecision] = []

    for entry in sorted(catalog, key=lambda item: item.check_id):
        if entry.check_id in excluded:
            decisions.append(
                ApplicabilityDecision(
                    check_id=entry.check_id,
                    applicable=False,
                    reason="The configured policy excludes this check; no rule was run.",
                    adapter="policy",
                    status="skipped",
                )
            )
            continue

        if entry.check_id in {"CS-PROJECT-001", "CS-PROJECT-002"}:
            decisions.append(
                ApplicabilityDecision(
                    check_id=entry.check_id,
                    applicable=True,
                    reason="Bounded inventory and project signals are meaningful for every repository.",
                    adapter="generic",
                )
            )
            continue

        if entry.adapters == ("python",) and not has_python:
            if primary == "node":
                reason = "No Python candidate was detected; the Python adapter does not apply to this Node project."
            elif primary == "unknown":
                reason = "No Python candidate was detected; the repository type remains unknown."
            else:
                reason = "The detected project signals do not include a Python candidate."
            decisions.append(
                ApplicabilityDecision(
                    check_id=entry.check_id,
                    applicable=False,
                    reason=reason,
                    adapter="python",
                    status="not_applicable",
                )
            )
            continue

        python_specific = entry.adapters == ("python",)
        if python_specific and has_python and mixed:
            reason = "A Python candidate is present in a mixed repository; the Python adapter is applicable without selecting Node over it."
            adapter = "python"
        elif python_specific and has_python:
            reason = "A Python candidate was detected from bounded metadata signals."
            adapter = "python"
        elif has_python:
            reason = "Generic repository evidence applies to the detected Python candidate."
            adapter = "generic"
        elif has_node:
            reason = "The generic adapter applies to the detected Node candidate; Python-specific rule logic is not applicable."
            adapter = "generic"
        else:
            reason = "Generic repository evidence can be planned even though no supported ecosystem candidate was detected."
            adapter = "generic"
        decisions.append(
            ApplicabilityDecision(
                check_id=entry.check_id,
                applicable=True,
                reason=reason,
                adapter=adapter,
            )
        )

    return tuple(decisions)


decide_applicability = plan_applicability
build_applicability = plan_applicability


__all__ = [
    "ApplicabilityDecision",
    "build_applicability",
    "decide_applicability",
    "plan_applicability",
]
