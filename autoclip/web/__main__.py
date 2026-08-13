"""Launch AutoClip's local web studio with ``python -m autoclip.web``."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("autoclip.web.runtime:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
