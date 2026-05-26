"""PyMOL access, rendering, and thread lock."""

from __future__ import annotations

import contextlib
import os
import tempfile
import threading
import time
from pathlib import Path

from mcp.server.fastmcp import Image

from pymol_claude.config import (
    PLDDT_PALETTE,
    RENDER_POLL_ATTEMPTS,
    RENDER_POLL_INTERVAL_S,
)

pymol_lock = threading.Lock()


def ensure_pymol():
    """Import pymol.cmd, raising a clear error if unavailable."""
    try:
        from pymol import cmd

        return cmd
    except ImportError as err:
        raise RuntimeError(
            "PyMOL is not installed. Install it with: "
            "/Applications/PyMOL.app/Contents/bin/python -m pip install -e ."
        ) from err


def apply_plddt_palette(cmd, selection: str = "all") -> None:
    """Color selection by pLDDT (b-factor 0–100, project palette)."""
    cmd.spectrum("b", PLDDT_PALETTE, selection, 0, 100)


def render_image(width: int, height: int, ray: bool = False) -> Image:
    """Render current PyMOL view to an Image. Must be called with pymol_lock held."""
    cmd = ensure_pymol()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if ray:
            cmd.ray(width, height)
        else:
            cmd.draw(width, height, antialias=2)
        cmd.png(tmp_path, dpi=150)

        # PyMOL's png command may be async; wait for file
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


def triage_render(path: Path, width: int = 800, height: int = 600) -> Image:
    """Focus on `path` (loading it if needed), hide siblings, color by pLDDT, render.

    Must be called with pymol_lock held.
    """
    cmd = ensure_pymol()
    obj_name = path.stem
    if obj_name not in cmd.get_object_list():
        cmd.load(str(path), obj_name)
    cmd.disable("all")
    cmd.enable(obj_name)
    cmd.show("cartoon", obj_name)
    cmd.hide("lines", obj_name)
    apply_plddt_palette(cmd, obj_name)
    cmd.orient(obj_name)
    cmd.bg_color("white")
    return render_image(width, height, ray=False)
