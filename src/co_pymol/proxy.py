"""Stdio MCP proxy that outlives PyMOL.

Run via the CLI: ``co-pymol proxy`` (see ``cli.py``). Claude Code launches it as a
subprocess and speaks the MCP **stdio** transport to it. Downstream, the proxy is
an MCP **SSE** client of the co-pymol server running inside PyMOL (default
http://127.0.0.1:8766/sse).

    Claude Code  <-[stdio]->  proxy  <-[SSE :8766]->  co-pymol (in PyMOL)

The point is to decouple Claude Code's connection lifetime from PyMOL's process
lifetime. A stdio server has no socket for Claude Code to give up on, so PyMOL
quitting/restarting never trips Claude Code's connection-retry backoff. The proxy
absorbs the downstream drop and reconnects on its own loop with no deadline.

What it does that an off-the-shelf bridge does not:
  * Caches the downstream ``initialize`` result and ``tools/list`` response on
    first connect, and answers Claude Code from cache even while PyMOL is down —
    so the server keeps *appearing* healthy across a restart.
  * On downstream reconnect, **replays** ``initialize`` +
    ``notifications/initialized`` to the fresh PyMOL server before resuming.
  * While PyMOL is down, a ``tools/call`` returns a clean tool-error result
    ("PyMOL is not connected") rather than hanging or surfacing a transport error.
  * An in-flight ``tools/call`` whose PyMOL dies mid-call gets that same error
    instead of hanging forever.

This module imports ``mcp``/``anyio`` at the top level, so it must only be
imported in an environment where the package's dependencies are installed (the
CLI defers importing it into the ``proxy`` subcommand handler for exactly this
reason — keeping ``co-pymol install-hook`` runnable under a stdlib-only Python).
stdout is the protocol channel — keep it clean. All logging goes to stderr.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import traceback
from collections.abc import Sequence

import anyio
from mcp.client.sse import sse_client
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import (
    ErrorData,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)

from co_pymol.cli import server_url
from co_pymol.constants import DEFAULT_HOST, DEFAULT_PORT

try:  # pin the negotiated protocol version to whatever this SDK ships
    from mcp.types import LATEST_PROTOCOL_VERSION as DEFAULT_PROTOCOL
except Exception:  # pragma: no cover - defensive
    DEFAULT_PROTOCOL = "2025-06-18"


# ---------------------------------------------------------------------------
# Tuning knobs (env-overridable so tests/operators can adjust without code edits)
# ---------------------------------------------------------------------------
BACKOFF_START = float(os.environ.get("PYMOL_PROXY_BACKOFF_START", "0.5"))
BACKOFF_CAP = float(os.environ.get("PYMOL_PROXY_BACKOFF_CAP", "5.0"))
# How long an upstream initialize/tools/list will wait for the *first* downstream
# connect before falling back to a synthesized (empty-tools) reply. Kept finite so
# a cold start with PyMOL not yet running doesn't hang Claude Code's handshake.
FIRST_CONNECT_WAIT = float(os.environ.get("PYMOL_PROXY_FIRST_CONNECT_WAIT", "12.0"))
ERROR_CODE = -32000  # JSON-RPC "server error" range


def log(msg: str) -> None:
    """Write a line to stderr (stdout is the protocol channel). Never raises."""
    try:
        sys.stderr.write(f"[pymol-proxy] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _rpc_id(root: object):
    return getattr(root, "id", None)


def tool_error_response(req_id, text: str) -> JSONRPCMessage:
    """A *successful* JSON-RPC response whose result is an errored CallToolResult.

    This is how Claude Code surfaces the failure to the user gracefully (as a tool
    result) instead of treating it as a protocol/transport error.
    """
    return JSONRPCMessage(
        JSONRPCResponse(
            jsonrpc="2.0",
            id=req_id,
            result={"content": [{"type": "text", "text": text}], "isError": True},
        )
    )


def rpc_error_response(req_id, text: str, code: int = ERROR_CODE) -> JSONRPCMessage:
    return JSONRPCMessage(
        JSONRPCError(jsonrpc="2.0", id=req_id, error=ErrorData(code=code, message=text))
    )


def empty_response(req_id) -> JSONRPCMessage:
    return JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=req_id, result={}))


class Proxy:
    def __init__(
        self,
        url: str,
        connect=None,
        *,
        backoff_start: float = BACKOFF_START,
        backoff_cap: float = BACKOFF_CAP,
        first_connect_wait: float = FIRST_CONNECT_WAIT,
    ) -> None:
        self.url = url

        # Downstream connection factory: a zero-arg callable returning an async
        # context manager that yields (read, write) streams. Defaults to a fresh
        # SSE client per call — so every reconnect gets a *new* downstream session
        # (the proxy never reuses a stale POST target). Injectable so tests can
        # drive a controllable fake without sockets. The timeouts are likewise
        # parameterised (defaulting to the module constants) so tests can run the
        # reconnect/backoff loop fast.
        self._connect = connect or (lambda: sse_client(self.url))
        self._backoff_start = backoff_start
        self._backoff_cap = backoff_cap
        self._first_connect_wait = first_connect_wait

        # Upstream (toward Claude Code) write stream — set once stdio is up.
        self.up_write = None

        # Downstream (toward PyMOL) write stream — present only while connected.
        self.dn_write = None

        # Cached downstream handshake artifacts. Tools are static, so once captured
        # they answer Claude Code forever, including while PyMOL is down.
        self.cached_init_result: dict | None = None
        self.cached_tools_result: dict | None = None
        self._tools_signature: str | None = None

        # Set the first time the cache is populated; lets initialize/tools/list
        # block briefly on a cold start until the first connect lands.
        self.cache_ready = anyio.Event()

        # Protocol version the *client* negotiated, reused when we (re)handshake
        # downstream so the fresh PyMOL server agrees with Claude Code.
        self.client_protocol = DEFAULT_PROTOCOL

        # Client request ids forwarded downstream and not yet answered. On a
        # downstream drop these are failed back so nothing hangs.
        self.outstanding: dict[object, str] = {}

        self._internal_counter = 0

    # -- upstream send helpers ------------------------------------------------
    async def send_up(self, msg: JSONRPCMessage) -> None:
        if self.up_write is None:
            return
        try:
            await self.up_write.send(SessionMessage(message=msg))
        except Exception as exc:  # Claude Code went away mid-write
            log(f"upstream send failed: {exc!r}")

    # -- lifecycle ------------------------------------------------------------
    async def run(self) -> None:
        async with stdio_server() as (up_read, up_write):
            await self._serve(up_read, up_write, arm_watchdog=True)

    async def _serve(self, up_read, up_write, arm_watchdog: bool = True) -> None:
        """Drive the proxy over already-open upstream streams until they close.

        Split out from ``run`` so tests can feed in-memory streams; production
        wraps it with the real ``stdio_server`` transport.
        """
        self.up_write = up_write
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._downstream_manager)
            # Upstream loop owns the lifetime: when stdin closes, Claude Code is
            # gone, so tear everything down.
            await self._upstream_loop(up_read)
            if arm_watchdog:
                # Watchdog: guarantee the process dies promptly on stdin EOF even
                # if anyio teardown wedges unwinding the reconnect loop (its sleep
                # /finally awaits can delay cancellation). The OS reclaims sockets.
                # Off in tests — os._exit would kill the test runner.
                _arm_exit_watchdog(2.0)
            tg.cancel_scope.cancel()

    # -- downstream connection management ------------------------------------
    async def _downstream_manager(self) -> None:
        backoff = self._backoff_start
        while True:
            try:
                async with self._connect() as (dn_read, dn_write):
                    await self._handshake(dn_read, dn_write)
                    self.dn_write = dn_write
                    backoff = self._backoff_start
                    log("downstream connected")
                    await self._downstream_pump(dn_read)
                    log("downstream stream ended")
            except anyio.get_cancelled_exc_class():
                raise
            except Exception as exc:
                log(f"downstream connect/serve error: {exc!r}")
            finally:
                self.dn_write = None
                await self._fail_outstanding("PyMOL disconnected")
            await anyio.sleep(backoff)
            backoff = min(backoff * 2, self._backoff_cap)

    async def _handshake(self, dn_read, dn_write) -> None:
        """Initialize the (fresh) downstream server, then capture tools/list.

        Runs before the general pump starts, reading dn_read directly for the two
        responses we care about and forwarding any interleaved notifications.
        """
        init_id = self._next_internal_id()
        init_params = {
            "protocolVersion": self.client_protocol,
            "capabilities": {},
            "clientInfo": {"name": "co-pymol-proxy", "version": "0.1"},
        }
        await dn_write.send(
            SessionMessage(
                message=JSONRPCMessage(
                    JSONRPCRequest(
                        jsonrpc="2.0",
                        id=init_id,
                        method="initialize",
                        params=init_params,
                    )
                )
            )
        )
        init_result = await self._read_until_response(dn_read, init_id)

        await dn_write.send(
            SessionMessage(
                message=JSONRPCMessage(
                    JSONRPCNotification(
                        jsonrpc="2.0", method="notifications/initialized"
                    )
                )
            )
        )

        tools_id = self._next_internal_id()
        await dn_write.send(
            SessionMessage(
                message=JSONRPCMessage(
                    JSONRPCRequest(
                        jsonrpc="2.0", id=tools_id, method="tools/list", params={}
                    )
                )
            )
        )
        tools_result = await self._read_until_response(dn_read, tools_id)

        self.cached_init_result = init_result
        changed = self._update_tools_cache(tools_result)
        if not self.cache_ready.is_set():
            self.cache_ready.set()
        if changed:
            # Tool set shifted between PyMOL instances — tell Claude Code to refetch.
            log("tools/list changed across reconnect; notifying client")
            await self.send_up(
                JSONRPCMessage(
                    JSONRPCNotification(
                        jsonrpc="2.0", method="notifications/tools/list_changed"
                    )
                )
            )

    def _update_tools_cache(self, tools_result: dict) -> bool:
        """Cache the tools list; return True if it changed from a prior connect."""
        names = sorted(t.get("name", "") for t in tools_result.get("tools", []))
        signature = "\n".join(names)
        changed = (
            self._tools_signature is not None and signature != self._tools_signature
        )
        self.cached_tools_result = tools_result
        self._tools_signature = signature
        return changed

    async def _read_until_response(self, dn_read, want_id) -> dict:
        """Read downstream messages until the response to `want_id`.

        Notifications seen along the way are forwarded upstream; other responses
        are ignored. Raises on stream end or a JSON-RPC error for `want_id`.
        """
        async for item in dn_read:
            if isinstance(item, Exception):
                raise item
            root = item.message.root
            if isinstance(root, JSONRPCResponse) and root.id == want_id:
                return root.result
            if isinstance(root, JSONRPCError) and root.id == want_id:
                raise RuntimeError(f"downstream error during handshake: {root.error}")
            if isinstance(root, JSONRPCNotification):
                await self.send_up(item.message)
            # else: a response/request we did not ask for during handshake — drop
        raise RuntimeError("downstream stream ended during handshake")

    async def _downstream_pump(self, dn_read) -> None:
        """Forward everything from PyMOL to Claude Code until the stream ends."""
        async for item in dn_read:
            if isinstance(item, Exception):
                log(f"downstream read error: {item!r}")
                return
            root = item.message.root
            rid = _rpc_id(root)
            if isinstance(root, (JSONRPCResponse, JSONRPCError)):
                self.outstanding.pop(rid, None)
            await self.send_up(item.message)

    async def _fail_outstanding(self, reason: str) -> None:
        if not self.outstanding:
            return
        pending = list(self.outstanding.items())
        self.outstanding.clear()
        for req_id, method in pending:
            if method == "tools/call":
                await self.send_up(
                    tool_error_response(req_id, f"{reason} (no PyMOL connected)")
                )
            else:
                await self.send_up(rpc_error_response(req_id, reason))

    # -- upstream request handling -------------------------------------------
    async def _upstream_loop(self, up_read) -> None:
        async for item in up_read:
            try:
                if isinstance(item, Exception):
                    log(f"upstream read error: {item!r}")
                    continue
                root = item.message.root
                if isinstance(root, JSONRPCRequest):
                    await self._handle_request(item, root)
                elif isinstance(root, JSONRPCNotification):
                    await self._handle_notification(item, root)
                else:
                    # A response from the client to a server-initiated request.
                    if self.dn_write is not None:
                        await self._forward_down(item)
            except anyio.get_cancelled_exc_class():
                raise
            except Exception:
                # Crash-proofing: one bad message must never kill the proxy.
                log("error handling upstream message:\n" + traceback.format_exc())
        log("stdin closed; shutting down")

    async def _handle_request(self, item: SessionMessage, root: JSONRPCRequest) -> None:
        method = root.method
        req_id = root.id

        if method == "initialize":
            await self._handle_initialize(req_id, root.params or {})
            return

        if method == "ping":
            # Answer locally so client health checks pass even when PyMOL is down.
            await self.send_up(empty_response(req_id))
            return

        if method == "tools/list":
            await self._handle_tools_list(req_id)
            return

        if method == "tools/call":
            if self.dn_write is not None:
                self.outstanding[req_id] = method
                await self._forward_down(item)
            else:
                name = (root.params or {}).get("name", "?")
                await self.send_up(
                    tool_error_response(
                        req_id,
                        f"PyMOL is not connected — cannot run tool '{name}'. "
                        "Open/restart PyMOL and try again.",
                    )
                )
            return

        # Anything else (resources/*, prompts/*, completion/*, ...): forward when
        # connected, else a clean error.
        if self.dn_write is not None:
            self.outstanding[req_id] = method
            await self._forward_down(item)
        else:
            await self.send_up(rpc_error_response(req_id, "PyMOL is not connected"))

    async def _handle_initialize(self, req_id, params: dict) -> None:
        # Remember the client's protocol version for downstream (re)handshakes.
        proto = params.get("protocolVersion")
        if isinstance(proto, str) and proto:
            self.client_protocol = proto

        await self._await_cache(self._first_connect_wait)

        if self.cached_init_result is not None:
            result = dict(self.cached_init_result)
        else:
            # Synthesized fallback: PyMOL wasn't up in time. Advertise listChanged
            # so we can nudge the client to refetch tools once PyMOL appears.
            result = {
                "protocolVersion": self.client_protocol,
                "serverInfo": {"name": "co-pymol (proxy)", "version": "0.1"},
                "capabilities": {"tools": {"listChanged": True}},
                "instructions": (
                    "PyMOL is not connected yet; tools appear once it starts."
                ),
            }
        result["protocolVersion"] = self.client_protocol
        caps = result.setdefault("capabilities", {})
        tools_cap = caps.setdefault("tools", {})
        if isinstance(tools_cap, dict):
            tools_cap["listChanged"] = True
        await self.send_up(
            JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=req_id, result=result))
        )

    async def _handle_tools_list(self, req_id) -> None:
        await self._await_cache(self._first_connect_wait)
        result = self.cached_tools_result or {"tools": []}
        await self.send_up(
            JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=req_id, result=result))
        )

    async def _handle_notification(
        self, item: SessionMessage, root: JSONRPCNotification
    ) -> None:
        method = root.method
        if method == "notifications/initialized":
            # The proxy already initialized its own downstream session; do not
            # double-send to PyMOL.
            return
        # Cancellations, progress acks, etc. — best-effort forward when connected.
        if self.dn_write is not None:
            await self._forward_down(item)

    async def _forward_down(self, item: SessionMessage) -> None:
        dn_write = self.dn_write
        if dn_write is None:
            return
        try:
            await dn_write.send(item)
        except Exception as exc:
            log(f"downstream send failed: {exc!r}")
            # The pump/manager will notice the drop and fail outstanding work.

    async def _await_cache(self, timeout: float) -> None:
        if self.cache_ready.is_set():
            return
        with anyio.move_on_after(timeout):
            await self.cache_ready.wait()

    def _next_internal_id(self) -> str:
        self._internal_counter += 1
        return f"proxy-{self._internal_counter}"


def _arm_exit_watchdog(seconds: float) -> None:
    """Force a hard process exit after `seconds` as a teardown backstop."""

    def _boom() -> None:
        log("watchdog: forcing exit")
        os._exit(0)

    t = threading.Timer(seconds, _boom)
    t.daemon = True
    t.start()


def run_proxy(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    """Run the proxy until stdin closes. Returns a process exit code.

    The downstream URL defaults to the co-pymol SSE endpoint for host:port, but
    PYMOL_PROXY_URL overrides it (e.g. to point at a non-default path).
    """
    url = os.environ.get("PYMOL_PROXY_URL") or server_url(host, port)

    async def _amain() -> None:
        log(f"starting; downstream = {url}")
        await Proxy(url).run()

    try:
        anyio.run(_amain)
    except KeyboardInterrupt:
        pass
    except Exception:
        log("fatal:\n" + traceback.format_exc())
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m co_pymol.proxy`` (the CLI uses run_proxy)."""
    parser = argparse.ArgumentParser(
        prog="co-pymol proxy",
        description="Stdio MCP proxy that keeps Claude Code connected across "
        "PyMOL restarts.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"co-pymol SSE host (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"co-pymol SSE port (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args(argv)
    return run_proxy(args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
