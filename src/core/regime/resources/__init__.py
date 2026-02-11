from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Optional


def resource_path(filename: str) -> Path:
    """Return a filesystem path to a packaged resource file."""
    return Path(resources.files(__package__) / filename)


def read_text(filename: str) -> str:
    """Read a packaged resource file as text."""
    return resource_path(filename).read_text(encoding="utf-8")


def default_config_path() -> Optional[str]:
    """Return the packaged default config path if available."""
    path = resource_path("regime_v1.yaml")
    if path.exists():
        return str(path)
    return None
