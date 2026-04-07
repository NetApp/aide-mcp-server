# Deploying to Docker/Podman
This guide walks you through deploying the `aide-mcp-server` to a Docker/Podman container and securely accessing it using local Agentic LLM clients like Claude Desktop and Gemini CLI.

> [!WARNING]
> This is not suitable for production-grade environment. It is only intended for demo purposes till the HTTP Streamable MCP server code is ready.
> Leverage [UVX](https://github.com/modelcontextprotocol/uvx) to run the server locally instead.

## Step 1: Configure the Secret
Before running the server, you need to create a `.netapp` file with the necessary configuration in the root folder of this project.

1. **Create a directory for the MCP server**:
   ```sh
   mkdir -p ~/netapp-aide-mcp-server
   ```

2. **Create your `.netapp` configuration file**:
   - Create a file named `.netapp` in the root folder of this project.

3. **Add the JSON configuration**:
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
   - On Unix-like systems, you can set the permissions of your local file using the following command:

     ```sh
     chmod 600 .netapp
     ```

   - On Windows, you can set the file permissions through the file properties dialog.

>[!TIP]
>There is an `Examples` folder in the repository that contains a `.netapp.example` file. This file provides examples of how your `.netapp` file should look. You can use this as a reference when creating your own `.netapp` file.

## Step 2: Connecting Local LLM Clients
Because this server operates over the `stdio` transport, your local LLM clients will connect by executing a `docker compose` tunnel into the container runtime. This ensures a raw, bidirectional JSON-RPC connection.

> [!IMPORTANT]
> Ensure that the machine running these clients has Docker or Podman installed. You must provide the absolute path to your `docker-compose.yml` file using the `-f` argument so the agent can find it regardless of where it starts from.

### Connecting Claude Desktop
Configure Claude to spawn and connect to the local container process natively.

1. Open your Claude Desktop configuration file:
   - **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
2. Add the following execution definition (update `/absolute/path/to/` to where you saved the directory):

```json
{
  "mcpServers": {
    "netapp-aide-docker": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "/absolute/path/to/aide-search-mcp/docker-compose.yml",
        "run",
        "-i",
        "--rm",
        "aide-mcp-server"
      ]
    }
  }
}
```
3. Restart Claude Desktop. The `netapp_data_engine_search` tool will be bridged and available!

### Connecting Gemini CLI

If you are using the Gemini CLI with MCP plugins, configure the server execution bridge identically to point through `docker compose`. 

In your Gemini CLI `mcp.json` or equivalent configuration file, define the server as:

```json
{
  "mcpServers": {
    "netapp-aide-docker": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "/absolute/path/to/aide-search-mcp/docker-compose.yml",
        "run",
        "-i",
        "--rm",
        "aide-mcp-server"
      ]
    }
  }
}
```
*(Swap `"docker"` for `"podman"` in the `command` field if you use the Podman runtime).*

## Step 3: Troubleshooting
- Ensure your .netapp file is present and correctly formatted.
- Ensure your container runtime is working.