"""Error marshalling for MCP tools.

MCP tools must return a string, so a raised exception has to become an
`Error: ...` message somewhere. Rather than each tool wrapping its body in
try/except, tools raise normally and `@error_wrapper` turns any exception into
that string at the boundary.
"""

from __future__ import annotations

import functools
from collections.abc import Callable


def error_wrapper(fn: Callable) -> Callable:
    """Turn any exception raised by an MCP tool into an `Error: ...` string."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return f"Error: {e}"

    return wrapper
