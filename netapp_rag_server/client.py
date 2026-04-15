"""Shared async HTTP client for AIDE API requests.

Centralizes all HTTP concerns: URL construction, OAuth2 injection,
SSL configuration, error parsing, async job detection, and pagination.
Tool functions in the ``tools/`` package use this module exclusively
for API communication.
"""

from __future__ import annotations

import logging
import urllib.parse

import httpx

from .oauth2 import clear_token_cache, get_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_config: dict | None = None
_http_client: httpx.AsyncClient | None = None

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AideConfigError(Exception):
    """Raised when the server config is insufficient for the requested operation."""


class AideApiError(Exception):
    """Raised when the ONTAP API returns an error response."""

    def __init__(self, code: str, message: str, target: str | None = None):
        self.code = code
        self.message = message
        self.target = target
        super().__init__(f"API Error {code}: {message}")


# ---------------------------------------------------------------------------
# Config / client lifecycle
# ---------------------------------------------------------------------------


def set_config(config: dict) -> None:
    """Store the validated config dict for use by ``aide_request``."""
    global _config
    _config = config


def _get_config() -> dict:
    if _config is None:
        raise AideConfigError("Config not initialized. Call set_config() first.")
    return _config


async def _get_client() -> httpx.AsyncClient:
    """Return (or lazily create) a shared ``httpx.AsyncClient``."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        config = _get_config()
        _http_client = httpx.AsyncClient(verify=config["verify_ssl"])
    return _http_client


async def close_client() -> None:
    """Close the shared HTTP client, releasing connection resources."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def _build_url(path: str, *, use_data_services: bool = False) -> str:
    """Construct a full URL from the config base and an API path.

    Routes to either the cluster management interface or the data services
    interface based on *use_data_services*.

    Raises ``AideConfigError`` if the required base URL is absent — this
    should not happen in practice because ``resolve_tools()`` already
    excludes tools whose interface is unavailable.
    """
    config = _get_config()
    if use_data_services:
        base = config.get("data_services_base_url")
        if not base:
            raise AideConfigError(
                "data_services_base_url is not configured. "
                "Search requires the data services interface."
            )
    else:
        base = config.get("base_url")
        if not base:
            raise AideConfigError(
                "base_url is not configured. "
                "This operation requires the cluster management interface."
            )
    return f"{base.rstrip('/')}{path}"


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _parse_error_body(data: dict) -> tuple[str, str, str | None]:
    """Extract ``(code, message, target)`` from an ONTAP error response."""
    error = data.get("error", {})
    code = str(error.get("code", "unknown"))
    message = error.get("message", "Unknown error")
    target = error.get("target")
    return code, message, target


# ---------------------------------------------------------------------------
# Core request function
# ---------------------------------------------------------------------------


async def aide_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    timeout: int = 30,
    use_data_services: bool = False,
) -> dict:
    """Make an authenticated request to the ONTAP AIDE API.

    Parameters
    ----------
    method:
        HTTP method — ``"GET"``, ``"POST"``, ``"PATCH"``, or ``"DELETE"``.
    path:
        API path appended to the base URL, e.g.
        ``"/data-engine/workspaces"``.
    params:
        Query parameters forwarded to the request.
    body:
        JSON request body (for ``POST`` / ``PATCH``).
    timeout:
        Per-request timeout in seconds.
    use_data_services:
        When ``True``, the request is routed to the data services
        interface (``data_services_base_url``) instead of the cluster
        management interface (``base_url``).

    Returns
    -------
    dict
        Parsed JSON response.  For HTTP 202 the return value is
        ``{"job": {"uuid": ..., "state": ..., "_links": ...}}``.
        For HTTP 200 with an empty body (e.g. after DELETE) the return
        value is ``{"status": "deleted"}``.

    Raises
    ------
    AideConfigError
        If the required base URL is absent from the config.
    AideApiError
        If the ONTAP API returns an error or the response cannot be
        parsed.
    """
    config = _get_config()
    url = _build_url(path, use_data_services=use_data_services)

    access_token = await get_access_token(config)
    headers = {"Authorization": f"Bearer {access_token}"}

    client = await _get_client()

    try:
        response = await client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=body if body is not None else None,
            headers=headers,
            timeout=timeout,
        )
    except httpx.TimeoutException:
        raise AideApiError(
            code="timeout",
            message=f"Request timed out after {timeout}s connecting to {url}",
        )

    # --- HTTP 401 — clear the token cache for retry on next call -----------
    if response.status_code == 401:
        clear_token_cache()
        try:
            data = response.json()
            code, message, target = _parse_error_body(data)
        except (ValueError, KeyError):
            code, message, target = "401", "Unauthorized", None
        raise AideApiError(code=code, message=message, target=target)

    # --- HTTP 202 — async job accepted -------------------------------------
    if response.status_code == 202:
        try:
            data = response.json()
        except ValueError as exc:
            raise AideApiError(
                code="parse_error",
                message=f"HTTP 202 but failed to parse job details: {exc}",
            )
        job = data.get("job", {})
        return {
            "job": {
                "uuid": job.get("uuid", ""),
                "state": job.get("state", "queued"),
                "_links": job.get("_links", {}),
            }
        }

    # --- HTTP 200 / 201 — success ------------------------------------------
    if response.status_code in (200, 201):
        if not response.content:
            status_label = "deleted" if method.upper() == "DELETE" else "updated"
            return {"status": status_label}
        try:
            return response.json()
        except ValueError as exc:
            raise AideApiError(
                code="parse_error",
                message=f"Failed to parse API response: {exc}",
            )

    # --- 4xx / 5xx — error -------------------------------------------------
    try:
        data = response.json()
        if "error" in data:
            code, message, target = _parse_error_body(data)
            raise AideApiError(code=code, message=message, target=target)
        raise AideApiError(
            code=str(response.status_code),
            message=str(data),
        )
    except ValueError:
        raise AideApiError(
            code=str(response.status_code),
            message=response.text or f"HTTP {response.status_code}",
        )


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------


async def aide_request_all_pages(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    timeout: int = 30,
    use_data_services: bool = False,
) -> dict:
    """Fetch all pages of a paginated collection endpoint.

    Follows ``_links.next`` until exhausted and merges every page's
    ``records`` into a single response dict.

    Returns
    -------
    dict
        ``{"num_records": N, "total_records": N, "records": [...]}``
    """
    all_records: list[dict] = []
    current_path = path
    current_params = dict(params) if params else None

    config = _get_config()
    origin = (
        config.get("data_services_base_url", "")
        if use_data_services
        else config.get("base_url", "")
    )
    api_prefix = urllib.parse.urlparse(origin).path if origin else ""

    while True:
        page = await aide_request(
            method,
            current_path,
            params=current_params,
            timeout=timeout,
            use_data_services=use_data_services,
        )
        all_records.extend(page.get("records", []))

        next_href = page.get("_links", {}).get("next", {}).get("href")
        if not next_href:
            break

        parsed = urllib.parse.urlparse(next_href)
        next_path = parsed.path
        if api_prefix and next_path.startswith(api_prefix):
            next_path = next_path[len(api_prefix):]

        current_path = next_path
        qs = urllib.parse.parse_qs(parsed.query)
        current_params = (
            {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
            if qs
            else None
        )

    return {
        "num_records": len(all_records),
        "total_records": len(all_records),
        "records": all_records,
    }
