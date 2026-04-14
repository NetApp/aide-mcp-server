# NetApp AI Data Engine MCP Server - AI Agent Instructions

## Project Overview
This repository contains `aide-mcp-server`, a Model Context Protocol (MCP) server written in Python. It exposes NetApp AI Data Engine (AIDE) RAG capabilities to local LLM clients (like Claude Desktop or IDEs) via the `netapp_data_engine_search` MCP tool.
- **Communication Protocol**: Standard I/O (`stdio`) or HTTP (for future use).
- **Core Functionality**: Semantic search / Retrieval-Augmented Generation (RAG) against internal corporate endpoints.
- **AI/LLM Agnostic**: The server is AI/LLM agnostic and can be used with any LLM client that supports the MCP protocol.
- **Security**: The server uses OAuth 2.0 for authentication and authorization.
- **Deployment**: The server can be run locally or deployed as a Docker container using Docker, Podman, or Kubernetes.

## Technology Stack & Tooling
When writing code or suggesting commands in this repository, strictly adhere to the following stack:
- **Language**: Python 3.13+
- **Dependency Management & Running**: We use `uv` and `uvx`. Do NOT use `pip`, `venv`, `poetry`, or `conda`.
  - Always run the server locally using: `uvx --from . server`
- **Containerization**: Docker / Docker Compose. The server is ultimately distributed as a Docker container published to `ghcr.io`.
- **Frameworks**: `fastmcp` for routing and server definitions.

## Credentials & Configuration
- **Never hardcode secrets.**
- The application relies on a `.netapp` JSON configuration file (stored in `~/.netapp` locally, or mounted via volumes in containers).
- The `.netapp` file controls authentication. We support two OAuth 2.0 flows: `pkce` (browser-based) and `device_code` (headless).
- If you need to test configuration parsing, provide examples structured like the `.netapp.example` file.

## Coding Conventions & Style
- **Type Hinting**: Use strict Python type hints everywhere.
- **Asynchronous Code**: Use `asyncio` wherever possible, especially for network requests (e.g., using `httpx`) to the AIDE backend.
- **Error Handling**: Catch specific exceptions. When network connectivity or authentication to the RAG endpoint fails, return graceful, conversational error messages via the MCP protocol rather than crashing the `stdio` stream.
- **Documentation**: Always update the `README.md`, `DOCKER.md`, `KUBERNETES.md`, and `UVX.md` files when making changes to the server. DO NOT MODIFY the `AGENT.md` file.

## CI/CD & Deployment
- We use GitHub Actions. Automatically built images are tagged via semantic versioning (e.g., `v2.0.0`) and pushed to the GitHub Container Registry.
- Do not modify workflow files without explicitly checking if the changes align with our `docker-publish.yml` logic (which relies on `docker/metadata-action`).
