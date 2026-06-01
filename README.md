# pylot

fyi — this repo is an active WIP!

## the what

**`pylot`** is a pymol plugin that lets you use pymol through claude code and cursor agents.

it turns PyMOL into an MCP server so you can drive PyMOL in English from any MCP client like Claude Code or Cursor, instead of typing PyMOL commands by hand. on startup, it spins up an MCP server — built on the official MCP Python SDK — inside PyMOL's own Python process, exposing the `pymol.cmd` API as tools.

there's also a gemmi-backed metrics layer that can parse mmCIF e.g. if you want to read confidence values (pLDDT / ipTM / pTM / PAE). you can also drop in your own `.py` of **custom PyMOL presets / analysis** helpers and ask the agent to use them, and work over **SSHFS-mounted cluster paths** as usual. and since it runs through Claude Code you get **any Claude capabilities** here too — remote-control from the mobile app, etc.

an example session in Claude Code / Cursor:

```
> load all the CIF files in /path/to/dir/w/predicted/structures/
[all the structures visible on PyMOL window]
loaded all structures, sorted by mean pLDDT.

> which one has the worst ipTM?
model_3 — ipTM 0.41 (others are 0.7+).

> show me the low-confidence loops on structure_500.
[renders cartoon on PyMOL window, residues 142–168 highlighted, mean pLDDT 38]
```

## the why

- automating analysis or visualisation with agents
- remote access on mobile

## installing

note: only tested on macOS :/ linux / conda / non-standard installs should work in principle — the recipe is just "install into PyMOL's bundled Python" — but i haven't verified them.

the plugin installs into **PyMOL's bundled Python**, not your system Python.

**1. clone and install**

```bash
git clone https://github.com/soo-jeongkim/pylot.git
cd pylot
/Applications/PyMOL.app/Contents/bin/python -m pip install --user -e .
```

**2. hook the plugin into PyMOL startup**

```bash
/Applications/PyMOL.app/Contents/bin/python -m pylot.cli install-hook
```

appends one line to `~/.pymolrc.py` so PyMOL loads the plugin on launch. safe to re-run.

**3. restart PyMOL**

the console should print:

```
pylot: MCP server running on http://127.0.0.1:8766/sse
```

if you don't see that line, `~/.pymolrc.py` isn't being loaded. the file must be in your home directory (`echo $HOME` to check), and you need a full PyMOL quit + relaunch, not a window close.

by default the server binds `127.0.0.1:8766` (loopback) — PyMOL and your MCP client must run on the same machine. to override, run `start_mcp` from the PyMOL command line: `start_mcp 9000` for a different port, or `start_mcp 8766, 0.0.0.0` to also accept connections from other machines. if you change either, point the client at the matching url (e.g. `install-config --host <host> --port <port>`).

**4. wire up your MCP client**

both setups are global — every Cursor window or Claude Code session sees the `pymol` server, no need to `cd` into this repo.

**cursor**

```bash
/Applications/PyMOL.app/Contents/bin/python -m pylot.cli install-config
```

writes/merges `~/.cursor/mcp.json`. fully quit Cursor (`Cmd+Q`, not just close the window) and reopen; verify under Settings → Cursor Settings → MCP that `pymol` is listed.

**claude code**

```bash
claude mcp add --transport sse --scope user pymol http://127.0.0.1:8766/sse
```

works from any directory. `claude mcp list` should show `pymol`.

once correct plumbing is verified, you need to open PyMOL first then a new Cursor window / Claude Code session.

## 03 experimenting!

1. open PyMOL (the MCP server auto-starts).
2. open Claude Code (`claude` in a terminal) or Cursor with MCP enabled.
3. talk to it:
   - "load all CIF files in `<dir>`, sorted by ipTM"
   - "color by pLDDT, then render a ray-traced PNG"
   - "align model_0 onto model_1; what's the RMSD?"
   - "look at `~/scripts/my_pymol_helpers.py` — apply the publication-style view to all objects"

want sample data? **[click here](https://500.kim/resources/pizza-and-pymol.zip)** to download a few sample CIF files (AF3 predictions, antibodies, multi-domain proteins) to play with.

## 04 uninstalling

reverses the install steps. there's no `uninstall` subcommand, so the config edits are manual — they're one line each.

**1. unwire your MCP client**

cursor: edit `~/.cursor/mcp.json` and delete the `"pymol"` entry under `mcpServers` (leave any other servers intact). quit Cursor (`Cmd+Q`) and reopen.

claude code:

```bash
claude mcp remove pymol --scope user
```

**2. remove the PyMOL startup hook**

delete these two lines from `~/.pymolrc.py`:

```python
# pylot: auto-start MCP server on PyMOL launch
from pylot import __init_plugin__; __init_plugin__()
```

if that was the only thing in the file, you can delete `~/.pymolrc.py` entirely.

**3. uninstall the package**

```bash
/Applications/PyMOL.app/Contents/bin/python -m pip uninstall pylot
```

**4. restart PyMOL**

a full quit + relaunch. the `MCP server running on...` line should be gone. the plugin keeps no caches or logs of its own, so nothing else is left behind. (the cloned repo is yours to `rm -rf` whenever.)

## 05 notes

- **`run()` security** — executes locally with restricted Python builtins (no imports / file I/O), but full PyMOL access via `cmd`. only connect trusted MCP clients.

- **dev setup (optional)** — `pip install -e ".[dev]" && pytest`. pre-commit hooks are available but not required — see `.pre-commit-config.yaml`.
