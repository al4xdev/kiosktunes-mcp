"""Resolve checkout-only locations so installed copies never write into site-packages."""

from __future__ import annotations

from pathlib import Path


def source_root() -> Path | None:
    """Return the repository root when running from a source checkout, otherwise None.

    Installed copies (pip, `uv tool install`, `uvx`) live in site-packages, three
    levels below a directory that may be read-only. The `pyproject.toml` marker
    keeps checkout-specific behaviour from leaking into those installs.
    """
    candidate = Path(__file__).resolve().parent.parent.parent
    if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir():
        return candidate
    return None
