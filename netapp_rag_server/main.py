# Copyright 2026 NetApp, Inc. All Rights Reserved.

# Entry point to setup and run the MCP server

import asyncio
import contextlib
import logging
import sys

from fastmcp import FastMCP

from .client import close_client, set_config
from .config import load_credentials
from .oauth2 import authenticate_eagerly, start_token_refresh_loop
from .tools import netapp_data_engine_search

# Creates the FastMCP server instance
mcp = FastMCP("NetApp AI Data Engine (AIDE) MCP Server")

# Register the tool
mcp.tool()(netapp_data_engine_search)


async def _async_main() -> None:
    config = load_credentials()
    set_config(config)

    # Completes interactive OAuth here so later tool calls reuse the same session.
    logging.info("Starting OAuth2 login (complete in the browser if prompted)...")
    await authenticate_eagerly(config)

    # Keeps the access token renewed while this process runs the MCP stdio transport.
    refresh_task = start_token_refresh_loop(config)

    if hasattr(mcp, "_tool_manager"):
        logging.info("Registered tools:")
        logging.info(mcp._tool_manager.get_tools())

    try:
        await mcp.run_async(transport="stdio")
    finally:
        # Stops the background refresh coroutine when stdio shuts down.
        refresh_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await refresh_task
        await close_client()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        # Single event loop drives OAuth, token refresh, and the MCP server.
        asyncio.run(_async_main())
    except Exception as e:
        logging.error(f"Server startup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
