# pymol-claude

PyMOL plugin that turns PyMOL into an MCP server. Drive PyMOL — load, color, align, score, render — from Claude Code, Cursor, or any MCP client.

## What it is

`pymol-claude` lets you drive PyMOL from Cursor or Claude Code (or any MCP client) in English — load structures, color, align, score, render. PyMOL hosts the MCP server; your editor is the client. Start PyMOL once and leave it running.

It ships with `gemmi`-backed metric tools, so pLDDT, ipTM, pTM, and PAE are read straight from mmCIF without rendering — triage queries like "which model has the worst ipTM?" come back as fast text answers. You can also drop a `.py` of your own PyMOL helpers anywhere on disk and ask the agent to load it; your lab's view presets and analysis functions work without being rewritten as MCP tools.

Because it works over Claude Code, anything you can do in a Claude Code session you can do here — including `/remote-control`, which lets you drive your workstation's PyMOL from the Claude mobile app. Triage a fold batch from your phone on the train.

A typical session in Claude Code:

```
> Load all the CIF files in /path/to/dir/w/predicted/structures/
[all the structures visible on PyMOL window]
Loaded all structures, sorted by mean pLDDT.

> Which one has the worst ipTM?
model_3 — ipTM 0.41 (others are 0.7+).

> Show me the low-confidence loops on model_3.
[renders cartoon on PyMOL window, residues 142–168 highlighted, mean pLDDT 38]
```

## Install

The plugin installs into **PyMOL's bundled Python**, not your system Python. PyMOL has to be running for any of this to work.

### 1. Clone

```bash
git clone https://github.com/soo-jeongkim/pymol-claude.git
cd pymol-claude
```

### 2. Find PyMOL's Python

On macOS, the default PyMOL.app install ships with:

```
/Applications/PyMOL.app/Contents/bin/python
```

On Linux, conda, or a non-standard install, ask PyMOL itself:

```bash
pymol -c -q -d "import sys; print(sys.executable)"
```

PyMOL may print startup noise around it — grab the path that looks like a Python interpreter.

Throughout the rest of these instructions, `$PYMOL_PY` refers to that path. Export it once and the rest of the install is copy-paste:

```bash
export PYMOL_PY=/Applications/PyMOL.app/Contents/bin/python   # macOS — or paste your path
```

Sanity check before continuing:

```bash
$PYMOL_PY -c "import pymol; print(pymol.__file__)"
```

If that errors, `$PYMOL_PY` isn't PyMOL's Python — re-check step 2 before running step 3.

### 3. Install the plugin into PyMOL's Python

```bash
$PYMOL_PY -m pip install -e .
```

This also drops a `pymol-claude` shim into PyMOL's `bin/` directory (sibling of `$PYMOL_PY`). The rest of this README invokes it as `$PYMOL_PY -m pymol_claude.cli ...` so the commands work whether or not you've put PyMOL's `bin/` on your `PATH`. If you have, the shorter `pymol-claude ...` form works too.

`sudo` is usually unnecessary and best avoided.

### 4. Tell PyMOL to start the plugin on launch

Add to `~/.pymolrc.py` (create it if missing):

```python
from pymol_claude import __init_plugin__
__init_plugin__()
```

### 5. Restart PyMOL

The console should print:

```
pymol-claude: MCP server running on http://127.0.0.1:8766/sse
```

If it doesn't, see [Troubleshooting](#troubleshooting).

### 6. Wire up your MCP client

Pick whichever you use. Both setups are **global** — every Cursor window or Claude Code session will see the `pymol` server, no need to `cd` into this repo first.

**Cursor:**

```bash
$PYMOL_PY -m pymol_claude.cli install-config
```

Writes `~/.cursor/mcp.json`, merging with any existing entries. Restart Cursor (full quit, not just window reload); verify under Settings → Cursor Settings → MCP that `pymol` is listed.

**Claude Code:**

```bash
claude mcp add --transport sse --scope user pymol http://localhost:8766/sse
```

Works from any directory. `claude mcp list` should now show `pymol`.

> The `install-config` CLI currently writes only Cursor config. For Claude Code, `claude mcp add` is the canonical path — there's no `pymol-claude` equivalent yet.

## Usage

1. Open PyMOL (the MCP server auto-starts).
2. Open Claude Code (`claude` in a terminal) or Cursor with MCP enabled.
3. Talk to it:
   - "Load all CIF files in `<dir>`, sorted by ipTM"
   - "Color by pLDDT, then render a ray-traced PNG"
   - "Align model_0 onto model_1; what's the RMSD?"
   - "Look at `~/scripts/my_pymol_helpers.py` — apply the publication-style view to all objects"

## Tools

One general-purpose tool, plus a handful of dedicated ones.

### `run(code)` — the workhorse

