# NetApp AI Data Engine (AIDE) MCP Server

## Description

`netapp-aide-mcp` is an MCP server (Python package) that exposes the [NetApp AI Data Engine](https://docs.netapp.com/us-en/ai-data-engine/index.html)'s RAG (Retrieval-Augmented Generation) search functionality via MCP. The server exposes a tool named `netapp_data_engine_search`, which provides the ability to search for documents using AIDE's RAG API. This RAG API implements a vector-based semantic similarity search engine that retrieves relevant documents based on the provided query.

>[!NOTE]
>This MCP server uses the stdio transport, making it a "local MCP server". 

## Quick start

### Prerequisites

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) (manages all installations automatically)

### Configuration

Before running the server, you need to create a `.netapp` file in your home directory with the necessary configuration.

1. **Create the `.netapp` file**:
   - Open a terminal or file explorer.
   - Navigate to your home directory (e.g., `~` on Unix-like systems or `C:\Users\YourUsername` on Windows).
   - Create a new file named `.netapp`.

2. **Add the JSON configuration**:
   - Open the `.netapp` file in a text editor.
   - Add the following JSON configuration, replacing the example values with your own:

    For PKCE flow: *(Recommended if you have a browser available on your machine)*

     ```json
     {
       "rag_search_api_endpoint_url": "https://example.com/api",
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

    For device code flow: *(Use this if you do not have a browser on your machine. A short code will be printed in the logs — copy it, open the provided verification URL on any device, and enter the code to complete authentication.)*

     ```json
     {
       "rag_search_api_endpoint_url": "https://example.com/api",
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

    >Only PKCE (web-based) and Device Code flows are supported.

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

You can run the MCP server instantly, without installing anything globally.

>[!NOTE]
>Authentication is initiated on the first tool call, not at server startup. When the first tool call is initiated: if you are using the PKCE flow, a browser window will open; if you are using the device code flow, the device code details will be printed to the MCP server's console logs. 

#### Run pre-built package from PyPI

```sh
# Run the latest stable version
uvx --from netapp-aide-mcp server

# Run a specific version
uvx --from netapp-aide-mcp==1.0.0 server
```

- `server` script launches the MCP server

#### Build and run from source

```sh
# Clone the repo
git clone https://github.com/NetApp/aide-mcp-server
cd aide-mcp-server

# Optional: check out a specific release
# git checkout tags/release-v1.0.0

# Retrieve the directory path for the cloned repo
export AIDE_MCP_REPO_PATH=$(pwd)

uvx --from $AIDE_MCP_REPO_PATH server
```

- `server` script launches the MCP server

#### Example JSON config

To use this MCP server with an MCP client, you need to configure the client to use this server. For many clients (such as [VS Code](https://code.visualstudio.com/docs/copilot/chat/mcp-servers), [Claude Desktop](https://modelcontextprotocol.io/quickstart/user), and [LMStudio](https://lmstudio.ai/docs/app/mcp)), this requires editing a config file in JSON format (often named mcp.json). Below is an example. Refer to the documentation for your MCP client for specific formatting details.

>[!NOTE]
>Most MCP clients will take care of starting the MCP server. You typically do not need to start the server yourself. As always, it's best to refer to the documentation for your MCP client for details on how it handles MCP servers.

```json
{
	"servers": {
		"netapp-aide-mcp": {
			"type": "stdio",
			"command": "uvx",
			"args": [
				"--from",
				"netapp-aide-mcp",
				"server"
			]
		}
	}
}
```


### Troubleshooting

- Ensure your .netapp file is present and correctly formatted.
- Check that Python 3.10+ and uv are installed.
- Ensure that your MCP client is compatible with the stdio transport; most desktop clients (e.g. VS Code, Claude Desktop, LMStudio) are, but some hosted clients are not.
- If you are using the device code auth flow, check the MCP server console logs for the device code details. The device code details will be printed to the logs when the first tool call is initiated.
- If your client is not invoking an MCP tool, try adding "Be sure to use NetApp AIDE" to your prompt.

### License

Distributed under the terms of the BSD 3-Clause License (see the `LICENSE` file in the repository).