# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Cursor, etc.) installing **pylot** on a user's machine.

`pylot` is a PyMOL plugin: it installs into **PyMOL's bundled Python**, not the system Python or any venv. On macOS that interpreter lives at `/Applications/PyMOL.app/Contents/bin/python`. On Linux/conda installs the path will differ — ask the user for it before running anything.

## Prerequisites to check

1. PyMOL is installed. On macOS, confirm `/Applications/PyMOL.app/Contents/bin/python` exists.
2. The repo is cloned and you are running commands from its root (the directory containing `pyproject.toml`).
3. The user is on macOS, or has told you where their PyMOL Python lives. If neither, ask — don't guess.

## Install steps

Run these in order. Each is idempotent; safe to re-run.

**0. Resolve PyMOL's Python**

Every command below assumes `$PYMOL_PYTHON` points at PyMOL's bundled interpreter. On macOS the default is `/Applications/PyMOL.app/Contents/bin/python`. On Linux/conda the path will differ — ask the user. Export it once before continuing:

```bash
export PYMOL_PYTHON=/Applications/PyMOL.app/Contents/bin/python
```

Sanity check it: `$PYMOL_PYTHON -c 'import pymol; print(pymol.__file__)'` should print a path inside the PyMOL install.

**1. Install the package into PyMOL's Python**

```bash
$PYMOL_PYTHON -m pip install --user -e .
```

**2. Hook the plugin into PyMOL startup**

```bash
$PYMOL_PYTHON -m pylot.cli install-hook
```

Appends one line to `~/.pymolrc.py` so PyMOL auto-loads the plugin.

**3. Wire up the MCP client the user is using**

Ask which client (or check the environment). Then:

- **Claude Code:**
  ```bash
  claude mcp add --transport sse --scope user pymol http://127.0.0.1:8766/sse
  ```
  Verify with `claude mcp list`.

- **Cursor:**
  ```bash
  $PYMOL_PYTHON -m pylot.cli install-config
  ```
  Writes/merges `~/.cursor/mcp.json`. Tell the user to fully quit Cursor (`Cmd+Q`) and reopen.

**4. Tell the user to restart PyMOL**

You can't do this for them. They need a full quit + relaunch (not just closing the window). On success the PyMOL console prints:

```
pylot: MCP server running on http://127.0.0.1:8766/sse
```

## Verifying the install

After the user restarts PyMOL, you can confirm the server is up:

```bash
curl -sf -m 2 http://127.0.0.1:8766/sse >/dev/null && echo OK
```

(SSE will hang open — the `-m 2` timeout is intentional; a successful connection is the signal.)

## If something goes wrong

- **No `MCP server running on...` line in PyMOL console** — `~/.pymolrc.py` isn't being loaded. Check `echo $HOME` matches where the file lives, and confirm the user did a full quit + relaunch.
- **`pip install` fails with "externally-managed-environment"** — you used the system Python, not PyMOL's. Re-check the interpreter path.
- **Port 8766 already in use** — another PyMOL instance is running, or the user wants a different port. They can run `start_mcp <port>` from the PyMOL command line; update the MCP client URL to match (`install-config --host <host> --port <port>` for Cursor, or re-run `claude mcp add` with the new URL).
- **Client running on a different machine than PyMOL** — the server binds loopback by default. The user must run `start_mcp 8766, 0.0.0.0` in PyMOL and point the client at the PyMOL host's IP.

## What NOT to do

- Don't `pip install pylot` into the system Python or a venv — the plugin will load but PyMOL won't see it.
- Don't edit `~/.pymolrc.py` by hand; use `install-hook`.
- Don't restart PyMOL yourself — the user has unsaved session state. Ask them to do it.
- Don't add `pymol` as a pip dependency. It's not on PyPI in the form this plugin needs; the user installs PyMOL.app separately.

## Uninstall

If the user asks to uninstall:

1. Remove the MCP client entry: `claude mcp remove pymol --scope user`, or for Cursor delete the `"pymol"` entry in `~/.cursor/mcp.json`.
2. Delete the two `pylot:` lines from `~/.pymolrc.py` (or the whole file if those are the only lines).
3. `$PYMOL_PYTHON -m pip uninstall pylot`
4. Ask the user to restart PyMOL.
