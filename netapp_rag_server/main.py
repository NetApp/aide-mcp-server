# Entry point to setup and run the MCP server

import sys
import logging
from fastmcp import FastMCP
from .tools import netapp_data_engine_search
from .config import load_credentials

# Creates the FastMCP server instance
mcp = FastMCP("NetApp RAG Search Server")

# Register the tool
mcp.tool() (netapp_data_engine_search)

if __name__ == "__main__":

    try:
        # Validates the configuration in the beginning to catch errors early
        load_credentials()

        # Sets up basic logging to capture server events and errors
        logging.basicConfig(level=logging.INFO)

        if hasattr(mcp, '_tool_manager'):
            logging.info("Registered tools:")
            logging.info(mcp._tool_manager.get_tools())

        # Starts the MCP server using stdio transport for local operation
        mcp.run(transport="stdio")

    except Exception as e:

        # Logs and prints any startup errors, then exits with an error code
        logging.error(f"Server startup failed: {e}")
        sys.exit(1)