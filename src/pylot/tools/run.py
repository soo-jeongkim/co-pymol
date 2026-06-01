"""Escape-hatch MCP tool for arbitrary PyMOL Python."""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from mcp.server.fastmcp import FastMCP

from pylot.tools.errors import error_wrapper
from pylot.utils.pymol.helper import pymol_session


def register_run_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @error_wrapper
    def run(code: str) -> str:
        """Execute arbitrary Python code with `cmd` (the PyMOL command module) bound.

        Use `cmd.do(...)` for PyMOL CLI syntax. Output from print() is returned.
        Examples:
            run("cmd.load('foo.cif')")
            run("cmd.show('cartoon'); cmd.color('salmon', 'chain A')")
            run("import numpy as np; print(np.mean(...))")

        Security: this runs arbitrary Python locally on your machine — full imports,
        file I/O, and PyMOL access. Only connect trusted MCP clients.
        """
        buf = io.StringIO()
        with pymol_session() as cmd, redirect_stdout(buf):
            exec(code, {"cmd": cmd})
        output = buf.getvalue()
        return output if output.strip() else "OK"
