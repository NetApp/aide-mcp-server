"""Shared async HTTP client for AIDE API requests.

Centralizes all HTTP concerns: URL construction, OAuth2 injection,
SSL configuration, error parsing, async job detection, and pagination.
Tool functions in the ``tools/`` package use this module exclusively
for API communication.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import Union

import httpx

from .oauth2 import clear_token_cache, get_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_config: dict | None = None
_http_client: httpx.AsyncClient | None = None
_client_lock: asyncio.Lock | None = None


def _get_client_lock() -> asyncio.Lock:
    """Lazily create the module-level client creation lock inside a running loop."""
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock

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
    """Store the validated config dict for use by ``aide_request``.

    If called again with a different config object (e.g. in tests or after
    reconfiguration), the shared HTTP client is invalidated so that the next
    ``_get_client()`` call recreates it with the updated ``verify_ssl`` setting.
    """
    global _config, _http_client
    if _config is not config:
        _http_client = None
    _config = config


def _get_config() -> dict:
    if _config is None:
        raise AideConfigError("Config not initialized. Call set_config() first.")
    return _config


async def _get_client() -> httpx.AsyncClient:
    """Return (or lazily create) a shared ``httpx.AsyncClient``.

    A double-checked asyncio lock prevents two concurrent coroutines from
    each observing ``_http_client is None`` and both creating a new instance.
    """
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    async with _get_client_lock():
        # Re-check inside the lock — another coroutine may have created it.
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


def _build_url(
    path: str,
    *,
    use_data_services: bool = False,
    raw_url: str | None = None,
) -> str:
    """Construct a full URL from the config base and an API path.

    When ``raw_url`` is supplied it is returned verbatim — no base URL is
    prepended.  This is the path used by Tool #17 (search) when the caller
    has not overridden the default UUIDs and ``rag_search_api_endpoint_url``
    is configured: the full pre-built URL is used directly without any path
    construction.

    Otherwise routes to either the cluster management interface or the data
    services interface based on ``use_data_services``.

    ``path`` must always be a relative path starting with ``/`` when
    ``raw_url`` is not provided — e.g. ``"/data-engine/workspaces"``.
    Callers that receive a fully-qualified ``_links.next.href`` must strip
    the origin and API prefix before passing the path here (see
    :func:`aide_request_all_pages`).

    Raises ``AideConfigError`` if the required base URL is absent — this
    should not happen in practice because ``resolve_tools()`` already
    excludes tools whose interface is unavailable.
    """
    if raw_url is not None:
        return raw_url

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
    """Extract ``(code, message, target)`` from an ONTAP error response.

    ``data`` must contain an ``"error"`` key; callers are responsible for
    checking this before calling.  Raises ``KeyError`` if the key is absent
    so that missing error structure is visible rather than silently defaulted.
    """
    if "error" not in data:
        raise KeyError("'error' key not present in response body")
    error = data["error"] if isinstance(data["error"], dict) else {}
    code = str(error.get("code", "unknown"))
    message = error.get("message") or str(data.get("error", "Unknown error"))
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
    timeout: Union[int, float, httpx.Timeout] = 30,
    use_data_services: bool = False,
    raw_url: str | None = None,
) -> dict:
    """Make an authenticated request to the ONTAP AIDE API.

    Parameters
    ----------
    method:
        HTTP method — ``"GET"``, ``"POST"``, ``"PATCH"``, or ``"DELETE"``.
    path:
        API path appended to the base URL, e.g. ``"/data-engine/workspaces"``.
        Ignored when ``raw_url`` is provided.
    params:
        Query parameters forwarded to the request.
    body:
        JSON request body (for ``POST`` / ``PATCH``).
    timeout:
        Per-request timeout — an integer/float in seconds or an
        ``httpx.Timeout`` object for fine-grained connect/read control
        (default ``30``).
    use_data_services:
        When ``True``, the request is routed to the data services interface
        (``data_services_base_url``) instead of the cluster management
        interface (``base_url``).  Ignored when ``raw_url`` is provided.
    raw_url:
        When provided, this exact URL is used verbatim — no base URL is
        prepended and ``path`` / ``use_data_services`` are ignored.  Used by
        Tool #17 (search) when ``rag_search_api_endpoint_url`` is configured
        and the caller has not overridden the default UUIDs.

    Returns
    -------
    dict
        Parsed JSON response.

        - HTTP 202: ``{"job": {"uuid": ..., "state": "queued", "_links": {...}}}``
        - HTTP 200/201 with empty body: ``{"status": "deleted"}`` /
          ``{"status": "created"}`` / ``{"status": "updated"}``
        - All other 200/201: parsed JSON body.

    Raises
    ------
    AideConfigError
        If the required base URL is absent from the config.
    AideApiError
        If the ONTAP API returns an error, the request times out, the
        connection fails, or the response cannot be parsed.
    """
    config = _get_config()
    url = _build_url(path, use_data_services=use_data_services, raw_url=raw_url)
    client = await _get_client()

    # Allow a single inline retry when a 401 indicates a stale cached token.
    for attempt in range(2):
        access_token = await get_access_token(config)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        logger.debug("%s %s  params=%s", method.upper(), url, params)

        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=body,
                headers=headers,
                timeout=timeout,
            )
        except httpx.TimeoutException:
            raise AideApiError(
                code="timeout",
                message=f"Request timed out after {timeout}s connecting to {url}",
            )
        except httpx.ConnectError as exc:
            raise AideApiError(
                code="connection_error",
                message=f"Failed to connect to {url}: {exc}",
            )

        logger.debug("Response: HTTP %s", response.status_code)

        # On the first attempt a 401 means the cached token has expired —
        # clear the cache and retry once with a fresh token.
        if response.status_code == 401 and attempt == 0:
            clear_token_cache()
            logger.warning("HTTP 401 received — retrying with a fresh token.")
            continue

        break

    # --- HTTP 401 after retry — raise clearly --------------------------------
    if response.status_code == 401:
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
            if method.upper() == "DELETE":
                status_label = "deleted"
            elif response.status_code == 201:
                status_label = "created"
            else:
                status_label = "updated"
            return {"status": status_label}
        try:
            return response.json()
        except ValueError as exc:
            raise AideApiError(
                code="parse_error",
                message=f"Failed to parse API response: {exc}",
            )

    # --- 4xx / 5xx — error -------------------------------------------------
    if response.status_code == 403:
        logger.warning(
            "HTTP 403 Forbidden from %s — check that the configured persona "
            "has the required ONTAP role for this endpoint.",
            url,
        )
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
    timeout: Union[int, float, httpx.Timeout] = 30,
    use_data_services: bool = False,
    max_pages: int = 1000,
) -> dict:
    """Fetch all pages of a paginated collection endpoint.

    Follows ``_links.next`` until exhausted and returns a single response
    dict whose ``records`` list contains every record across all pages.

    Parameters
    ----------
    method:
        HTTP method forwarded to :func:`aide_request` for each page.
    path:
        Initial API path forwarded to :func:`aide_request`.
    params:
        Query parameters forwarded to :func:`aide_request` for the first page.
        Cleared automatically on subsequent cursor pages.
    timeout:
        Per-request timeout forwarded to :func:`aide_request`.
    use_data_services:
        Interface routing flag forwarded to :func:`aide_request`.
    max_pages:
        Safety limit on the number of pages fetched (default ``1000``).
        Prevents infinite loops if the API ever returns a circular next-link.

    Returns
    -------
    dict
        ``{"num_records": N, "total_records": T, "records": [...]}``

        - ``num_records``: count of records actually fetched across all pages.
        - ``total_records``: the unpaginated total reported by the API on the
          first page; falls back to ``num_records`` if not present.
        - ``records``: flat list of all record dicts.

    Raises
    ------
    AideConfigError
        Propagated from :func:`aide_request`.
    AideApiError
        Propagated from :func:`aide_request`.
    """
    all_records: list[dict] = []
    current_path = path
    current_params: dict | None = dict(params) if params else None
    current_method = method
    pages_fetched = 0
    # The API reports the total record count on the first page response
    # (num_records field).  Capture it so it can be included in the final
    # return value; falls back to len(all_records) if not present.
    api_total_records: int | None = None

    config = _get_config()
    origin = (
        config.get("data_services_base_url", "")
        if use_data_services
        else config.get("base_url", "")
    )
    api_prefix = urllib.parse.urlparse(origin).path if origin else ""

    while True:
        if pages_fetched >= max_pages:
            logger.warning(
                "Pagination stopped after %d pages (max_pages=%d).",
                pages_fetched,
                max_pages,
            )
            break

        page = await aide_request(
            current_method,
            current_path,
            params=current_params,
            timeout=timeout,
            use_data_services=use_data_services,
        )
        pages_fetched += 1
        all_records.extend(page.get("records", []))

        # Capture the API-reported total from the first page only.
        if api_total_records is None:
            api_total_records = page.get("num_records") or page.get("total_records")

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
        # Cursor pages are always GET regardless of the original method —
        # re-sending a POST/PATCH body on a cursor URL would be incorrect.
        current_method = "GET"

    total = api_total_records if api_total_records is not None else len(all_records)
    return {
        "num_records": len(all_records),
        "total_records": total,
        "records": all_records,
    }
