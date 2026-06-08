"""Triage-specific rendering: focus a structure and snapshot it.

Unlike the rest of `core/`, this drives PyMOL — it's the one triage operation
that needs `cmd`. The pure triage state lives in `triage.py`.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import Image

from co_pymol.utils.pymol.render import apply_plddt_palette, render_image


def triage_render(cmd, path: Path, width: int = 800, height: int = 600) -> Image:
    """Focus on `path` (loading it if needed), hide siblings, color by pLDDT, render.

    Caller holds the pymol_session lock.
    """
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
    return render_image(cmd, width, height, ray=False)
