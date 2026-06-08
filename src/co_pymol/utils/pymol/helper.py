"""PyMOL access and the shared thread lock.

`pymol_session` is the entry point tools use — `with pymol_session() as cmd:`
resolves `cmd` and holds the lock for the block. `ensure_pymol` and `pymol_lock`
are the primitives it's built from.
"""

from __future__ import annotations

import threading

pymol_lock = threading.Lock()


def ensure_pymol():
    """Import pymol.cmd, raising a clear error if unavailable."""
    try:
        from pymol import cmd

        return cmd
    except ImportError as err:
        raise RuntimeError(
            "PyMOL is not installed. Install it with: "
            "/Applications/PyMOL.app/Contents/bin/python -m pip install -e ."
        ) from err


class pymol_session:
    """Acquire `pymol_lock` and yield `cmd` for the duration of the block.

    Folds the usual `cmd = ensure_pymol()` + `with pymol_lock:` pair into one:

        with pymol_session() as cmd:
            cmd.some_operation(arg)

    `cmd` is resolved once and cached on the class, so `ensure_pymol` only runs
    its import check the first time.
    """

    _cmd = None

    def __enter__(self):
        if pymol_session._cmd is None:
            pymol_session._cmd = ensure_pymol()
        pymol_lock.acquire()
        return pymol_session._cmd

    def __exit__(self, exc_type, exc, tb):
        pymol_lock.release()
        return False
