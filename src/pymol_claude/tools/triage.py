"""Triage navigation MCP tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from pymol_claude.core.session import AppSession
from pymol_claude.utils.pymol_helpers import ensure_pymol, pymol_lock, triage_render


def register_triage_tools(mcp: FastMCP, session: AppSession) -> None:
    @mcp.tool()
    def load_directory(path: str) -> str:
        """Scan a directory for structure files, extract metrics, and load all.

        Sets up triage navigation.
        """
        cmd = ensure_pymol()
        try:
            msg = session.triage.load_directory(path)
        except OSError as e:
            return f"Error: {e}"
        session.sync_metrics_from_triage()
        with pymol_lock:
            cmd.delete("all")
            for f in session.triage.files:
                cmd.load(str(f), f.stem)
        return msg

    def _render_current() -> Image | str:
        p = session.triage.current_path()
        if p is None:
            return "Error: No structures loaded. Use load_directory first."
        try:
            with pymol_lock:
                return triage_render(p)
        except RuntimeError as e:
            return f"Error: {e}"

    @mcp.tool(structured_output=False)
    def next_structure() -> Image | str:
        """Advance to next structure, load it, color by pLDDT, and render."""
        session.triage.next()
        return _render_current()

    @mcp.tool(structured_output=False)
    def prev_structure() -> Image | str:
        """Go back to previous structure, load it, color by pLDDT, and render."""
        session.triage.prev()
        return _render_current()

    @mcp.tool(structured_output=False)
    def go_to(number: int) -> Image | str:
        """Jump to Nth structure (1-indexed), load it, and render."""
        session.triage.go_to(number)
        return _render_current()

    @mcp.tool(structured_output=False)
    def current() -> Image | str:
        """Re-render the current structure without advancing."""
        return _render_current()

    @mcp.tool()
    def flag(note: str = "") -> str:
        """Flag the current structure with an optional note."""
        return session.triage.flag(note)

    @mcp.tool()
    def show_flags() -> str:
        """List all flagged structures."""
        return session.triage.show_flags()

    @mcp.tool()
    def export_flags() -> str:
        """Export all flags as JSON (with metrics)."""
        return session.triage.export_flags()

    @mcp.tool()
    def filter(
        min_plddt: float, max_plddt: float, include_unscored: bool = False
    ) -> str:
        """Filter triage structures by pLDDT range.

        Unscored records excluded unless include_unscored=True.
        """
        return session.triage.filter(min_plddt, max_plddt, include_unscored)
