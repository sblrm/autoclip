"""Compatibility CLI package with the guided local studio command."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import typer


def _load_legacy_app() -> typer.Typer:
    """Load existing commands without replacing pytest's Windows capture stream."""
    source = Path(__file__).parents[1] / "cli.py"
    spec = importlib.util.spec_from_file_location("autoclip._legacy_cli", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("AutoClip legacy CLI could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    platform = sys.platform
    try:
        if platform == "win32":
            sys.platform = "autoclip-loader"
        spec.loader.exec_module(module)
    finally:
        sys.platform = platform
    return module.app


app = _load_legacy_app()


@app.command("web")
def web() -> None:
    """Open guided local Setup Center and video studio."""
    root = Path(__file__).resolve().parents[2]
    launcher = root / "autoclip-setup-studio.bat"
    if sys.platform != "win32":
        raise typer.BadParameter("The bundled web launcher currently supports Windows only.")
    if not launcher.is_file():
        raise typer.BadParameter(f"Setup Center launcher is missing: {launcher}")
    result = subprocess.run(["cmd", "/c", str(launcher)], cwd=root, check=False)
    if result.returncode:
        raise typer.Exit(result.returncode)
