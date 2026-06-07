# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Cursor, etc.) working with **pylot**.

**What pylot is:** a PyMOL plugin that starts an MCP server inside PyMOL's own Python process, exposing the `pymol.cmd` API (plus a gemmi-backed metrics layer for pLDDT/ipTM/pTM/PAE) as tools. Once installed, an MCP client like Claude Code or Cursor can drive PyMOL in natural language.

Two scenarios — jump to whichever fits:

1. **You're editing this repo** → see [§1 Working on this repo](#1-working-on-this-repo).
2. **You're helping a user install pylot on their machine** → see [§2 Installing pylot on a user's machine](#2-installing-pylot-on-a-users-machine).

---

## 1. Working on this repo

### Architecture

- **Plugin runs inside PyMOL's process.** On startup (`__init_plugin__`), an MCP server launches in a daemon background thread on port 8766.
- **MCP server** (`src/pylot/server.py`) exposes PyMOL's `cmd` module as MCP tools. MCP clients (Claude Code, Cursor, etc.) connect via `http://localhost:8766/sse`.
- **Metrics** (`src/pylot/core/metrics.py`) uses gemmi for structure metadata extraction — not PyMOL. This keeps metric parsing clean and avoids polluting PyMOL's object state. Reads PAE/ipTM/pTM from `_ma_qa_metric_*` categories in mmCIF first, falls back to sibling JSON.
- **Triage** (`src/pylot/core/triage.py`) manages navigation/flagging state for reviewing batches of structures (mobile eval workflow).

### Layers

The package uses a **src-layout**: it lives at `src/pylot/`. Inside it:

- **package root** (`__init__.py`, `cli.py`, `server.py`) — entry points; `constants.py` holds shared constants (port, palette, etc.); `instructions.py` loads `MCP_INSTRUCTIONS` from the sibling `instructions.md`. No domain logic.
- **`core/`** — domain logic + state, no MCP: `session.py` (per-session state), `metrics.py` and `triage.py` (pure, no PyMOL). `triage_view.py` is the one exception — it drives PyMOL to render a focused structure (`triage_render`); the pure triage state stays in `triage.py`. `session` depends on `metrics`/`triage`.
- **`utils/pymol/`** — cross-cutting PyMOL primitives: `helper.py` (`ensure_pymol`, `pymol_lock`) and `render.py` (`render_image`, `apply_plddt_palette`).
- **`tools/`** — thin MCP wrappers, one `register_*_tools(mcp)` per file; no logic beyond marshalling to `core/` and `utils/`.

### Thread safety

All `pymol.cmd` calls are serialized with `pymol_lock` (a `threading.Lock`). The MCP server runs in a daemon thread; PyMOL's GUI runs on the main thread. Rendering (`cmd.ray`, `cmd.png`) definitely needs the lock. Most read operations work from threads in modern PyMOL, but we lock everything for safety.

### Agent-facing behavior

The MCP server pushes its own instructions (`src/pylot/instructions.md`) to every connected client. That file is the right place to change cross-client agent behavior (e.g. "don't auto-render after operations") — not this AGENTS.md, and not per-client config.

### Dev setup

Install into PyMOL's bundled Python (the same rule as the user-facing install — see §2 for the full playbook with troubleshooting):

```bash
/Applications/PyMOL.app/Contents/bin/python -m pip install --user -e ".[dev]"
```

Then:

- **Tests:** `pytest`
- **Pre-commit hooks (optional):** `pre-commit install` — see `.pre-commit-config.yaml`
- **Commit style:** `type: subject` (see `git log` for examples — `refactor:`, `docs:`, `chore:`, `fix:`, etc.)

### How to add new tools

1. Add a `register_*_tools(mcp)` function in the relevant `src/pylot/tools/` file (or a new one), then call it from `create_server()` in `src/pylot/server.py`
2. Inside the register function, add a new function decorated with `@mcp.tool()`
3. Use `pymol_lock` for any `pymol.cmd` calls
4. Return a string (status message) or `Image` (for rendered output)

```python
@mcp.tool()
def my_new_tool(arg: str) -> str:
    """Description shown to Claude."""
    cmd = ensure_pymol()
    with pymol_lock:
        cmd.some_operation(arg)
        return f"Done: {arg}"
```

### Dependencies

- `mcp~=1.27.1` — official MCP Python SDK; we use its bundled `mcp.server.fastmcp.FastMCP` (no standalone `fastmcp` package). Pinned tight on purpose — MCP is pylot's network-facing trust boundary and `FastMCP` has had API churn between minors; bump the pin deliberately, not opportunistically.
- `gemmi>=0.6` — mmCIF/PDB parsing for metrics (atom data + AF3 `_ma_qa_metric_*`)
- `numpy` — array ops for pLDDT/PAE in metrics
- PyMOL — **not a pip dependency**, install the app from pymol.org. Install this plugin into PyMOL's Python: `/Applications/PyMOL.app/Contents/bin/python -m pip install --user -e .`

---

## 2. Installing pylot on a user's machine

Because pylot lives inside PyMOL, it installs into **PyMOL's bundled Python**, not the system Python or any venv. On macOS that interpreter lives at `/Applications/PyMOL.app/Contents/bin/python`. On Linux/conda installs the path will differ — ask the user for it before running anything. If they're not sure, `which pymol` followed by checking for a sibling `python` in the same `bin/` directory is usually the right interpreter.

### Prerequisites to check

1. PyMOL is installed. On macOS, confirm `/Applications/PyMOL.app/Contents/bin/python` exists.
2. The repo is cloned and you are running commands from its root (the directory containing `pyproject.toml`).
3. The user is on macOS, or has told you where their PyMOL Python lives. If neither, ask — don't guess.

### Install steps

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

Appends two lines (a sentinel comment + the import) to `~/.pymolrc.py` so PyMOL auto-loads the plugin. Safe to run against an existing `~/.pymolrc.py` — it appends rather than overwrites, and is a no-op if the line is already present. Do not edit the file by hand.

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

### Verifying the install

After the user restarts PyMOL, confirm the server is reachable:

```bash
curl -sf -m 2 http://127.0.0.1:8766/sse >/dev/null && echo OK
```

(SSE will hang open — the `-m 2` timeout is intentional; a successful connection is the signal.)

That only proves the port is open. For a real end-to-end check, have the user ask their MCP client to call a trivial pymol tool — e.g. "in pymol, what version is loaded?" should round-trip through `cmd.get_version`. If the curl check passes but the tool call doesn't, the MCP client isn't actually wired to the `pymol` server (re-check step 3).

### If something goes wrong

- **No `MCP server running on...` line in PyMOL console** — `~/.pymolrc.py` isn't being loaded. Check `echo $HOME` matches where the file lives, and confirm the user did a full quit + relaunch.
- **`pip install` fails with "externally-managed-environment"** — you used the system Python, not PyMOL's. Re-check the interpreter path.
- **Port 8766 already in use** — another PyMOL instance is running, or the user wants a different port. They can run `start_mcp <port>` from the PyMOL command line; update the MCP client URL to match (`install-config --host <host> --port <port>` for Cursor, or re-run `claude mcp add` with the new URL).
- **Client running on a different machine than PyMOL** — the server binds loopback by default. The user must run `start_mcp 8766, 0.0.0.0` in PyMOL and point the client at the PyMOL host's IP.

### What NOT to do

- Don't `pip install pylot` into the system Python or a venv — the plugin will load but PyMOL won't see it.
- Don't edit `~/.pymolrc.py` by hand; use `install-hook`.
- Don't restart PyMOL yourself — the user has unsaved session state. Ask them to do it.
- Don't add `pymol` as a pip dependency. It's not on PyPI in the form this plugin needs; the user installs PyMOL.app separately.

### Uninstall

If the user asks to uninstall:

1. Remove the MCP client entry: `claude mcp remove pymol --scope user`, or for Cursor delete the `"pymol"` entry in `~/.cursor/mcp.json`.
2. Delete the two `pylot:` lines from `~/.pymolrc.py` (or the whole file if those are the only lines).
3. `$PYMOL_PYTHON -m pip uninstall pylot`
4. Ask the user to restart PyMOL.
