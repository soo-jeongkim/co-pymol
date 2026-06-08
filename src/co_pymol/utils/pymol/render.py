"""Rendering primitives: snapshot the current view, color by pLDDT."""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path

from mcp.server.fastmcp import Image

from co_pymol.constants import (
    PLDDT_PALETTE,
    RENDER_POLL_ATTEMPTS,
    RENDER_POLL_INTERVAL_S,
)


def apply_plddt_palette(cmd, selection: str = "all") -> None:
    """Color selection by pLDDT (b-factor 0–100, project palette)."""
    cmd.spectrum("b", PLDDT_PALETTE, selection, 0, 100)


def render_image(cmd, width: int, height: int, ray: bool = False) -> Image:
    """Render current PyMOL view to an Image. Caller holds the pymol_session lock."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if ray:
            cmd.ray(width, height)
        else:
            cmd.draw(width, height, antialias=2)
        cmd.png(tmp_path, dpi=150)

        # In GUI mode the PNG is written on PyMOL's main thread at the next
        # redraw, not by this worker thread's cmd.png call — poll for the file.
        for _ in range(RENDER_POLL_ATTEMPTS):
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                break
            time.sleep(RENDER_POLL_INTERVAL_S)
        else:
            timeout_s = RENDER_POLL_ATTEMPTS * RENDER_POLL_INTERVAL_S
            raise RuntimeError(
                f"Render timed out after {timeout_s:.1f}s (PNG file never appeared)"
            )

        data = Path(tmp_path).read_bytes()
        if not data:
            raise RuntimeError("Render produced an empty PNG file")
        return Image(data=data, format="png")
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
