# pylot

**Active WIP** — works for personal use.

tldr - PyMOL plugin that turns PyMOL into an MCP server. Drive PyMOL from Claude Code, Cursor, or any MCP client.

## What it is

`pylot` lets you drive PyMOL from Cursor or Claude Code (or any MCP client) in English — load structures, color, align, score, render.

It ships with `gemmi`-backed metric tools, so pLDDT, ipTM, pTM, and PAE can be read from the CIF (or PDB) files without rendering. You can use it to triage with queries like "which design has the worst ipTM?" come back as fast text answers. You can also drop a `.py` of your own PyMOL custom presets and analysis functions within the cloned dir and ask the agent to use it.

Because it can work over Claude Code, anything you can do in a Claude Code session you can do here — including `/remote-control`, which lets you drive your workstation's PyMOL from the Claude mobile app.

For cluster users: run PyMOL locally as usual and point it at your remote CIFs through your mounted cluster path as per usual (SSHFS/NFS/etc.), anything visible locally works!

An example session in Claude Code/cursor:

```
> Load all the CIF files in /path/to/dir/w/predicted/structures/
[all the structures visible on PyMOL window]
Loaded all structures, sorted by mean pLDDT.

> Which one has the worst ipTM?
model_3 — ipTM 0.41 (others are 0.7+).

> Show me the low-confidence loops on structure_500.
[renders cartoon on PyMOL window, residues 142–168 highlighted, mean pLDDT 38]

```

## Install

> **Only tested on macOS** with the default `/Applications/PyMOL.app/` install. Linux / conda / non-standard installs should work in principle — the recipe is just "install into PyMOL's bundled Python" — but I haven't verified them.

The plugin installs into **PyMOL's bundled Python**, not your system Python.

### 1. Clone and install

```bash
git clone https://github.com/soo-jeongkim/pylot.git
cd pylot
/Applications/PyMOL.app/Contents/bin/python -m pip install --user -e .
```

### 2. Hook the plugin into PyMOL startup

```bash
/Applications/PyMOL.app/Contents/bin/python -m pylot.cli install-hook
```

Appends one line to `~/.pymolrc.py` so PyMOL loads the plugin on launch. Safe to re-run.

### 3. Restart PyMOL

The console should print:

```
pylot: MCP server running on http://127.0.0.1:8766/sse
```

If you don't see that line, `~/.pymolrc.py` isn't being loaded. The file must be in your home directory (`echo $HOME` to check), and you need a full PyMOL quit + relaunch, not a window close.

### 4. Wire up your MCP client

Both setups are **global** — every Cursor window or Claude Code session sees the `pymol` server, no need to `cd` into this repo.

**Cursor:**

```bash
/Applications/PyMOL.app/Contents/bin/python -m pylot.cli install-config
```

Writes/merges `~/.cursor/mcp.json`. Fully quit Cursor (`Cmd+Q`, not just close the window) and reopen; verify under Settings → Cursor Settings → MCP that `pymol` is listed.

**Claude Code:**

```bash
claude mcp add --transport sse --scope user pymol http://localhost:8766/sse
```

Works from any directory. `claude mcp list` should show `pymol`.

Once correct plumbing is verified, you need to open PyMOL first then a new Cursor window/Claude Code session.

## Uninstall

Reverses the Install steps. There's no `uninstall` subcommand, so the config edits are manual — they're one line each.

### 1. Unwire your MCP client

**Cursor:** edit `~/.cursor/mcp.json` and delete the `"pymol"` entry under `mcpServers` (leave any other servers intact). Quit Cursor (`Cmd+Q`) and reopen.

**Claude Code:**

```bash
claude mcp remove pymol --scope user
```

### 2. Remove the PyMOL startup hook

Delete these two lines from `~/.pymolrc.py`:

```python
# pylot: auto-start MCP server on PyMOL launch
from pylot import __init_plugin__; __init_plugin__()
```

If that was the only thing in the file, you can delete `~/.pymolrc.py` entirely.

### 3. Uninstall the package

```bash
/Applications/PyMOL.app/Contents/bin/python -m pip uninstall pylot
```

### 4. Restart PyMOL

A full quit + relaunch. The `MCP server running on...` line should be gone. The plugin keeps no caches or logs of its own, so nothing else is left behind. (The cloned repo is yours to `rm -rf` whenever.)

## Usage

1. Open PyMOL (the MCP server auto-starts).
2. Open Claude Code (`claude` in a terminal) or Cursor with MCP enabled.
3. Talk to it:
   - "Load all CIF files in `<dir>`, sorted by ipTM"
   - "Color by pLDDT, then render a ray-traced PNG"
   - "Align model_0 onto model_1; what's the RMSD?"
   - "Look at `~/scripts/my_pymol_helpers.py` — apply the publication-style view to all objects"

## Notes

- **`get_metrics` and `path`:** Structures loaded via `load_directory` have metrics automatically. If you load with `run("cmd.load('foo.cif')")`, pass `path` to `get_metrics` or `find_low_confidence`.
- **`run()` security:** Executes locally with restricted Python builtins (no imports/file I/O), but full PyMOL access via `cmd`. Only connect trusted MCP clients.
- **Dev setup (optional):** `pip install -e ".[dev]" && pytest`. Pre-commit hooks are available but not required — see `.pre-commit-config.yaml`.
