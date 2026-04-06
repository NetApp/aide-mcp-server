## Quick Start

### Prerequisites
* Container runtime: Docker or compatible tool like Podman.

### Configuration
Before running the server, you need to create a `.netapp` file in your home directory with the necessary configuration.

> [!WARNING]
> For security reasons, the required `.netapp` configuration file should never be baked into the container image.
> It should be securely provided at runtime using Docker Compose secrets (for local development) or a Kubernetes Secret (for deployment).

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

### Running with Docker Compose (Recommended)

Using `docker-compose.yml` abstracts away volume mounting complexities and relies on Compose `secrets` to directly and securely handle the configuration permissions.

1. **Ensure your configuration is ready**:
   Make sure you have created your `.netapp` file in the root of the project directory.

2. **Run the MCP Server via Compose**:
   Because the MCP server uses `stdio` for its transport protocol, do not use `docker compose up` (which prefixes and breaks JSON-RPC output). Instead, use `run` which passes streams raw:

   ```sh
   docker compose run -i --rm aide-mcp-server
   ```

> [!NOTE]
> - The `-i` flag is critical to keep STDIN open for the server's `stdio` transport protocol.
> - The `--rm` flag automatically cleans up the container when it exits.
> - You can swap `docker compose` with `podman-compose` if Podman is your container engine.


### Troubleshooting
- Ensure your .netapp file is present and correctly formatted.
- Ensure your container runtime is working.