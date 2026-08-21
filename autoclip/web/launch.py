"""Packaged localhost launcher for the AutoClip browser studio."""

from __future__ import annotations

import socket
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from typing import Any, Protocol
from urllib.request import urlopen


class WebLaunchError(RuntimeError):
    """The local Studio cannot start with a useful recovery message."""


class LocalServer(Protocol):
    def run(self) -> None: ...


ServerFactory = Callable[[str, int], LocalServer]
HealthWaiter = Callable[[str, float], None]


def static_root_or_error(root: Path | None = None) -> Path:
    static_root = root or Path(__file__).resolve().parent / "static"
    if not (static_root / "index.html").is_file():
        raise WebLaunchError(
            "Studio assets are missing; build frontend assets with `npm.cmd run build` from web/."
        )
    return static_root


def find_available_local_port(host: str, preferred_port: int) -> int:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise WebLaunchError("AutoClip Studio only serves localhost.")
    for port in (preferred_port, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return int(probe.getsockname()[1])
    raise WebLaunchError("No local port is available for AutoClip Studio.")


def wait_for_health(
    url: str,
    timeout_seconds: float = 15.0,
    request: Callable[..., Any] = urlopen,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with request(url, timeout=1.0) as response:
                if getattr(response, "status", 200) == 200:
                    return
        except Exception as error:  # Local server may still be binding its port.
            last_error = error
        time.sleep(0.1)
    detail = f" ({type(last_error).__name__})" if last_error is not None else ""
    raise WebLaunchError(f"AutoClip Studio did not become ready within {timeout_seconds:.0f} seconds{detail}.")


def make_server(host: str, port: int) -> LocalServer:
    static_root = static_root_or_error()
    from autoclip.web.usable_studio import create_usable_studio

    try:
        import uvicorn
    except ImportError as error:
        raise WebLaunchError("Web runtime is missing; install AutoClip web dependencies.") from error
    config = uvicorn.Config(
        create_usable_studio(dist=static_root),
        host=host,
        port=port,
        log_level="info",
    )
    return uvicorn.Server(config)


def run_web(
    *,
    host: str = "127.0.0.1",
    preferred_port: int = 8765,
    server_factory: ServerFactory = make_server,
    health_waiter: HealthWaiter = wait_for_health,
    open_browser: Callable[[str], bool] = webbrowser.open,
) -> int:
    """Run one localhost server, wait for health, then open its browser Home."""
    port = find_available_local_port(host, preferred_port)
    url = f"http://{host}:{port}/"
    server = server_factory(host, port)
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    try:
        health_waiter(f"{url}api/runtime-health", 15.0)
        open_browser(url)
        thread.join()
        return 0
    except Exception:
        if hasattr(server, "should_exit"):
            setattr(server, "should_exit", True)
        thread.join(timeout=2.0)
        raise
