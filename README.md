# netapp_mcp_server

## Description

`netapp-data-engine-mcp` is an MCP server (Python package) with custom AIDE RAG (Retrieval-Augmented Generation) search functionality. The server exposes a tool called `netapp_data_engine_search` for use in LLM workflows.

>[!NOTE]
>This MCP server uses the stdio transport, as shown in the [MCP Server Quickstart](https://modelcontextprotocol.io/quickstart/server), making it a "local MCP server". 

## Quick Start

### Prerequisites

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

You can run the MCP server from your local project directory without installing anything globally:

    ```sh
    uvx --from . server
    ```

This command finds the project in the current directory (`.`) and runs the `server` script.

### Troubleshooting

- Ensure your .netapp file is present and correctly formatted.
- Check that Python 3.10+ is installed 

### License

Distributed under the terms of the BSD 3-Clause License (see the `LICENSE` file in the repository).