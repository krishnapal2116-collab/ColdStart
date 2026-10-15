"""Small dependency-free PEP 517/660 backend for the Phase 1 package.

ColdStart deliberately keeps its Phase 1 build path independent of a third-party
build backend. The backend creates a pure-Python wheel and an editable wheel
using only the Python standard library.
"""

from __future__ import annotations

import base64
import hashlib
import os
import pathlib
import zipfile


ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "coldstart"
DIST_NAME = "coldstart"
DIST_INFO = "coldstart-0.1.0.dist-info"
WHEEL_NAME = "coldstart-0.1.0-py3-none-any.whl"


def _metadata() -> str:
    return "\n".join(
        (
            "Metadata-Version: 2.1",
            "Name: coldstart",
            "Version: 0.1.0",
            "Summary: A local-first software-repository reproducibility auditor.",
            "Requires-Python: >=3.12,<3.13",
            "",
        )
    )


def _wheel_metadata() -> str:
    return "\n".join(
        (
            "Wheel-Version: 1.0",
            "Generator: coldstart.phase1.backend",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
            "",
        )
    )


def _entry_points() -> str:
    return "[console_scripts]\ncoldstart = coldstart.cli:main\n"


def _digest(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return f"sha256={encoded.decode('ascii')}"


def _wheel_bytes(editable: bool) -> dict[str, bytes]:
    files: dict[str, bytes] = {
        f"{DIST_INFO}/METADATA": _metadata().encode(),
        f"{DIST_INFO}/WHEEL": _wheel_metadata().encode(),
        f"{DIST_INFO}/entry_points.txt": _entry_points().encode(),
    }
    if editable:
        pth_name = "__editable__.coldstart-0.1.0.pth"
        files[pth_name] = (str(SOURCE.parent) + os.linesep).encode()
    else:
        for path in sorted(SOURCE.rglob("*.py")):
            files[path.relative_to(SOURCE.parent).as_posix()] = path.read_bytes()

    record_lines = []
    for name, data in sorted(files.items()):
        record_lines.append(f"{name},{_digest(data)},{len(data)}")
    record_lines.append(f"{DIST_INFO}/RECORD,,")
    files[f"{DIST_INFO}/RECORD"] = ("\n".join(record_lines) + "\n").encode()
    return files


def _write_wheel(wheel_directory: str, editable: bool) -> str:
    destination = pathlib.Path(wheel_directory) / WHEEL_NAME
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for name, data in _wheel_bytes(editable).items():
            wheel.writestr(name, data)
    return WHEEL_NAME


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_editable(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    return _prepare_metadata(metadata_directory)


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return _prepare_metadata(metadata_directory)


def _prepare_metadata(metadata_directory: str) -> str:
    target = pathlib.Path(metadata_directory) / DIST_INFO
    target.mkdir(parents=True, exist_ok=True)
    (target / "METADATA").write_text(_metadata(), encoding="utf-8")
    (target / "WHEEL").write_text(_wheel_metadata(), encoding="utf-8")
    (target / "entry_points.txt").write_text(_entry_points(), encoding="utf-8")
    return DIST_INFO


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _write_wheel(wheel_directory, editable=False)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _write_wheel(wheel_directory, editable=True)
