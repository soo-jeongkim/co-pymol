"""PyMOL plugin entry point for pymol-claude.

Exposes PyMOL's Python API as an MCP server so Claude can control PyMOL
from any MCP client (Claude Code, claude.ai, mobile app).
"""

from __future__ import annotations

import threading
from typing import Optional

_server_thread: Optional[threading.Thread] = None


def __init_plugin__(app=None):
    """Called by PyMOL's plugin system on startup."""
    start_claude()


def start_claude(port: int = 8766):
    """Start the MCP server in a background thread.

    Can be called from PyMOL command line: start_claude [port]
    """
    global _server_thread

    if _server_thread is not None and _server_thread.is_alive():
        print("pymol-claude: MCP server is already running")
        return

    from pymol_claude.mcp_server import create_server

    server = create_server()
    port = int(port)

    _server_thread = threading.Thread(
        target=server.run,
        kwargs={"transport": "sse", "host": "0.0.0.0", "port": port},
        daemon=True,
    )
    _server_thread.start()

    print(f"pymol-claude: MCP server running on http://0.0.0.0:{port}/sse")
    print(f"pymol-claude: WARNING — server binds 0.0.0.0 (all interfaces)")


def stop_claude():
    """Stop the MCP server.

    Note: daemon thread will die when PyMOL exits. This just clears the reference.
    """
    global _server_thread
    if _server_thread is None or not _server_thread.is_alive():
        print("pymol-claude: MCP server is not running")
        return

    # Daemon threads can't be cleanly stopped; they die with the process.
    # Clear the reference so start_claude can be called again.
    _server_thread = None
    print("pymol-claude: server reference cleared (thread will stop on PyMOL exit)")


# Register PyMOL commands
try:
    from pymol import cmd
    cmd.extend("start_claude", start_claude)
    cmd.extend("stop_claude", stop_claude)
except ImportError:
    # Not running inside PyMOL (e.g., during pip install)
    pass
