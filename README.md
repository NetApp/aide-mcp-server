# NetApp MCP Server for AI Data Engine (AIDE)

## Description
`netapp-data-engine-mcp` is an MCP server (Python package) to access the NetApp AI Data Engine (AIDE) capabilities via MCP tools, like:
-  The `netapp_data_engine_search` tool for RAG (Retrieval-Augmented Generation) search functionality.

Additional tools will be added in the future.

>[!NOTE]
>This MCP server uses the stdio transport, as shown in the [MCP Server Quickstart](https://modelcontextprotocol.io/quickstart/server), making it a local-first MCP server for Agentic workflows with Claude Code, Copilot CLI, Gemini CLI, and others.

## Deployments
### Running from Sources
See [UVX](DOCS/UVX.md) for deployment and usage instructions.   

### Docker/Podman
See [DOCKER](DOCS/docker/DOCKER.md) for deployment and usage instructions.   

### Kubernetes
See [KUBERNETES](DOCS/KUBERNETES.md) for deployment and usage instructions.   

### License
Distributed under the terms of the BSD 3-Clause License (see the `LICENSE` file in the repository).