"""Rendering MCP tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from pymol_claude.utils.pymol_helpers import (
    apply_plddt_palette,
    ensure_pymol,
    pymol_lock,
    render_image,
)


def register_render_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def color_by_plddt(selection: str = "all") -> str:
        """Color by pLDDT (B-factor 0–100) with the project palette.

        Blue = high confidence, red = low.
        """
        cmd = ensure_pymol()
        with pymol_lock:
            apply_plddt_palette(cmd, selection)
            return f"Colored {selection} by pLDDT"

    @mcp.tool(structured_output=False)
    def render(width: int = 800, height: int = 600, ray: bool = True) -> Image | str:
        """Render current view as an image. ray=True for high quality (slower)."""
        try:
            with pymol_lock:
                return render_image(width, height, ray=ray)
        except RuntimeError as e:
            return f"Error: {e}"

    @mcp.tool(structured_output=False)
    def snapshot(width: int = 800, height: int = 600) -> Image | str:
        """Quick snapshot without ray tracing. Faster, lower quality."""
        try:
            with pymol_lock:
                return render_image(width, height, ray=False)
        except RuntimeError as e:
            return f"Error: {e}"
