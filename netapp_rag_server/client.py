"""
Shared async HTTP client for the NetApp AIDE MCP server.

All HTTP concerns are centralized here:
  - URL construction (base_url vs data_services_base_url)
  - OAuth2 token injection
  - SSL configuration
  - Error parsing and exception hierarchy
  - HTTP 202 / async-job detection
  - Pagination cursor following

Tool functions import ``aide_request`` and ``aide_request_all_pages``; they
focus solely on parameter mapping and response formatting.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import AsyncIterator

import httpx

from .config import load_credentials
from .oauth2 import clear_token_cache, get_access_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class AideConfigError(Exception):
    """Raised when the server config is insufficient for the requested operation.

    This normally should not surface at runtime because ``resolve_tools()``
    already excludes tools whose required interface is not configured, but it
    acts as a safety net for unexpected code paths.
    """


class AideApiError(Exception):
    """Raised when the AIDE / ONTAP API returns an error response.

    Attributes:
        code:    The error code string returned by the API (e.g. ``"404"``).
        message: The human-readable error message from the API.
        target:  Optional field name / path that caused the error, if present.
    """

    def __init__(self, code: str, message: str, target: str | None = None) -> None:
        self.code = code
        self.message = message
        self.target = target
        super().__init__(f"API Error {code}: {message}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_url(config: dict, path: str, *, use_data_services: bool) -> str:
    """Construct the full request URL from *config* and a relative *path*.

    Parameters
    ----------
    config:
        Validated configuration dictionary (output of :func:`load_credentials`).
    path:
        Relative API path, e.g. ``"/data-engine/workspaces"``.
    use_data_services:
        When ``True`` use ``config["data_services_base_url"]``;
        when ``False`` use ``config["base_url"]``.

    Raises
    ------
    AideConfigError
        If the required base-URL key is absent from the config.
    """
    if use_data_services:
        base = config.get("data_services_base_url")
        if not base:
            raise AideConfigError(
                "Operation requires 'data_services_base_url' but it is not "
                "present in the configuration.  Ensure 'data_services_base_url' "
                "or 'rag_search_api_endpoint_url' is set in ~/.netapp."
            )
    else:
        base = config.get("base_url")
        if not base:
            raise AideConfigError(
                "Operation requires 'base_url' but it is not present in the "
                "configuration.  Set 'base_url' in ~/.netapp."
            )

    parsed = urllib.parse.urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    base_path = parsed.path.rstrip("/")

    # If the path already includes the API root prefix (e.g. _links.next.href
    # returns "/api/data-engine/..." when base_url is "https://host/api"),
    # join with the origin only to avoid double-pathing.
    if base_path and (path.startswith(base_path + "/") or path == base_path):
        return f"{origin}{path}"

    return base.rstrip("/") + "/" + path.lstrip("/")


def _parse_error(response_json: dict) -> AideApiError | None:
    """Return an :class:`AideApiError` if *response_json* contains an error key.

    AIDE / ONTAP REST APIs embed errors in one of two shapes:

    .. code-block:: json

        {"error": {"code": "4", "message": "...", "target": "..."}}

    or the top-level dict itself is the error object:

    .. code-block:: json

        {"code": "4", "message": "..."}
    """
    err = response_json.get("error")
    if err is None:
        return None

    if isinstance(err, dict):
        code = str(err.get("code", "unknown"))
        message = err.get("message", "Unknown API error")
        target = err.get("target")
    else:
        # The "error" value is a plain string (some older endpoints).
        code = "unknown"
        message = str(err)
        target = None

    return AideApiError(code=code, message=message, target=target)


def _extract_async_job(response_json: dict) -> dict | None:
    """Return a normalised job dict if *response_json* represents an async job.

    The API signals an in-progress job via a ``job`` key:

    .. code-block:: json

        {
          "job": {
            "uuid": "abc-123",
            "state": "queued",
            "_links": {"self": {"href": "/api/cluster/jobs/abc-123"}}
          }
        }
    """
    job = response_json.get("job")
    if not job:
        return None
    return {
        "job": {
            "uuid": job.get("uuid"),
            "state": job.get("state", "queued"),
            "_links": job.get("_links", {}),
        }
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def aide_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    timeout: int = 30,
    use_data_services: bool = False,
    full_url: str | None = None,
) -> dict:
    """Execute a single authenticated HTTP request against the AIDE REST API.

    Parameters
    ----------
    method:
        HTTP verb — ``"GET"``, ``"POST"``, ``"PATCH"``, or ``"DELETE"``.
    path:
        Relative API path, e.g. ``"/data-engine/workspaces"``.
    params:
        Optional query-string parameters (``dict``).
    body:
        Optional JSON request body (``dict``).
    timeout:
        Request timeout in seconds (default ``30``).
    use_data_services:
        When ``True``, the request is sent to ``config["data_services_base_url"]``
        instead of ``config["base_url"]``.  Ignored when *full_url* is set.
    full_url:
        When set, this URL is used verbatim — ``_build_url`` is bypassed
        entirely.  Used by the search tool to pass
        ``config["rag_search_api_endpoint_url"]`` directly.

    Returns
    -------
    dict
        Parsed JSON response body.  If the server returned HTTP 202 the
        return value is a normalised job dict
        ``{"job": {"uuid": ..., "state": ..., "_links": {...}}}``.
        DELETE with an empty body returns ``{"status": "deleted"}``.
        PATCH with an empty body returns ``{"status": "updated"}``.

    Raises
    ------
    AideConfigError
        If the required base URL is absent from the configuration.
    AideApiError
        If the API response contains an ``"error"`` key.
    httpx.HTTPStatusError
        For non-2xx responses whose body is not a JSON error object.
    """
    config = load_credentials()

    if full_url is not None:
        url = full_url
    else:
        url = _build_url(config, path, use_data_services=use_data_services)

    token = await get_access_token(config)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    verify_ssl: bool | str = config.get("verify_ssl", True)

    logger.debug("%s %s  params=%s", method.upper(), url, params)

    async with httpx.AsyncClient(verify=verify_ssl, timeout=timeout) as client:
        response = await client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=body,
            headers=headers,
        )

    logger.debug("Response: HTTP %s", response.status_code)

    # --- 401: clear cached token so the next call can retry -----------------
    if response.status_code == 401:
        clear_token_cache()
        logger.warning("Received HTTP 401 — OAuth2 token cache cleared.")

    # --- parse body ---------------------------------------------------------
    try:
        response_json: dict = response.json()
    except Exception:
        response.raise_for_status()
        if method.upper() == "DELETE":
            return {"status": "deleted"}
        if method.upper() == "PATCH":
            return {"status": "updated"}
        return {}

    # --- API-level error ----------------------------------------------------
    api_error = _parse_error(response_json)
    if api_error:
        raise api_error

    # --- Async job (HTTP 202) -----------------------------------------------
    if response.status_code == 202:
        job = _extract_async_job(response_json)
        if job:
            return job
        # 202 without a job body — return the raw dict as-is.
        return response_json

    # --- Generic HTTP errors (non-2xx, non-202) not caught above ------------
    if response.status_code >= 400:
        response.raise_for_status()

    return response_json


async def aide_request_all_pages(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    timeout: int = 30,
    use_data_services: bool = False,
    records_key: str = "records",
) -> list[dict]:
    """Fetch every page of a paginated AIDE REST collection.

    Follows ``_links.next.href`` until no further pages are returned, then
    returns a flat list of all ``records`` entries across all pages.

    Parameters
    ----------
    method, path, params, body, timeout, use_data_services:
        Forwarded to :func:`aide_request` for the first (and each subsequent)
        request.
    records_key:
        The key inside each page response that holds the list of items
        (default ``"records"``).

    Returns
    -------
    list[dict]
        Aggregated list of all record dicts across all pages.

    Raises
    ------
    AideConfigError, AideApiError, httpx.HTTPStatusError:
        Propagated from :func:`aide_request`.
    """
    all_records: list[dict] = []
    next_href: str | None = path
    current_params = dict(params) if params else {}

    while next_href is not None:
        page = await aide_request(
            method,
            next_href,
            params=current_params,
            body=body,
            timeout=timeout,
            use_data_services=use_data_services,
        )

        records = page.get(records_key)
        if isinstance(records, list):
            all_records.extend(records)

        # Cursor / next-page link
        links = page.get("_links", {})
        next_link = links.get("next", {})
        next_href = next_link.get("href") if isinstance(next_link, dict) else None

        # On subsequent pages the path comes from _links.next.href which is
        # already fully qualified relative to the API root, so clear params
        # to avoid duplicating cursor tokens.
        current_params = {}

    return all_records


async def aide_paginated_stream(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    timeout: int = 30,
    use_data_services: bool = False,
    records_key: str = "records",
) -> AsyncIterator[dict]:
    """Async generator that yields individual records page-by-page.

    Unlike :func:`aide_request_all_pages` this does not accumulate all pages
    in memory — useful when iterating over very large collections.

    Yields
    ------
    dict
        Individual record dicts.
    """
    next_href: str | None = path
    current_params = dict(params) if params else {}

    while next_href is not None:
        page = await aide_request(
            method,
            next_href,
            params=current_params,
            body=body,
            timeout=timeout,
            use_data_services=use_data_services,
        )

        records = page.get(records_key)
        if isinstance(records, list):
            for record in records:
                yield record

        links = page.get("_links", {})
        next_link = links.get("next", {})
        next_href = next_link.get("href") if isinstance(next_link, dict) else None
        current_params = {}
