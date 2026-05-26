"""Escape-hatch MCP tool for arbitrary PyMOL Python."""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from fastmcp import FastMCP

from pymol_claude.utils.pymol_helpers import ensure_pymol, pymol_lock

# Restricted builtins for run() — enough for PyMOL scripting, not general Python.
# No imports, open(), exec(), eval(), etc. Full PyMOL access remains via `cmd`.
RUN_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def register_run_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    def run(code: str) -> str:
        """Execute Python code with restricted builtins.

        `cmd` is the PyMOL command module; use `cmd.do(...)` for PyMOL CLI syntax.
        Output from print() is returned. Examples:
            run("cmd.load('foo.cif')")
            run("cmd.show('cartoon'); cmd.color('salmon', 'chain A')")

        Security: runs locally on your machine with no imports or file I/O builtins,
        but full PyMOL access via `cmd`. Only connect trusted MCP clients.
        """
        cmd = ensure_pymol()
        buf = io.StringIO()
        with pymol_lock:
            try:
                with redirect_stdout(buf):
                    exec(
                        code,
                        {"cmd": cmd, "__builtins__": RUN_BUILTINS},
                    )
            except Exception as e:
                return f"Error: {e}"
        output = buf.getvalue()
        return output if output.strip() else "OK"
