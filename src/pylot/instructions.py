"""MCP server instructions shown to connected agents.

The prose lives in ``instructions.md`` (alongside this module) and is read at
import time. Keeping it as markdown makes it easier to edit and review than a
long triple-quoted string.
"""

from importlib import resources

MCP_INSTRUCTIONS = (
    resources.files(__package__).joinpath("instructions.md").read_text(encoding="utf-8")
)
