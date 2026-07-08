"""bAInary GUI CLI entry point.

``bainary-gui`` resolves to :func:`main`, which starts a uvicorn server
bound to ``GUI_HOST:GUI_PORT`` (defaults: 127.0.0.1:8787). It opens the
default browser unless ``--no-browser`` is passed.
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from pathlib import Path

log = logging.getLogger(__name__)


def _env_path() -> Path:
    return Path.cwd() / ".env"


def main() -> None:
    """Parse CLI args and start the uvicorn server."""
    p = argparse.ArgumentParser(prog="bainary-gui", description="bAInary web GUI")
    p.add_argument("--host", default=None, help="Bind host (overrides GUI_HOST)")
    p.add_argument("--port", type=int, default=None, help="Bind port (overrides GUI_PORT)")
    p.add_argument("--no-browser", action="store_true", help="Do not open the default browser")
    p.add_argument("--reload", action="store_true", help="Reload on file changes (dev)")
    args = p.parse_args()

    # Read .env if present (best effort).
    host = args.host
    port = args.port
    env_path = _env_path()
    if env_path.exists():
        try:
            from dotenv import dotenv_values

            vals = dotenv_values(env_path)
            if host is None and vals.get("GUI_HOST"):
                host = vals["GUI_HOST"]
            if port is None and vals.get("GUI_PORT"):
                port = int(vals["GUI_PORT"] or 0)
        except Exception as e:
            log.warning("could not read .env: %s", e)
    if host is None:
        host = "127.0.0.1"
    if port is None:
        port = 8787

    if not args.no_browser:
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception as e:
            log.warning("could not open browser: %s", e)

    import uvicorn

    print(f"bAInary GUI on http://{host}:{port}", file=sys.stderr)
    uvicorn.run(
        "bainary.gui.server:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
