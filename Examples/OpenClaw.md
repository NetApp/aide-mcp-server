# Use the NetApp AIDE MCP Server with OpenClaw

[OpenClaw](https://openclaw.ai) is an AI assistant gateway that connects to MCP servers. This guide shows how to register the NetApp AIDE MCP server with OpenClaw so you can search NetApp documentation directly from the OpenClaw chat interface.

## Ubuntu Desktop Quickstart

> [!NOTE]
> These steps have been validated on Ubuntu Desktop. They may work on other Linux desktop environments, but that has not been verified.

On Ubuntu Desktop, the MCP server needs access to your graphical browser to complete the PKCE OAuth flow. Because OpenClaw launches the server as a background process, it won't automatically inherit your desktop session's environment variables. The steps below create a small wrapper script that injects those variables before starting the server.

1. Create your `.netapp` file as described in the [main README](../README.md). Be sure to use PKCE authentication.

2. Register your browser as the default handler for HTTP and HTTPS so that Python's `webbrowser` module opens the correct browser during authentication.

    **Firefox:**
    ```sh
    xdg-mime default firefox.desktop x-scheme-handler/http
    xdg-mime default firefox.desktop x-scheme-handler/https
    ```

    **Google Chrome:**
    ```sh
    xdg-mime default google-chrome.desktop x-scheme-handler/http
    xdg-mime default google-chrome.desktop x-scheme-handler/https
    ```

3. Create a helper script for starting the MCP server. The script sets the environment variables needed for the browser-based OAuth flow to work correctly inside an Ubuntu desktop session.

    ```sh
    cat > ~/run-netapp-mcp.sh << 'EOF'
    #!/bin/bash

    # Force Python to use your graphical browser instead of a hidden text browser.
    # Change "firefox" to "google-chrome" if that is your default browser.
    export BROWSER=firefox

    # Inject the Wayland, X11, and DBus variables required for Ubuntu.
    export XDG_RUNTIME_DIR=/run/user/$(id -u)
    export WAYLAND_DISPLAY=wayland-0
    export DISPLAY=:0
    export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus

    # Start the MCP server.
    # Example:  exec /home/ailab/.local/bin/uvx -q --from netapp-aide-mcp server 2>> /tmp/mcp_browser_error.log
    exec <path_to_your_uvx>/uvx -q --from netapp-aide-mcp server 2>> /tmp/mcp_browser_error.log
    EOF
    ```

3. Make the script executable.

    ```sh
    chmod +x ~/run-netapp-mcp.sh
    ```

4. Add the MCP server to OpenClaw.

    ```sh
    openclaw mcp set netapp-aide '{"command": "'$HOME'/run-netapp-mcp.sh", "args": []}'
    ```

5. Restart the OpenClaw gateway.

    ```sh
    openclaw gateway restart
    ```

6. Prompt OpenClaw to search NetApp AIDE. For example: *"Search NetApp AIDE: \<your query\>"*. OpenClaw will invoke the MCP server's search tool, which opens a browser window to complete authentication before returning results.