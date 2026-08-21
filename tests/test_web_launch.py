from __future__ import annotations

from pathlib import Path

import pytest


class FakeServer:
    def __init__(self) -> None:
        self.run_calls = 0

    def run(self) -> None:
        self.run_calls += 1


def test_run_web_waits_for_health_then_opens_local_url() -> None:
    from autoclip.web.launch import run_web

    opened: list[str] = []
    server = FakeServer()
    health_urls: list[tuple[str, float]] = []

    result = run_web(
        server_factory=lambda host, port: server,
        health_waiter=lambda url, timeout_seconds: health_urls.append((url, timeout_seconds)),
        open_browser=opened.append,
    )

    assert result == 0
    assert server.run_calls == 1
    assert health_urls == [("http://127.0.0.1:8765/api/runtime-health", 15.0)]
    assert opened == ["http://127.0.0.1:8765/"]


def test_missing_static_assets_has_recovery_message(tmp_path: Path) -> None:
    from autoclip.web.launch import WebLaunchError, static_root_or_error

    with pytest.raises(WebLaunchError, match="build frontend assets"):
        static_root_or_error(tmp_path / "missing")


def test_cli_web_delegates_to_packaged_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    import autoclip.cli as cli
    from autoclip.web import launch

    calls: list[bool] = []
    monkeypatch.setattr(launch, "run_web", lambda: calls.append(True) or 0)

    cli.web()

    assert calls == [True]
