# Deploying to Kubernetes
This guide walks you through deploying the `aide-mcp-server` to a Kubernetes cluster and securely accessing it using local Agentic LLM clients like Claude Desktop and Gemini CLI.

> [!WARNING]
> This is not suitable for production-grade environment. It is only intended for demo purposes till the HTTP Streamable MCP server code is ready.
> Leverage [UVX](https://github.com/modelcontextprotocol/uvx) to run the server locally instead.

## Step 1: Configure the Secret
The MCP server requires the `.netapp` configuration securely loaded via a Kubernetes Secret rather than baking it into the image. 

1. Open `secret.yaml`.
2. Update the JSON block under the `stringData` section to include your specific authentication details (like your `client_id` and endpoints).
3. Apply the secret to your cluster:
   ```sh
   kubectl apply -f secret.yaml
   ```

## Step 2: Deploy the Server

The deployment manifest provisions the Kubernetes sandbox, securely mounting the Secret to `/config/.netapp`. To cleanly support multi-agent execution, the pod is configured to natively idle rather than booting the server automatically. The actual Python MCP processes are dynamically spawned per-client when they connect!

1. Review `deployment.yaml`.
2. Apply the deployment:
   ```sh
   kubectl apply -f deployment.yaml
   ```
3. Verify that the server pod is ready:
   ```sh
   kubectl get pods -l app=aide-mcp-server
   ```
   *You should see the pod in a `Running` state.*

---

## Step 3: Connecting Local LLM Clients
Because this server operates over the `stdio` transport, your local LLM clients will connect by executing a secure `kubectl exec` tunnel into the remote deployment. This ensures a raw, bidirectional JSON-RPC connection over the Kubernetes API.

> [!IMPORTANT]
> Ensure that the machine running these clients has a valid `kubeconfig` configured with `pods/exec` permissions for the active namespace.

### Connecting Claude Desktop
Configure Claude to spawn and connect to the remote server process natively.

1. Open your Claude Desktop configuration file:
   - **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
2. Add the following remote execution definition:

```json
{
  "mcpServers": {
    "netapp-aide-mcp-server": {
      "command": "kubectl",
      "args": [
        "exec",
        "-i",
        "deployment/aide-mcp-server",
        "--",
        "python",
        "-m",
        "netapp_rag_server.main"
      ]
    }
  }
}
```

3. Restart Claude Desktop. The `netapp_data_engine_search` tool will now be bridged and available!

### Connecting Gemini CLI
If you are using the Gemini CLI with MCP plugins, configure the server execution bridge identically to point through `kubectl`. 
In your Gemini CLI `mcp.json` or equivalent configuration file, define the server as:

```json
{
  "mcpServers": {
    "netapp-aide-mcp-server": {
      "command": "kubectl",
      "args": [
        "exec",
        "-i",
        "deployment/aide-mcp-server",
        "--",
        "python",
        "-m",
        "netapp_rag_server.main"
      ]
    }
  }
}
```
Run your Gemini CLI command. The CLI will execute `kubectl exec`, dynamically spawn the remote Python process, and access the NetApp MCP tools perfectly natively.
