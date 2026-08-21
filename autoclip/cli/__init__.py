"""Compatibility CLI package with the guided local studio command."""

from __future__ import annotations

import importlib.util
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
    """Open packaged local Studio in the default browser."""
    from autoclip.web.launch import run_web

    result = run_web()
    if result:
        raise typer.Exit(result)
