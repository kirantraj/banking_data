"""
MCP Client — Banking Data Copilot

BankingMCPClient is an async context manager that:
  1. Spawns mcp_server/server.py as a child process.
  2. Establishes an MCP session over the child's stdin/stdout.
  3. Exposes list_tools() and call_tool() as the only public API.

The orchestrator and agents never touch the subprocess directly —
they call this thin wrapper, keeping MCP plumbing invisible.

Usage:
    async with BankingMCPClient() as mcp:
        tools  = await mcp.list_tools()
        result = await mcp.call_tool("query_bigquery", {"sql": "SELECT ..."})
"""
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Allow running from any working directory
PROJECT_ROOT = Path(__file__).parent.parent
SERVER_SCRIPT = PROJECT_ROOT / "mcp_server" / "server.py"

sys.path.insert(0, str(PROJECT_ROOT))
from utils.logger import get_logger

logger = get_logger("mcp_client")


class BankingMCPClient:
    """
    Manages the lifecycle of the MCP server subprocess and provides
    a clean async API to the rest of the application.

    Tool discovery results are cached for the lifetime of the session
    so repeated list_tools() calls don't cost extra round-trips.
    """

    def __init__(self, server_script: Path = SERVER_SCRIPT):
        self.server_script = server_script
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._tool_cache: list[dict] | None = None

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "BankingMCPClient":
        await self._connect()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self._disconnect()

    # ── Public API ────────────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict]:
        """
        Return the list of tools the MCP server advertises.
        Result is cached — safe to call many times.
        """
        if self._tool_cache is not None:
            return self._tool_cache

        response = await self._session.list_tools()
        self._tool_cache = [
            {
                "name":         t.name,
                "description":  t.description,
                "input_schema": t.inputSchema,
            }
            for t in response.tools
        ]
        logger.info(
            f"Discovered {len(self._tool_cache)} MCP tools: "
            f"{[t['name'] for t in self._tool_cache]}"
        )
        return self._tool_cache

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Invoke a named tool and return its parsed JSON result.

        Logs every call for auditability (important in banking contexts).
        Raises ValueError on empty or unparseable responses.
        """
        logger.info(
            f"→ MCP call  '{tool_name}' | "
            f"args: { {k: str(v)[:60] for k, v in arguments.items()} }"
        )

        response = await self._session.call_tool(tool_name, arguments)

        if not response.content:
            raise ValueError(f"Tool '{tool_name}' returned an empty response.")

        raw_text = response.content[0].text
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning(f"Non-JSON response from '{tool_name}': {raw_text[:200]}")
            parsed = {"raw": raw_text}

        logger.info(
            f"← MCP result '{tool_name}' | "
            f"preview: {str(parsed)[:120]}"
        )
        return parsed

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _connect(self) -> None:
        self._exit_stack = AsyncExitStack()

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(self.server_script)],
            # Pass the full environment so GCP credentials and env vars are available
            env={
                **os.environ,
                "PYTHONPATH": str(PROJECT_ROOT),
            },
        )

        read, write = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        logger.info("MCP session established ✓")

    async def _disconnect(self) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()
            logger.info("MCP session closed")
