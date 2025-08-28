"""
Utilities for per-plugin virtualenv path isolation.

This module provides helpers to locate a plugin's venv site-packages and a
context manager that temporarily prepends those paths to sys.path to isolate
imports when loading drivers. Global sys.path is restored after use.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List
import sys
import os


def _candidate_site_packages(venv_dir: Path) -> List[Path]:
    paths: List[Path] = []
    # Linux/macOS style: .venv/lib/pythonX.Y/site-packages or lib64
    lib_dir = venv_dir / "lib"
    if lib_dir.exists():
        for child in lib_dir.iterdir():
            if child.is_dir() and child.name.startswith("python"):
                sp = child / "site-packages"
                if sp.exists():
                    paths.append(sp)
        # lib64 variant
        lib64_dir = venv_dir / "lib64"
        if lib64_dir.exists():
            for child in lib64_dir.iterdir():
                if child.is_dir() and child.name.startswith("python"):
                    sp = child / "site-packages"
                    if sp.exists():
                        paths.append(sp)
    # Windows style: .venv/Lib/site-packages
    win_sp = venv_dir / "Lib" / "site-packages"
    if win_sp.exists():
        paths.append(win_sp)
    # Ensure uniqueness while preserving order
    seen = set()
    unique_paths: List[Path] = []
    for p in paths:
        if str(p) not in seen:
            seen.add(str(p))
            unique_paths.append(p)
    return unique_paths


def get_plugin_site_packages(plugin_dir: Path) -> List[Path]:
    """Return a list of site-packages paths inside the plugin's .venv, if present."""
    venv_dir = plugin_dir / ".venv"
    if not venv_dir.exists() or not venv_dir.is_dir():
        return []
    return _candidate_site_packages(venv_dir)


@contextmanager
def plugin_import_path(plugin_dir: Path) -> Iterator[None]:
    """
    Context manager that prepends the plugin venv site-packages to sys.path.

    Restores sys.path after context exit.
    """
    to_add = [str(p) for p in get_plugin_site_packages(plugin_dir)]
    removed: List[str] = []
    try:
        for p in reversed(to_add):  # keep original order when inserting at front
            if p not in sys.path:
                sys.path.insert(0, p)
                removed.append(p)
        yield
    finally:
        # Remove only what we added
        for p in removed:
            try:
                if p in sys.path:
                    sys.path.remove(p)
            except Exception:
                pass

