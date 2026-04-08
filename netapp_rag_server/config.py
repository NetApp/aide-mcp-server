import json
import logging
import os
import re
import urllib.parse

logger = logging.getLogger(__name__)

# Matches the path portion of a fully-qualified search endpoint URL.
# Captures the workspace UUID and data-collection UUID embedded in the path.
_RAG_URL_PATTERN = re.compile(
    r"/data-engine/workspaces/([^/]+)/data-collections/([^/]+)/search/?$"
)


def _parse_rag_search_url(url: str) -> tuple[str, str, str]:
    """Extract the data-services base URL and default UUIDs from a
    fully-qualified RAG search endpoint URL.

    Expected format:
        https://<host>/api/data-engine/workspaces/<ws>/data-collections/<dc>/search

    Returns:
        (data_services_base_url, workspace_uuid, datacollection_uuid)

    Raises:
        ValueError: If the URL does not match the expected pattern.
    """
    parsed = urllib.parse.urlparse(url)
    match = _RAG_URL_PATTERN.search(parsed.path)
    if not match:
        raise ValueError(
            "Cannot parse 'rag_search_api_endpoint_url': expected path "
            "containing /data-engine/workspaces/{uuid}/data-collections/"
            f"{{uuid}}/search — got '{parsed.path}'"
        )

    workspace_uuid = match.group(1)
    datacollection_uuid = match.group(2)

    # Everything before "/data-engine" is the API root (e.g. "/api").
    api_root_end = parsed.path.find("/data-engine")
    api_root = parsed.path[:api_root_end] if api_root_end > 0 else ""
    data_services_base_url = f"{parsed.scheme}://{parsed.netloc}{api_root}"

    return data_services_base_url, workspace_uuid, datacollection_uuid


def _validate_auth_config(config: dict) -> None:
    """Validate authentication-related keys in the config dict.

    Raises:
        ValueError: If required authentication keys are missing or invalid.
    """
    if "token_request_params" not in config:
        raise ValueError(
            "Missing required key 'token_request_params' in '.netapp' file."
        )

    if not isinstance(config["token_request_params"], dict):
        raise ValueError(
            "'token_request_params' must be a JSON object in '.netapp' file."
        )

    auth_flow = config.get("auth_flow")

    if not auth_flow:
        raise ValueError(
            "Missing required key 'auth_flow' in '.netapp' file."
        )

    if auth_flow not in {"pkce", "device_code"}:
        raise ValueError("'auth_flow' must be one of: pkce, device_code.")

    if "token_request_endpoint_url" not in config:
        raise ValueError(
            "Missing required key 'token_request_endpoint_url' in '.netapp' file."
        )

    token_params = config["token_request_params"]

    if auth_flow == "pkce":
        for key in ("client_id", "redirect_uri"):
            if key not in token_params:
                raise ValueError(
                    f"Missing required key 'token_request_params.{key}' "
                    "in '.netapp' file."
                )
        token_params.setdefault("use_pkce", True)

    elif auth_flow == "device_code":
        if "device_code_endpoint_url" not in config:
            raise ValueError(
                "Missing required key 'device_code_endpoint_url' "
                "in '.netapp' file."
            )
        if "client_id" not in token_params:
            raise ValueError(
                "Missing required key 'token_request_params.client_id' "
                "in '.netapp' file."
            )


def _validate_and_derive_endpoints(config: dict) -> None:
    """Validate endpoint configuration and populate derived values.

    ONTAP exposes two network interfaces — *cluster management* and
    *data services* — each with its own hostname.  The config can supply
    endpoints in three ways (profiles):

        Search-only   — ``rag_search_api_endpoint_url`` only
        Full explicit — ``base_url`` + ``data_services_base_url``
        Full mixed    — ``base_url`` + ``rag_search_api_endpoint_url``

    When ``rag_search_api_endpoint_url`` is present, this function parses
    it to derive ``data_services_base_url`` (unless explicitly provided),
    ``default_workspace_uuid``, and ``default_datacollection_uuid``.

    The derived keys are written into *config* in-place.

    Raises:
        ValueError: If none of the three endpoint keys are present, or if
            ``rag_search_api_endpoint_url`` cannot be parsed.
    """
    has_base_url = "base_url" in config
    has_data_services = "data_services_base_url" in config
    has_rag_url = "rag_search_api_endpoint_url" in config

    if not (has_base_url or has_data_services or has_rag_url):
        raise ValueError(
            "At least one of 'base_url', 'data_services_base_url', or "
            "'rag_search_api_endpoint_url' must be present in '.netapp' file."
        )

    if has_rag_url:
        derived_base, workspace_uuid, dc_uuid = _parse_rag_search_url(
            config["rag_search_api_endpoint_url"]
        )
        config["default_workspace_uuid"] = workspace_uuid
        config["default_datacollection_uuid"] = dc_uuid

        if not has_data_services:
            config["data_services_base_url"] = derived_base

    if not has_base_url:
        logger.warning(
            "'base_url' is not configured — "
            "only the search tool will be available."
        )


def load_credentials() -> dict:
    """Load and validate configuration from ``~/.netapp``.

    Reads the JSON configuration file, validates authentication settings
    and endpoint URLs, and derives any implicit values (such as
    ``data_services_base_url`` from ``rag_search_api_endpoint_url``).

    Supports three endpoint profiles:

    * **Search-only** — ``rag_search_api_endpoint_url`` only
    * **Full (explicit)** — ``base_url`` + ``data_services_base_url``
    * **Full (mixed)** — ``base_url`` + ``rag_search_api_endpoint_url``

    Returns:
        Validated configuration dictionary with derived fields populated.

    Raises:
        FileNotFoundError: If ``~/.netapp`` does not exist.
        ValueError: If required keys are missing or invalid.
    """
    credentials_path = os.path.expanduser("~/.netapp")

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            "Credentials file '.netapp' not found in the user's home directory."
        )

    with open(credentials_path, "r") as f:
        config = json.load(f)

    if "verify_ssl" not in config:
        raise ValueError("Missing required key 'verify_ssl' in '.netapp' file.")

    if not isinstance(config["verify_ssl"], bool):
        raise ValueError(
            "'verify_ssl' must be a boolean (true or false) in '.netapp' file, "
            f"got {type(config['verify_ssl']).__name__}."
        )

    _validate_auth_config(config)
    _validate_and_derive_endpoints(config)

    return config
