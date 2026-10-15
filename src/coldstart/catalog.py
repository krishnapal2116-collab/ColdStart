"""Stable metadata for the M2 check catalog.

M2 only plans applicability.  The entries in this module describe the
catalog's public identities and adapters; they intentionally contain no rule
implementation or repository-reading logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    check_id: str
    name: str
    severity: str
    category: str
    adapters: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "severity": self.severity,
            "category": self.category,
            "adapters": list(self.adapters),
        }


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        "CS-PROJECT-001",
        "Project metadata discovery",
        "warning",
        "project",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-PROJECT-002",
        "Supported project type detection",
        "warning",
        "project",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-DEPS-001",
        "Dependency declaration discovery",
        "error",
        "dependencies",
        ("python",),
    ),
    CatalogEntry(
        "CS-DEPS-002",
        "Applicable lockfile presence",
        "error",
        "dependencies",
        ("python",),
    ),
    CatalogEntry(
        "CS-RUNTIME-001",
        "Runtime version declaration",
        "error",
        "runtime",
        ("python",),
    ),
    CatalogEntry(
        "CS-DOCS-001",
        "Setup documentation presence",
        "warning",
        "documentation",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-DOCS-002",
        "Test command documentation",
        "error",
        "documentation",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-CONFIG-001",
        "Configuration example discovery",
        "warning",
        "configuration",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-CONFIG-002",
        "Environment-variable documentation",
        "warning",
        "configuration",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-PORT-001",
        "Developer-specific absolute paths",
        "warning",
        "portability",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-SEC-001",
        "Potential secret exposure indicator",
        "error",
        "security",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-BUILD-001",
        "Container build configuration discovery",
        "info",
        "build",
        ("generic", "python", "node"),
    ),
    CatalogEntry(
        "CS-PATH-001",
        "Repository-contained path validation",
        "error",
        "portability",
        ("generic", "python", "node"),
    ),
)

CATALOG_CHECK_IDS = tuple(entry.check_id for entry in CATALOG)
CATALOG_BY_ID = {entry.check_id: entry for entry in CATALOG}


def catalog_entries() -> tuple[CatalogEntry, ...]:
    """Return catalog entries in their stable check-ID order."""

    return CATALOG


__all__ = [
    "CATALOG",
    "CATALOG_BY_ID",
    "CATALOG_CHECK_IDS",
    "CatalogEntry",
    "catalog_entries",
]
