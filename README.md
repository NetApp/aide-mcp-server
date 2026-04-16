# NetApp AI Data Engine (AIDE) MCP Server

## Description
`netapp-aide-mcp` is an MCP server (Python package) for accessing [NetApp AI Data Engine](https://docs.netapp.com/us-en/ai-data-engine/index.html) (AIDE) capabilities via MCP tools, like:
-  The `netapp_data_engine_search` tool, which provides the ability to search for relevant documents using AIDE's RAG/vector search API.

Additional tools will be added in the future.

>[!NOTE]
>This MCP server uses the stdio transport, making it a "local MCP server".

## Deployments

### Run from PyPI or from source
See [UVX](DOCS/UVX.md) for deployment and usage instructions.   

### Docker/Podman
See [DOCKER](DOCS/docker/DOCKER.md) for deployment and usage instructions.   

### Kubernetes
See [KUBERNETES](DOCS/KUBERNETES.md) for deployment and usage instructions.   

## MCP Registry metadata

mcp-name: io.github.NetApp/aide-mcp-server

## License
Distributed under the terms of the BSD 3-Clause License (see the `LICENSE` file in the repository).