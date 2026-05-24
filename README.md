# pymol-claude

PyMOL plugin that exposes PyMOL as an MCP server. Control PyMOL from Claude Code, Cursor, or any MCP client — load structures, color, align, render — all from the terminal.

## Setup (one time)

### 1. Clone this repo

```bash
git clone <repo-url> pymol-claude
cd pymol-claude
```

### 2. Tell PyMOL where the plugin lives (recommended)

Add this once to `~/.pymolrc.py` (edit manually, no shell heredoc needed):

```python
from pathlib import Path
import sys

repo = Path("~/pymol-claude").expanduser()  # adjust if you cloned elsewhere
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))

from pymol_claude import __init_plugin__
__init_plugin__()
```

This runs directly from your clone, so you can pull changes and restart PyMOL without reinstalling.

### 3. Optional: install into PyMOL's Python

If you prefer an installed package instead of importing from the clone:

```bash
/Applications/PyMOL.app/Contents/bin/python -m pip install --user -e .
```

On Linux/conda installs, replace the Python path with your PyMOL interpreter.

`sudo` is usually unnecessary and best avoided. Use it only if you intentionally want a system-wide install and understand the permission implications.

### 4. Connect an MCP client

#### Claude Code

```bash
claude mcp add --transport sse --scope user pymol http://localhost:8766/sse
```

That's it. This works globally — you can run `claude` from any directory.

#### Cursor

Recent Cursor releases support SSE/HTTP MCP servers. Add this in either:
- `~/.cursor/mcp.json` (global), or
- `.cursor/mcp.json` in your project

```json
{
  "mcpServers": {
    "pymol": {
      "url": "http://localhost:8766/sse"
    }
  }
}
```

Then:
- Restart Cursor
- Go to Settings -> Cursor Settings -> MCP
- Make sure PyMOL is already running (PyMOL hosts the MCP server)
- Confirm `pymol` is listed and tools are visible (`run`, `render`, `load_directory`, etc.)
- If tools do not appear, check the MCP panel error and run `curl http://localhost:8766/sse` to confirm the server is reachable

This repo also includes `.mcp.json` with the same server URL block.

## Usage

1. **Open PyMOL** — the MCP server auto-starts (check console for "MCP server running on...")
2. **Open your MCP client**
   - Claude Code in any terminal: `claude`
   - Cursor in the IDE with MCP enabled
3. **Talk to it:**
   - "Load all the CIF files in <your structure dir>"
   - "Color by pLDDT"
   - "Align model_0 to model_1"
   - "Show sticks for the active site"
   - "Render an image"

PyMOL must be running first — it's the server, and your MCP client (Claude Code or Cursor) is the client.

### Phone / remote use

Any MCP client session that can reach the MCP port can drive PyMOL. Claude Code sessions — including ones started remotely from the Claude mobile app — work well for this. So you can leave PyMOL running on your workstation and triage structures from your phone:

- "Load the latest fold batch and tell me which model has the best pLDDT"
- "Any low-confidence loops in model 3?"
- "Color by chain and render"

Metrics (pLDDT, ipTM, pTM, PAE) are extracted by **gemmi** straight from the mmCIF — no render needed — so you get fast text answers, and your MCP client does the actual analysis (sorting, comparing, flagging) on top of those numbers. Renders come back inline as PNGs when you ask for them.

### Reusing your existing PyMOL scripts

You can point your MCP client at a `.py` file full of your own PyMOL functions and ask it to apply them. It reads the script, lists what's in there, and runs the function bodies for you through the `run` tool — defining any custom colors or settings the script depends on.

Example:

> "Look at `~/scripts/my_pymol_helpers.py` — what view templates do you have? Apply the publication-style one to all loaded objects."

Your MCP client will scan the script, summarize the available functions (e.g. `pic`, `pic2`, `ball_and_stick`, `bspec1`, ...), then execute the chosen one against your current session. Useful for porting old `.pymolrc` setups or lab-specific styling presets without rewriting them as MCP tools.

## Available tools

The main tool is **`run(code)`** — arbitrary Python with `cmd` (pymol.cmd) bound. Your MCP client writes the PyMOL itself rather than calling a wrapper for every verb: `run("cmd.load('foo.cif'); cmd.show('cartoon'); cmd.color('salmon', 'chain A')")`.

The dedicated tools cover what `run` can't:

**Rendering (return PNGs inline):** `render` (ray-traced), `snapshot` (fast), `color_by_plddt` (project palette)

**Metrics (gemmi, not PyMOL):** `get_metrics`, `find_low_confidence`, `compare_all`, `cif_grep`

**Triage (stateful navigation + rendered images):** `load_directory`, `next_structure`, `prev_structure`, `go_to`, `current`, `flag`, `show_flags`, `export_flags`, `filter`

## PyMOL commands

```
start_mcp [port]   # Start MCP server (auto-starts on plugin load)
stop_mcp           # Stop MCP server
```
