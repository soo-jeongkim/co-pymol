#!/usr/bin/env python
"""Headless PyMOL launcher for cluster use.

Usage:
    pymol -cq -r start_headless.py -- /path/to/structures/*.cif --port 8766
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Start pymol-claude MCP server in headless mode")
    parser.add_argument("files", nargs="*", help="Structure files to load into triage")
    parser.add_argument("--port", type=int, default=8766, help="MCP server port (default: 8766)")
    args = parser.parse_args()

    # Verify PyMOL is available
    try:
        from pymol import cmd
    except ImportError:
        print("Error: PyMOL is not available. Run this with: pymol -cq -r start_headless.py")
        sys.exit(1)

    from pymol_claude.mcp_server import create_server, triage

    server = create_server()

    # If files were provided, load them into triage
    if args.files:
        # Check if a directory was provided
        paths = [Path(f) for f in args.files]
        if len(paths) == 1 and paths[0].is_dir():
            result = triage.load_directory(paths[0])
        else:
            # Load individual files
            from pymol_claude.metrics import extract_record
            triage.files = paths
            for p in paths:
                if p.exists():
                    record = extract_record(p)
                    triage.records[p.name] = record
            result = f"Loaded {len(paths)} structures"
        print(result)

    print(f"\npymol-claude: MCP server starting on http://127.0.0.1:{args.port}/sse")
    print(f"\nFor remote use, tunnel the port to your laptop:")
    print(f"  ssh -L {args.port}:localhost:{args.port} user@host")
    print(f"\nThen, on the machine running your MCP client, wire it up:")
    print(f"  pymol-claude install-config --port {args.port}                                # Cursor")
    print(f"  claude mcp add --transport sse --scope user pymol http://localhost:{args.port}/sse  # Claude Code")
    print(f"\nOr add this entry by hand to ~/.cursor/mcp.json or your Claude Code config:")
    print(f'  "pymol": {{ "url": "http://localhost:{args.port}/sse" }}')
    print()

    # Run blocking (no GUI to keep alive)
    server.run(transport="sse", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
