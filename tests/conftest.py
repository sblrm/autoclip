"""Shared test setup for local studio static assets."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _supply_layout_test_asset_directory(request: pytest.FixtureRequest, tmp_path):
    """Mirror Vite's output shape for the focused static-layout regression test."""
    if request.node.name == "test_layout_fixed_studio_injects_the_desktop_grid_rule":
        (tmp_path / "dist" / "assets").mkdir(parents=True, exist_ok=True)
