# netapp_mcp_server

## Description

`netapp_mcp_server` is an MCP server with custom AIDP RAG search functionality. The server provides a tool called `netapp_data_engine_search`. This project is a work in progress, and the AIDP RAG endpoints are yet to be integrated.

### NOTE

This MCP server uses the stdio transport as shown in the MCP Server Quickstart (MCP official documentation). The use of the stdio transport implies that this MCP server will be what is known as a "local MCP server," which means that users will run it locally wherever they are running their MCP client.

## Setup Instructions

### Prerequisites

Before you begin, ensure you have the following installed on your system:

- Python (>= 3.10)
- pip (Python package installer)

### Creating the `.netapp` File

Before running the server, you need to create a `.netapp` file in your home directory with the necessary configuration.

1. **Create the `.netapp` file**:
   - Open a terminal or file explorer.
   - Navigate to your home directory (e.g., `~` on Unix-like systems or `C:\Users\YourUsername` on Windows).
   - Create a new file named `.netapp`.

2. **Add the JSON configuration**:
   - Open the `.netapp` file in a text editor.
   - Add the following JSON configuration, replacing the example values with your own:

     ```json
     {
         "rag_search_api_endpoint_url": "https://example.com/api",
         "token_request_endpoint": "https://example.com/oauth2/token",
         "token_request_params": {
             "client_id": "your_client_id",
             "client_secret": "your_client_secret",
             "scope": "your_scope",
             "grant_type": "client_credentials"
         },
         "verify_ssl": true
     }
     ```

3. **Set file permissions**:
   - Ensure that the `.netapp` file is not readable by other users/groups for security reasons.
   - On Unix-like systems, you can set the permissions using the following command:

     ```sh
     chmod 600 ~/.netapp
     ```

   - On Windows, you can set the file permissions through the file properties dialog.

### Examples Folder

There is an `Examples` folder in the repository that contains a `.netapp.example` file. This file provides an example of how your `.netapp` file should look. You can use this as a reference when creating your own `.netapp` file.

### Cloning the Repository

1. Clone the repository:

    ```sh
    git clone https://bitbucket.ngage.netapp.com/scm/sie-bb/netapp_mcp_server.git
    cd netapp_mcp_server
    ```

### Ensuring `uv` Package is Installed

2. Install `uv` if not already installed:

    Follow [these](https://docs.astral.sh/uv/getting-started/installation/#pypi) instructions to install uv/ uvx

### Installing Python dependencies

3. Install Python dependencies:

    `uv` will automatically install all dependencies when you run any project command.

### To run the modelcontextprotocol server

4. Run mcp server:

    ```sh
    server
    ```

### To run the modelcontextprotocol inspector with a running server

5. Run mcp inspector with a running server:

    ```sh
    inspector
    ```