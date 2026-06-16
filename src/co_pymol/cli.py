"""CLI for co-pymol setup and diagnostics.

Subcommands:
    install-hook       Append the plugin startup line to ~/.pymolrc.py
    install-config     Write Cursor MCP config (global by default)
    proxy              Run the stdio MCP proxy that survives PyMOL restarts

The CLI is pure stdlib — it does not import pymol or mcp — so it can run
under any Python interpreter, even if the plugin itself was installed into
PyMOL's bundled Python.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from co_pymol.constants import DEFAULT_HOST, DEFAULT_PORT

PYMOLRC_SENTINEL = "# co-pymol: auto-start MCP server on PyMOL launch"
PYMOLRC_LINE = "from co_pymol import __init_plugin__; __init_plugin__()"


def server_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    """The SSE endpoint a client connects to for a server at host:port."""
    return f"http://{host}:{port}/sse"


def load_config(path: Path) -> dict:
    """Read a JSON object from `path`, or {} if it's missing or empty."""
    text = path.read_text() if path.exists() else ""
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object at the top level.")
    return data


def write_mcp_config(path: Path, host: str, port: int) -> str:
    """Merge a `pymol` entry into mcpServers, preserving other servers."""
    data = load_config(path)
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"'mcpServers' in {path} must be an object.")

    desired_url = server_url(host, port)
    existing = servers.get("pymol")
    if isinstance(existing, dict) and existing.get("url") == desired_url:
        return f"Already configured: {path} -> pymol @ {desired_url}"

    servers["pymol"] = {"url": desired_url}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")

    action = "Updated" if existing is not None else "Wrote"
    return f"{action} {path} -> pymol @ {desired_url}"


def write_pymolrc_hook(path: Path) -> str:
    """Append the plugin startup line to ~/.pymolrc.py if not already present."""
    existing = path.read_text() if path.exists() else ""
    if PYMOLRC_LINE in existing:
        return f"Already configured: {path}"

    prefix = "" if not existing else "\n" if existing.endswith("\n") else "\n\n"
    snippet = f"{prefix}{PYMOLRC_SENTINEL}\n{PYMOLRC_LINE}\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(snippet)

    action = "Appended to" if existing else "Wrote"
    return f"{action} {path}. Restart PyMOL to load the plugin."


def cmd_install_hook(args: argparse.Namespace) -> None:
    print(write_pymolrc_hook(Path.home() / ".pymolrc.py"))


def cmd_proxy(args: argparse.Namespace) -> int:
    # Deferred import: proxy.py pulls in mcp/anyio, which (like pymol) only exist
    # where the package's deps are installed. Importing it lazily here keeps the
    # rest of the CLI (install-hook/install-config) runnable under a stdlib-only
    # Python that just has the package source on its path.
    from co_pymol.proxy import run_proxy

    return run_proxy(args.host, args.port)


def cmd_install_config(args: argparse.Namespace) -> None:
    if args.project:
        target = Path(args.project_dir).resolve() / ".cursor" / "mcp.json"
    else:
        target = Path.home() / ".cursor" / "mcp.json"

    print(write_mcp_config(target, args.host, args.port))
    if not args.project:
        print("Restart Cursor to pick up the change.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="co-pymol",
        description="co-pymol setup and diagnostics",
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
        "--project",
        action="store_true",
        help="Write project-level config (./.cursor/mcp.json) instead of global",
    )
    p_install.add_argument(
        "--project-dir",
        default=".",
        help="Project root for --project (default: current directory)",
    )
    p_install.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"MCP server host (default: {DEFAULT_HOST})",
    )
    p_install.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"MCP server port (default: {DEFAULT_PORT})",
    )
    p_install.set_defaults(func=cmd_install_config)

    p_proxy = sub.add_parser(
        "proxy",
        help="Run the stdio MCP proxy that survives PyMOL restarts",
        description=(
            "Run a stdio MCP proxy in the foreground. A client (e.g. Claude Code) "
            "launches this as a subprocess; it forwards to the co-pymol SSE server "
            "in PyMOL and survives PyMOL quitting/restarting so the client's "
            "connection never drops. Configure the client with: "
            "`claude mcp add pymol -- co-pymol proxy`."
        ),
    )
    p_proxy.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"co-pymol SSE host (default: {DEFAULT_HOST})",
    )
    p_proxy.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"co-pymol SSE port (default: {DEFAULT_PORT})",
    )
    p_proxy.set_defaults(func=cmd_proxy)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # Subcommands return an exit code (proxy) or None (setup commands).
        return args.func(args) or 0
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
