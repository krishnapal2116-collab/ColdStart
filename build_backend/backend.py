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
import tomllib
import zipfile
from typing import Any, cast


ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "coldstart"


def _project() -> dict[str, Any]:
    """Read the public project metadata used to build the wheel."""

    with (ROOT / "pyproject.toml").open("rb") as stream:
        document = tomllib.load(stream)
    project = document.get("project")
    if not isinstance(project, dict):
        raise RuntimeError("pyproject.toml does not contain [project] metadata")
    return cast(dict[str, Any], project)


PROJECT = _project()
DIST_NAME = str(PROJECT["name"])
VERSION = str(PROJECT["version"])
DIST_INFO = f"{DIST_NAME.replace('-', '_')}-{VERSION}.dist-info"
WHEEL_NAME = f"{DIST_NAME.replace('-', '_')}-{VERSION}-py3-none-any.whl"


def _metadata() -> str:
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {DIST_NAME}",
        f"Version: {VERSION}",
        f"Summary: {PROJECT.get('description', '')}",
    ]
    requires_python = PROJECT.get("requires-python")
    if requires_python:
        lines.append(f"Requires-Python: {requires_python}")
    for author in PROJECT.get("authors", []):
        if isinstance(author, dict):
            name = author.get("name")
            email = author.get("email")
            if name and email:
                lines.append(f"Author-email: {name} <{email}>")
            elif name:
                lines.append(f"Author: {name}")
    for dependency in PROJECT.get("dependencies", []):
        lines.append(f"Requires-Dist: {dependency}")
    for classifier in PROJECT.get("classifiers", []):
        lines.append(f"Classifier: {classifier}")
    for label, url in sorted(PROJECT.get("urls", {}).items()):
        lines.append(f"Project-URL: {label}, {url}")
    if PROJECT.get("readme"):
        lines.append("Description-Content-Type: text/markdown")
    return "\n".join(lines + [""])


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
    scripts = PROJECT.get("scripts", {})
    if not isinstance(scripts, dict):
        return ""
    lines = ["[console_scripts]"]
    lines.extend(f"{name} = {target}" for name, target in sorted(scripts.items()))
    return "\n".join(lines) + "\n"


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
        pth_name = f"__editable__.{DIST_NAME}-{VERSION}.pth"
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
