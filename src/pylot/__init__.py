"""PyMOL plugin entry point for pylot.

Exposes PyMOL's Python API as an MCP server so any MCP client
(Cursor, Claude Code, Claude Desktop, etc.) can drive PyMOL.
"""

from __future__ import annotations

import threading

from pylot.config import DEFAULT_HOST, DEFAULT_PORT

server_thread: threading.Thread | None = None


def __init_plugin__(app=None):
    """Called by PyMOL's plugin system on startup."""
    from pymol import cmd

    cmd.extend("start_mcp", start_mcp)
    start_mcp()


def start_mcp(port: int = DEFAULT_PORT):
    """Start the MCP server in a background thread.

    Can be called from PyMOL command line: start_mcp [port]
    """
    global server_thread

    if server_thread is not None and server_thread.is_alive():
        print("pylot: MCP server is already running")
        return

    from pylot.server import create_server

    port = int(port)
    server = create_server(host=DEFAULT_HOST, port=port, log_level="WARNING")

    server_thread = threading.Thread(
        target=server.run,
        kwargs={"transport": "sse"},
        daemon=True,
    )
    server_thread.start()

    print(f"pylot: MCP server running on http://{DEFAULT_HOST}:{port}/sse")
