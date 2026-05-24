"""PyMOL plugin entry point for pymol-claude.

Exposes PyMOL's Python API as an MCP server so any MCP client
(Cursor, Claude Code, Claude Desktop, etc.) can drive PyMOL.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

# Ensure the pymol_claude package is importable even when loaded as a PyMOL
# startup plugin from the app bundle. The project root (parent of pymol_claude/)
# must be on sys.path so that "from pymol_claude.mcp_server import ..." works.
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

server_thread: Optional[threading.Thread] = None


def __init_plugin__(app=None):
    """Called by PyMOL's plugin system on startup."""
    start_mcp()


def start_mcp(port: int = 8766):
    """Start the MCP server in a background thread.

    Can be called from PyMOL command line: start_mcp [port]
    """
    global server_thread

    if server_thread is not None and server_thread.is_alive():
        print("pymol-claude: MCP server is already running")
        return

    import os
    os.environ["FASTMCP_LOG_LEVEL"] = "WARNING"

    from pymol_claude.mcp_server import create_server

    server = create_server()
    port = int(port)

    server_thread = threading.Thread(
        target=server.run,
        kwargs={"transport": "sse", "host": "127.0.0.1", "port": port, "log_level": "warning"},
        daemon=True,
    )
    server_thread.start()

    print(f"pymol-claude: MCP server running on http://127.0.0.1:{port}/sse")


def stop_mcp():
    """Stop the MCP server.

    Note: daemon thread will die when PyMOL exits. This just clears the reference.
    """
    global server_thread
    if server_thread is None or not server_thread.is_alive():
        print("pymol-claude: MCP server is not running")
        return

    # Daemon threads can't be cleanly stopped; they die with the process.
    # Clear the reference so start_mcp can be called again.
    server_thread = None
    print("pymol-claude: Server reference cleared (thread will stop on PyMOL exit)")


# Register PyMOL commands
try:
    from pymol import cmd
    cmd.extend("start_mcp", start_mcp)
    cmd.extend("stop_mcp", stop_mcp)
except ImportError:
    # Not running inside PyMOL (e.g., during pip install)
    pass
