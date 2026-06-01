"""PyMOL plugin entry point for pylot.

Exposes PyMOL's Python API as an MCP server so any MCP client
(Cursor, Claude Code, Claude Desktop, etc.) can drive PyMOL.
"""

from __future__ import annotations

import threading

from pylot.cli import server_url
from pylot.constants import DEFAULT_HOST, DEFAULT_PORT

server_thread: threading.Thread | None = None


def __init_plugin__(app=None):
    """Called by PyMOL's plugin system on startup."""
    from pymol import cmd

    cmd.extend("start_mcp", start_mcp)
    start_mcp()


def start_mcp(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST):
    """Start the MCP server in a background thread.

    Can be called from PyMOL command line: start_mcp [port [host]]
    """
    global server_thread

    if server_thread is not None and server_thread.is_alive():
        print("pylot: MCP server is already running")
        return

    # Deferred so that `import pylot` (and thus the stdlib-only CLI) doesn't
    # pull in mcp/pymol, which only exist inside PyMOL's bundled interpreter.
    from pylot.server import create_server

    # PyMOL's command extension passes all args as strings (`start_mcp 9000`).
    port = int(port)
    server = create_server(host=host, port=port, log_level="WARNING")

    server_thread = threading.Thread(
        target=server.run,
        kwargs={"transport": "sse"},
        daemon=True,
    )
    server_thread.start()

    print(f"pylot: MCP server running on {server_url(host, port)}")
