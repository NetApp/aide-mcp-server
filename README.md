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

<<<<<<< IMP-Maintainability
### Kubernetes
See [KUBERNETES](KUBERNETES.md) for deployment and usage instructions.   
=======
- Python >= 3.10
- uvx (manages all installations automatically)

### Configuration

Before running the server, you need to create a `.netapp` file in your home directory with the necessary configuration.

1. **Create the `.netapp` file**:
   - Open a terminal or file explorer.
   - Navigate to your home directory (e.g., `~` on Unix-like systems or `C:\Users\YourUsername` on Windows).
   - Create a new file named `.netapp`.

2. **Add the JSON configuration**:
   - Open the `.netapp` file in a text editor.
   - Add the following JSON configuration, replacing the example values with your own.
   - The server supports three endpoint profiles depending on your access level:

    **Search-only** — you only have a search endpoint URL (PKCE auth flow shown):

     ```json
     {
       "rag_search_api_endpoint_url": "https://<data-services-host>/api/data-engine/workspaces/<workspace-uuid>/data-collections/<datacollection-uuid>/search",
       "verify_ssl": true,
       "auth_flow": "pkce",
       "token_request_endpoint_url": "https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize",
       "token_exchange_endpoint_url": "https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token",
       "token_request_params": {
         "client_id": "your_client_id",
         "redirect_uri": "http://localhost:8888",
         "scope": "api://your-app/.default",
         "use_pkce": true,
         "auth_timeout_seconds": 300
       }
     }
     ```

    **Full access** — you have access to both the cluster management and data services interfaces (device code auth flow shown):

     ```json
     {
       "base_url": "https://<cluster-mgmt-host>/api",
       "data_services_base_url": "https://<data-services-host>/api",
       "verify_ssl": true,
       "auth_flow": "device_code",
       "device_code_endpoint_url": "https://login.microsoftonline.com/<tenant>/oauth2/v2.0/devicecode",
       "token_request_endpoint_url": "https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token",
       "token_request_params": {
         "client_id": "your_client_id",
         "scope": "api://your-app/.default"
       }
     }
     ```

   > At least one of `base_url`, `data_services_base_url`, or `rag_search_api_endpoint_url` must be present. Only PKCE (web-based) and Device Code auth flows are supported. See `Examples/.netapp.example` for all three profiles with detailed explanations.

3. **Set file permissions**:
   - Ensure that the `.netapp` file is not readable by other users/groups for security reasons.
   - On Unix-like systems, you can set the permissions using the following command:

     ```sh
     chmod 600 ~/.netapp
     ```

   - On Windows, you can set the file permissions through the file properties dialog.

>[!TIP]
>There is an `Examples` folder in the repository that contains a `.netapp.example` file. This file provides examples of how your `.netapp` file should look. You can use this as a reference when creating your own `.netapp` file.

### Running with uvx

You can run the MCP server instantly, without installing anything globally:

    ```sh
    uvx --from netapp-data-engine-mcp server
    ```

- `server` script launches the MCP server

### Troubleshooting

- Ensure your .netapp file is present and correctly formatted.
- Check that Python 3.10+ is installed 
>>>>>>> release-v2.0.0

### License
Distributed under the terms of the BSD 3-Clause License (see the `LICENSE` file in the repository).