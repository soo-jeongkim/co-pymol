"""Pure JSON-RPC message builders for the MCP proxy.

Stateless helpers that construct ``JSONRPCMessage`` envelopes. They live here —
rather than inside ``proxy.py`` — so they're independently importable and
testable, like the other cross-cutting primitives under ``utils/``.
"""

from __future__ import annotations

from mcp.types import (
    ErrorData,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCResponse,
)

from co_pymol.constants import JSONRPC_SERVER_ERROR_CODE


def rpc_id(root: object):
    """The JSON-RPC id of a message root, or None for notifications."""
    return getattr(root, "id", None)


def tool_error_response(req_id, text: str) -> JSONRPCMessage:
    """A *successful* JSON-RPC response whose result is an errored CallToolResult.

    This is how a client surfaces the failure to the user gracefully (as a tool
    result) instead of treating it as a protocol/transport error.
    """
    return JSONRPCMessage(
        JSONRPCResponse(
            jsonrpc="2.0",
            id=req_id,
            result={"content": [{"type": "text", "text": text}], "isError": True},
        )
    )


def rpc_error_response(
    req_id, text: str, code: int = JSONRPC_SERVER_ERROR_CODE
) -> JSONRPCMessage:
    return JSONRPCMessage(
        JSONRPCError(jsonrpc="2.0", id=req_id, error=ErrorData(code=code, message=text))
    )


def empty_response(req_id) -> JSONRPCMessage:
    return JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=req_id, result={}))
