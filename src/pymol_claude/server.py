"""FastMCP server exposing PyMOL's cmd module as MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP

from pymol_claude.core.session import AppSession
from pymol_claude.instructions import MCP_INSTRUCTIONS
from pymol_claude.tools.metrics import register_metrics_tools
from pymol_claude.tools.render import register_render_tools
from pymol_claude.tools.run import register_run_tool
from pymol_claude.tools.triage import register_triage_tools


def create_server() -> FastMCP:
    """Create and configure the FastMCP server with all PyMOL tools."""
    session = AppSession()
    mcp = FastMCP("pymol-claude", instructions=MCP_INSTRUCTIONS)

    register_render_tools(mcp)
    register_metrics_tools(mcp, session)
    register_triage_tools(mcp, session)
    register_run_tool(mcp)

    return mcp