Arbitrary Python with `cmd` (PyMOL's `pymol.cmd`) bound. The client writes PyMOL directly rather than calling a wrapper per verb. Examples of what a client might actually send:

```python
run("cmd.load('foo.cif'); cmd.color('salmon', 'chain A')")

run("""
cmd.fetch('1ubq', async_=0)
cmd.hide('everything'); cmd.show('cartoon')
cmd.color('marine')
cmd.orient()
""")

run("""
print(cmd.get_object_list())
print('Polymer atoms:', cmd.count_atoms('polymer'))
""")
```

Stdout is returned to the client. Use `run` for anything PyMOL-y the dedicated tools below don't already cover.

### Rendering

- `render(width, height, ray=True)` — ray-traced PNG, returned inline.
- `snapshot(width, height)` — fast, non-ray PNG.
- `color_by_plddt(selection)` — applies the project palette (blue=high → red=low).

### Metrics (gemmi, not PyMOL)

Reads `_ma_qa_metric_*` from mmCIF first, falls back to sibling JSON (AF3 server and AF2-multimer layouts both work).

- `get_metrics(name)` — full per-structure report: chains, residue count, pLDDT bands, ipTM, pTM, ranking_score, mean PAE. Reach for it when you want everything you know about one model.
- `find_low_confidence(name, threshold=70)` — contiguous regions below a pLDDT threshold. Reach for it when you want "where exactly is this model uncertain?" rather than a single number.
- `compare_all()` — sorted table of every loaded structure with pLDDT, ipTM, pTM columns. Reach for it after `load_directory` when you want a ranking.
- `cif_grep(tag, path)` — search `.cif` files for a tag value (e.g. `_ma_qa_metric_global.metric_value`) across a directory. Reach for it when you need a one-off field the structured tools don't expose.

### Triage

A stateful navigator for reviewing a batch of structures (the mobile-eval workflow):

- `load_directory(path)` — scan a directory, extract metrics, load all structures into PyMOL, set up the navigation cursor.
- `next_structure` / `prev_structure` / `go_to(n)` / `current` — move the cursor; each call hides the others, colors by pLDDT, orients, renders.
- `flag(note)` / `show_flags` / `export_flags` — flag the current structure with a note; export as JSON for downstream tools.
- `filter(min_plddt, max_plddt)` — restrict navigation to structures in a pLDDT range.

## Troubleshooting

**"MCP server running on..." doesn't appear when PyMOL starts.**
- *Port 8766 already in use.* Another PyMOL session is running, or another process owns the port. `lsof -iTCP:8766` to check; close the offender or restart on a different port from PyMOL's CLI: `stop_mcp` then `start_mcp 8767`.
- *Plugin not found.* Step 3 likely installed into the wrong Python. Run `$PYMOL_PY -c "import pymol_claude; print(pymol_claude.__file__)"` — it should print a path. If it errors, re-run step 3 with the path from step 2.
- *`~/.pymolrc.py` not loaded.* Add `print("pymolrc loaded")` to the top; if you don't see it, PyMOL isn't reading the file (check PyMOL's working dir; it loads from `$HOME`).

**MCP client can't see the `pymol` server.**
- *Cursor:* fully quit and reopen — a window reload isn't enough. Check Settings → Cursor Settings → MCP.
- *Claude Code:* `claude mcp list` to confirm `pymol` is registered.
- *Either:* `curl http://localhost:8766/sse` should hang open (SSE). If it errors, PyMOL isn't running, the plugin didn't start, or the port is blocked.

**Manual server control (inside PyMOL):**

```
start_mcp [port]   # auto-runs on plugin load; use this to restart on a new port
stop_mcp           # stop the server
```

**Running headless (no GUI, e.g. on a cluster):**

```bash
pymol -cq -r start_headless.py -- --port 8766 /path/to/structures/
```

Then tunnel the port back to your laptop:

```bash
ssh -L 8766:localhost:8766 user@host
```

…and point your local MCP client at `http://localhost:8766/sse`.

**Skipping the pip install.** To run from this clone without installing, point `~/.pymolrc.py` at it via `sys.path`:

```python
import sys
sys.path.insert(0, "/path/to/pymol-claude")
from pymol_claude import __init_plugin__
__init_plugin__()
```

For step 6 (Cursor), `python -m pymol_claude.cli install-config` works from inside the clone with any Python.

**Project-scoped Cursor config.** To enable `pymol` only inside one project (e.g. to point at a different port for that workspace):

```bash
$PYMOL_PY -m pymol_claude.cli install-config --project --project-dir /path/to/project
```

Writes `<project>/.cursor/mcp.json`. Cursor merges project and global configs; project entries override the global `pymol` entry in that workspace — occasionally what you want, otherwise surprising.
