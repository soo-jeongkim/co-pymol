"""CLI for pymol-claude setup and diagnostics.

Subcommands:
    install-hook       Append the plugin startup line to ~/.pymolrc.py
    install-config     Write Cursor MCP config (global by default)

The CLI is pure stdlib — it does not import pymol or fastmcp — so it can run
under any Python interpreter, even if the plugin itself was installed into
PyMOL's bundled Python.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pymol_claude.config import DEFAULT_PORT

PYMOLRC_SENTINEL = "# pymol-claude: auto-start MCP server on PyMOL launch"
PYMOLRC_LINE = "from pymol_claude import __init_plugin__; __init_plugin__()"


def server_url(port: int) -> str:
    return f"http://localhost:{port}/sse"


def _load_existing(path: Path) -> tuple[dict, str | None]:
    """Return (data, error). data is {} if file is missing."""
    if not path.exists():
        return {}, None
    try:
        text = path.read_text()
    except OSError as e:
        return {}, f"Could not read {path}: {e}"
    if not text.strip():
        return {}, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {}, f"{path} is not valid JSON: {e}. Fix or remove it, then re-run."
    if not isinstance(data, dict):
        return {}, f"{path} must contain a JSON object at the top level."
    return data, None


def write_mcp_config(path: Path, port: int) -> str:
    """Merge a `pymol` entry into mcpServers, preserving other servers.

    Returns a human-readable status message. Raises on I/O errors.
    """
    data, err = _load_existing(path)
    if err is not None:
        return f"ERROR: {err}"

    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        return f"ERROR: 'mcpServers' in {path} must be an object."

    desired_url = server_url(port)
    existing = servers.get("pymol")
    if isinstance(existing, dict) and existing.get("url") == desired_url:
        return f"Already configured: {path} -> pymol @ {desired_url}"

    servers["pymol"] = {"url": desired_url}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")

    action = "Updated" if existing is not None else "Wrote"
    return f"{action} {path} -> pymol @ {desired_url}"


def write_pymolrc_hook(path: Path) -> str:
    """Append the plugin startup line to ~/.pymolrc.py if not already present.

    Returns a human-readable status message. Raises on I/O errors.
    """
    existing = path.read_text() if path.exists() else ""

    if PYMOLRC_LINE in existing:
        return f"Already configured: {path}"

    snippet_parts: list[str] = []
    if existing and not existing.endswith("\n"):
        snippet_parts.append("\n")
    if existing:
        snippet_parts.append("\n")
    snippet_parts.append(f"{PYMOLRC_SENTINEL}\n{PYMOLRC_LINE}\n")
    snippet = "".join(snippet_parts)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(snippet)

    action = "Appended to" if existing else "Wrote"
    return f"{action} {path}. Restart PyMOL to load the plugin."


def cmd_install_hook(args: argparse.Namespace) -> int:
    target = Path.home() / ".pymolrc.py"
    msg = write_pymolrc_hook(target)
    print(msg)
    return 0


def cmd_install_config(args: argparse.Namespace) -> int:
    if args.project:
        target = Path(args.project_dir).resolve() / ".cursor" / "mcp.json"
    else:
        target = Path.home() / ".cursor" / "mcp.json"

    msg = write_mcp_config(target, args.port)
    print(msg)
    if msg.startswith("ERROR"):
        return 1
    if not args.project:
        print("Restart Cursor to pick up the change.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymol-claude",
        description="pymol-claude setup and diagnostics",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hook = sub.add_parser(
        "install-hook",
        help="Append plugin startup line to ~/.pymolrc.py so PyMOL loads it on launch",
        description=(
            "Append a one-liner to ~/.pymolrc.py that starts the MCP server when "
            "PyMOL launches. Safe to re-run — does nothing if the line is already "
            "present."
        ),
    )
    p_hook.set_defaults(func=cmd_install_hook)

    p_install = sub.add_parser(
        "install-config",
        help="Write Cursor MCP config so the pymol server is available everywhere",
        description=(
            "Write Cursor MCP config. Default target is ~/.cursor/mcp.json (global), "
            "which makes the pymol tools available in every Cursor window. "
            "Use --project to write ./.cursor/mcp.json instead. "
            "Existing entries in mcpServers are preserved."
        ),
    )
    p_install.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"MCP server port (default: {DEFAULT_PORT})",
    )
    p_install.add_argument(
        "--project",
        action="store_true",
        help="Write project-level config (./.cursor/mcp.json) instead of global",
    )
    p_install.add_argument(
        "--project-dir",
        default=".",
        help="Project root for --project (default: current directory)",
    )
    p_install.set_defaults(func=cmd_install_config)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
