"""MCP server exposing PyMOL's cmd module as MCP tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from co_pymol.constants import DEFAULT_HOST, DEFAULT_PORT
from co_pymol.core.session import AppSession
from co_pymol.instructions import MCP_INSTRUCTIONS
from co_pymol.tools.metrics import register_metrics_tools
from co_pymol.tools.render import register_render_tools
from co_pymol.tools.run import register_run_tool
from co_pymol.tools.triage import register_triage_tools


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    log_level: str = "WARNING",
) -> FastMCP:
    """Create and configure the MCP server with all PyMOL tools.

    Transport settings (host/port/log_level) are passed to the server here;
    the SDK's FastMCP reads them from its Settings rather than from run().
    """
    session = AppSession()
    mcp = FastMCP(
        "co-pymol",
        instructions=MCP_INSTRUCTIONS,
        host=host,
        port=port,
        log_level=log_level,
    )

    register_render_tools(mcp)
    register_metrics_tools(mcp, session)
    register_triage_tools(mcp, session)
    register_run_tool(mcp)

    return mcp
