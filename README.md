# netapp_mcp_server

## Description

`netapp_mcp_server` is an MCP server with custom AIDP RAG search functionality. The server provides a tool called `netapp_data_engine_search`. This project is a work in progress, and the AIDP RAG endpoints are yet to be integrated.

## Setup Instructions

### Prerequisites

Before you begin, ensure you have the following installed on your system:

- Python (>= 3.7)
- pip (Python package installer)
- Node.js and npm (Node package manager)

### Cloning the Repository

1. Clone the repository:

    ```sh
    git clone https://bitbucket.ngage.netapp.com/scm/sie-bb/netapp_mcp_server.git
    cd netapp_mcp_server
    ```

### Installing Python Dependencies

2. Install `pip-tools` if not already installed:

    ```sh
    pip install pip-tools
    ```

### Ensuring `uv` Package is Installed

3. If the `uv` package is not installed:

    ```sh
    pip install uv
    ```

4. Run the setup script to install dependencies and set up the environment:

    ```sh
    ./setup.sh
    ```

    This script will:
    - Create a cache directory for `uv`.
    - Set the `UV_CACHE_DIR` environment variable.
    - Add the environment variable to `.bashrc` if not already present.
    - Source `.bashrc` to apply changes.
    - Generate a `requirements.txt` file from `pyproject.toml` if it doesn't exist.
    - Install the dependencies listed in `requirements.txt`.
    - Verify the installation of `fastmcp`.

### Installing npm Modules

5. Install npm modules:

    ```sh
    npm install
    ```

### To run the modelcontextprotocol server

6. Run mcp server:

    ```sh
    npm run server
    ```

### To run the modelcontextprotocol inspector with a running server

7. Run mcp inspector with a running server:

    ```sh
    npm run inspector
    ```