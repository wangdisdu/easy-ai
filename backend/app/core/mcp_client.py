"""MCP client: connect to MCP servers and discover/invoke tools."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)


class McpToolInfo:
    """Discovered tool from an MCP server."""

    def __init__(self, name: str, description: str, parameters: dict[str, Any]) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


async def _discover_sse(url: str, headers: dict[str, str] | None) -> list[McpToolInfo]:
    async with sse_client(url=url, headers=headers or {}) as streams:
        read_stream, write_stream = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                McpToolInfo(
                    name=t.name,
                    description=t.description or "",
                    parameters=t.inputSchema if t.inputSchema else {},
                )
                for t in result.tools
            ]


async def _discover_streamable_http(url: str, headers: dict[str, str] | None) -> list[McpToolInfo]:
    async with (
        httpx.AsyncClient(headers=headers or None) as http_client,
        streamable_http_client(url=url, http_client=http_client) as streams,
    ):
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                McpToolInfo(
                    name=t.name,
                    description=t.description or "",
                    parameters=t.inputSchema if t.inputSchema else {},
                )
                for t in result.tools
            ]


def discover_tools(
    transport: str, url: str, headers: dict[str, str] | None = None
) -> list[McpToolInfo]:
    """Synchronously discover tools from an MCP server.

    Args:
        transport: "sse" or "streamable_http"
        url: MCP server endpoint URL
        headers: optional HTTP headers (e.g. auth)

    Returns:
        List of discovered tools

    Raises:
        ValueError: invalid transport
        Exception: connection / protocol errors
    """
    if transport == "sse":
        coro = _discover_sse(url, headers)
    elif transport == "streamable_http":
        coro = _discover_streamable_http(url, headers)
    else:
        raise ValueError(f"unsupported transport: {transport}")

    return _run_sync(coro, timeout=30)


# ── Tool invocation ──


async def _call_sse(
    url: str,
    headers: dict[str, str] | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    async with sse_client(url=url, headers=headers or {}) as streams:
        read_stream, write_stream = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return _coerce_call_result(result, tool_name)


async def _call_streamable_http(
    url: str,
    headers: dict[str, str] | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    async with (
        httpx.AsyncClient(headers=headers or None) as http_client,
        streamable_http_client(url=url, http_client=http_client) as streams,
    ):
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return _coerce_call_result(result, tool_name)


def call_tool(
    transport: str,
    url: str,
    tool_name: str,
    arguments: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> str:
    """Synchronously invoke a tool on an MCP server and return its text result.

    Args:
        transport: "sse" or "streamable_http"
        url: MCP server endpoint URL
        tool_name: tool name to invoke
        arguments: arguments dict matching the tool input schema
        headers: optional HTTP headers (e.g. auth)
        timeout: max wait in seconds; enforced inside the coroutine via
            ``asyncio.timeout`` so it fires regardless of how ``_run_sync``
            schedules execution. Raises ``TimeoutError`` on expiry.

    Raises:
        ValueError: invalid transport
        TimeoutError: tool didn't return within ``timeout`` seconds
        RuntimeError: tool reported an error
    """
    if transport == "sse":
        inner = _call_sse(url, headers, tool_name, arguments)
    elif transport == "streamable_http":
        inner = _call_streamable_http(url, headers, tool_name, arguments)
    else:
        raise ValueError(f"unsupported transport: {transport}")

    return _run_sync(_with_timeout(inner, timeout, tool_name), timeout=timeout)


async def _with_timeout(coro: Any, timeout: float, tool_name: str) -> Any:
    """把 timeout 推到协程内部，asyncio.timeout 会真正取消未完成的子任务，
    避免 ``Future.result(timeout=...)`` 那种"主线程不等了但底层还在跑"的资源泄漏。
    """
    try:
        async with asyncio.timeout(timeout):
            return await coro
    except TimeoutError as exc:
        raise TimeoutError(f"mcp tool {tool_name} did not respond within {timeout:.0f}s") from exc


def _coerce_call_result(result: Any, tool_name: str) -> str:
    """Convert an MCP CallToolResult to a plain string for LLM consumption."""
    is_error = bool(getattr(result, "isError", False))
    parts: list[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(str(text))
        else:
            parts.append(str(item))
    payload = "\n".join(parts).strip()
    if is_error:
        raise RuntimeError(f"mcp tool {tool_name} reported error: {payload or '<no detail>'}")
    return payload


def _run_sync(coro: Any, *, timeout: float) -> Any:
    """Run an awaitable from sync code, even when an event loop is already active."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=timeout)
    return asyncio.run(coro)
