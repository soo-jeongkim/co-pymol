# pymol-claude

PyMOL plugin that exposes PyMOL as an MCP server. Control PyMOL from Claude Code (terminal), Claude mobile app, or claude.ai.

## How it works

The plugin runs inside PyMOL's process. On startup it launches a FastMCP server in a background thread on port 8766. That server exposes PyMOL's `cmd` module as MCP tools. Claude connects to `http://localhost:8766/sse` and can execute any PyMOL operation.

There is no chat UI inside PyMOL. PyMOL is the viewer. Claude (in terminal, phone, or browser) is where you type.

## Install

**Prerequisites:** PyMOL must be installed separately:
```bash
conda install -c conda-forge pymol-open-source
```

**Install the plugin:**
```bash
pip install -e .
```

**Or as a PyMOL plugin (GUI):**
1. In PyMOL: Plugin > Plugin Manager > Install New Plugin > Choose file
2. Point it at `pymol_claude/__init__.py`
3. Restart PyMOL

## Usage

### Desktop (GUI PyMOL + Claude Code)

1. Open PyMOL — plugin auto-starts MCP server
2. In another terminal, run `claude`
3. Type "load my_protein.pdb and color by pLDDT" — it happens in PyMOL

Claude Code MCP config (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "pymol": {
      "url": "http://localhost:8766/sse"
    }
  }
}
```

### Mobile (phone triage)

1. Start PyMOL on cluster:
   ```bash
   pymol -cq -r start_headless.py -- predictions/*.cif --port 8766
   ```
2. Add `http://your-cluster:8766/sse` as a connector on claude.ai (Settings > Connectors)
3. Open Claude app on phone
4. "Show me the first structure" — rendered image appears in chat
5. "Next" / "Flag this one, bad loop at N-terminus" — navigate and flag

### PyMOL commands

```
start_claude [port]   # Start MCP server (auto-starts on plugin load)
stop_claude           # Stop MCP server
```

## Available tools

**Visualization:** load, delete, list_objects, show, hide, color, color_by_plddt, color_by_chain, color_by_spectrum, select, zoom, center, orient, turn, bg_color, set_setting

**Structural analysis:** align, super_align, polar_contacts, measure, get_sequence, get_chains, count_atoms

**Rendering:** render (ray-traced), snapshot (fast)

**Metrics (biotite):** get_metrics, find_low_confidence, compare_all

**Triage:** load_directory, next_structure, prev_structure, go_to, current, flag, show_flags, export_flags, filter

**Escape hatch:** run (arbitrary PyMOL/Python code)
