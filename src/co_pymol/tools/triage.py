"""Triage navigation MCP tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from co_pymol.core.session import AppSession
from co_pymol.core.triage_view import triage_render
from co_pymol.tools.errors import error_wrapper
from co_pymol.utils.pymol.helper import pymol_session


def register_triage_tools(mcp: FastMCP, session: AppSession) -> None:
    @mcp.tool()
    @error_wrapper
    def load_directory(path: str) -> str:
        """Scan a directory for structure files, extract metrics, and load all.

        Sets up triage navigation.
        """
        msg = session.triage.load_directory(path)
        session.sync_metrics_from_triage()
        with pymol_session() as cmd:
            cmd.delete("all")
            for f in session.triage.files:
                cmd.load(str(f), f.stem)
        return msg

    def _render_current() -> Image | str:
        p = session.triage.current_path()
        if p is None:
            return "Error: No structures loaded. Use load_directory first."
        with pymol_session() as cmd:
            return triage_render(cmd, p)

    @mcp.tool(structured_output=False)
    @error_wrapper
    def next_structure() -> Image | str:
        """Advance to next structure, load it, color by pLDDT, and render."""
        session.triage.next()
        return _render_current()

    @mcp.tool(structured_output=False)
    @error_wrapper
    def prev_structure() -> Image | str:
        """Go back to previous structure, load it, color by pLDDT, and render."""
        session.triage.prev()
        return _render_current()

    @mcp.tool(structured_output=False)
    @error_wrapper
    def go_to(number: int) -> Image | str:
        """Jump to Nth structure (1-indexed), load it, and render."""
        session.triage.go_to(number)
        return _render_current()

    @mcp.tool(structured_output=False)
    @error_wrapper
    def current() -> Image | str:
        """Re-render the current structure without advancing."""
        return _render_current()

    @mcp.tool()
    @error_wrapper
    def flag(note: str = "") -> str:
        """Flag the current structure with an optional note."""
        return session.triage.flag(note)

    @mcp.tool()
    @error_wrapper
    def show_flags() -> str:
        """List all flagged structures."""
        return session.triage.show_flags()

    @mcp.tool()
    @error_wrapper
    def export_flags() -> str:
        """Export all flags as JSON (with metrics)."""
        return session.triage.export_flags()

    @mcp.tool()
    @error_wrapper
    def filter(
        min_plddt: float, max_plddt: float, include_unscored: bool = False
    ) -> str:
        """Filter triage structures by pLDDT range.

        Unscored records excluded unless include_unscored=True.
        """
        return session.triage.filter(min_plddt, max_plddt, include_unscored)
