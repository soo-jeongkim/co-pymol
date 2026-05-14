# pymol-claude

PyMOL plugin that exposes PyMOL's Python API as an MCP server.

## Architecture

- **Plugin runs inside PyMOL's process.** On startup (`__init_plugin__`), a FastMCP server launches in a daemon background thread on port 8766.
- **MCP server** (`pymol_claude/mcp_server.py`) exposes PyMOL's `cmd` module as MCP tools. Claude connects via `http://localhost:8766/sse`.
- **Metrics** (`pymol_claude/metrics.py`) uses biotite for structure metadata extraction — not PyMOL. This keeps metric parsing clean and avoids polluting PyMOL's object state.
- **Triage** (`pymol_claude/triage.py`) manages navigation/flagging state for reviewing batches of structures (mobile eval workflow).

## Thread safety

All `pymol.cmd` calls are serialized with `_pymol_lock` (a `threading.Lock`). The MCP server runs in a daemon thread; PyMOL's GUI runs on the main thread. Rendering (`cmd.ray`, `cmd.png`) definitely needs the lock. Most read operations work from threads in modern PyMOL, but we lock everything for safety.

## How to test

1. Install: `uv pip install -e .`
2. Start PyMOL (GUI): plugin auto-starts, check console for "MCP server running on..."
3. Or headless: `pymol -cq -r start_headless.py -- --port 8766`
4. Test with curl: `curl http://localhost:8766/sse` should establish SSE connection
5. Connect Claude Code: add `"pymol": {"url": "http://localhost:8766/sse"}` to MCP settings

## How to add new tools

1. Open `pymol_claude/mcp_server.py`
2. Inside `create_server()`, add a new function decorated with `@mcp.tool()`
3. Use `_pymol_lock` for any `pymol.cmd` calls
4. Return a string (status message) or `Image` (for rendered output)

```python
@mcp.tool()
def my_new_tool(arg: str) -> str:
    """Description shown to Claude."""
    cmd = _ensure_pymol()
    with _pymol_lock:
        cmd.some_operation(arg)
        return f"Done: {arg}"
```

## Dependencies

- `fastmcp>=2.0` — MCP server framework
- `biotite>=0.40` — structure file parsing for metrics
- `numpy`, `scipy`, `rich` — supporting libraries
- PyMOL — **not a pip dependency**, install via `uv pip install pymol-open-source`
