"""ColdStart package metadata and public version constants."""

from .audit import AuditOptions, AuditResult, audit, run_audit
from .applicability import ApplicabilityDecision, plan_applicability
from .config import ColdStartConfig, ConfigValidationError, load_config, parse_config
from .discovery import (
    DetectionCandidate,
    DetectionResult,
    FileRecord,
    InventoryResult,
    detect_projects,
    inventory_repository,
)
from .findings import (
    Applicability,
    AuditReport,
    Evidence,
    Finding,
    EVIDENCE_STRENGTH_VALUES,
    STATUS_VALUES,
)
from .version import (
    CHECK_CATALOG_VERSION,
    REPORT_SCHEMA_VERSION,
    __version__,
)

__all__ = [
    "CHECK_CATALOG_VERSION",
    "EVIDENCE_STRENGTH_VALUES",
    "REPORT_SCHEMA_VERSION",
    "STATUS_VALUES",
    "__version__",
    "Applicability",
    "ApplicabilityDecision",
    "AuditOptions",
    "AuditReport",
    "AuditResult",
    "Evidence",
    "ColdStartConfig",
    "ConfigValidationError",
    "DetectionCandidate",
    "DetectionResult",
    "FileRecord",
    "Finding",
    "InventoryResult",
    "audit",
    "detect_projects",
    "inventory_repository",
    "load_config",
    "parse_config",
    "plan_applicability",
    "run_audit",
]
