"""
Shared async HTTP client for the NetApp AIDE MCP server.

All HTTP concerns are centralized here so that tool modules focus solely on
parameter mapping and response formatting:

  - URL construction (cluster-management vs. data-services interface)
  - OAuth2 Bearer-token injection
  - SSL / TLS verification
  - Request timeouts
  - ONTAP error-response parsing and exception hierarchy
  - HTTP 202 async-job detection
  - Pagination cursor following
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import AsyncGenerator

import httpx

from .config import load_credentials
from .oauth2 import clear_token_cache, get_access_token

logger = logging.getLogger(__name__)

_cached_config: dict | None = None
_shared_client: httpx.AsyncClient | None = None


def set_config(config: dict) -> None:
    """Seed the module-level config cache.

    Called once from ``main`` at startup so that every subsequent
    ``_get_config()`` call reuses the same validated dict without
    re-reading ``~/.netapp`` from disk.

    If called again with a different config (e.g. in tests) the shared
    ``httpx.AsyncClient`` is invalidated so that the next ``_get_client()``
    call recreates it with the new ``verify_ssl`` setting.
    """
    global _cached_config, _shared_client
    if _cached_config is not config:
        # Discard the old client so _get_client() rebuilds it with the new
        # verify_ssl value.  We do not await aclose() here because set_config
        # is synchronous; the old client will be GC-collected after any
        # in-flight requests complete.
        _shared_client = None
    _cached_config = config


def _get_config() -> dict:
    """Return the validated config, caching the result after the first load."""
    global _cached_config
    if _cached_config is None:
        _cached_config = load_credentials()
    return _cached_config


def _get_client() -> httpx.AsyncClient:
    """Return the shared ``httpx.AsyncClient``, creating it on first use.

    The client is configured with ``verify_ssl`` from the loaded config
    and reuses TCP + TLS connections across requests.
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        config = _get_config()
        verify_ssl: bool | str = config.get("verify_ssl", True)
        _shared_client = httpx.AsyncClient(verify=verify_ssl)
    return _shared_client


async def close_client() -> None:
    """Close the shared HTTP client.  Call once during server shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


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
        code:    The error code string returned by the API (e.g. ``"4"``).
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

    When *use_data_services* is ``True`` the URL is built from
    ``config["data_services_base_url"]`` (data-services LIF); otherwise from
    ``config["base_url"]`` (cluster-management LIF).

    Absolute paths (starting with ``/``) — such as ``_links.next.href``
    values — are resolved against the origin only, so the base path is
    never duplicated.  Relative paths are appended to the full base URL.

    Raises :class:`AideConfigError` if the required key is missing.
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

    if path.startswith("/"):
        return urllib.parse.urljoin(origin, path)

    return base.rstrip("/") + "/" + path.lstrip("/")


def _parse_error(response_json: dict) -> AideApiError | None:
    """Return an :class:`AideApiError` if *response_json* contains an error.

    ONTAP REST APIs embed errors as::

        {"error": {"code": "4", "message": "...", "target": "..."}}

    Some older endpoints use a plain string value for ``"error"``.
    """
    err = response_json.get("error")
    if err is None:
        return None

    if isinstance(err, dict):
        code = str(err.get("code", "unknown"))
        message = err.get("message", "Unknown API error")
        target = err.get("target")
    else:
        code = "unknown"
        message = str(err)
        target = None

    return AideApiError(code=code, message=message, target=target)


def _extract_async_job(response_json: dict) -> dict | None:
    """Return a normalised job dict if the response represents an async job.

    Returns ``None`` when no ``"job"`` key is present.
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
) -> dict:
    """Execute a single authenticated HTTP request against the AIDE REST API.

    Parameters
    ----------
    method:
        HTTP verb — ``"GET"``, ``"POST"``, ``"PATCH"``, or ``"DELETE"``.
    path:
        Relative API path, e.g. ``"/data-engine/workspaces"``.
    params:
        Optional query-string parameters.
    body:
        Optional JSON request body.
    timeout:
        Request timeout in seconds (default ``30``).
    use_data_services:
        When ``True``, the request targets ``config["data_services_base_url"]``
        (data-services LIF) instead of ``config["base_url"]``
        (cluster-management LIF).

    Returns
    -------
    dict
        Parsed JSON response.  Status-code-specific shapes:

        * **200** — parsed JSON body.
        * **201** — parsed JSON body (created resource).
        * **202** — ``{"job": {"uuid": …, "state": …, "_links": {…}}}``.
        * **DELETE with empty body** — ``{"status": "deleted"}``.
        * **PATCH  with empty body** — ``{"status": "updated"}``.

    Raises
    ------
    AideConfigError
        If the required base URL is absent from the configuration.
    AideApiError
        If the API returns an error envelope, the request times out,
        the connection fails, or authentication fails.
    """
    config = _get_config()
    client = _get_client()

    # --- URL -----------------------------------------------------------------
    url = _build_url(config, path, use_data_services=use_data_services)

    response: httpx.Response | None = None

    # Allow a single retry when a 401 indicates the cached token has expired.
    for attempt in range(2):
        # --- OAuth2 token ----------------------------------------------------
        try:
            token = await get_access_token(config)
        except Exception as exc:
            raise AideApiError(
                code="auth_failure",
                message=f"OAuth2 authentication failed: {exc}",
            ) from exc

        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        logger.debug("%s %s  params=%s", method.upper(), url, params)

        # --- HTTP round-trip -------------------------------------------------
        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=body,
                headers=headers,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise AideApiError(
                code="timeout",
                message=f"Request timed out after {timeout}s connecting to {url}",
            ) from exc
        except httpx.ConnectError as exc:
            raise AideApiError(
                code="connection_error",
                message=f"Failed to connect to {url}: {exc}",
            ) from exc

        logger.debug("Response: HTTP %s", response.status_code)

        # --- 401: clear cache and retry once with a fresh token --------------
        if response.status_code == 401 and attempt == 0:
            clear_token_cache()
            logger.warning("Received HTTP 401 — retrying with a fresh token.")
            continue

        break

    # Both iteration paths either raise or assign `response`; this assertion
    # guards against future refactors breaking that invariant.
    assert response is not None, "response was never assigned — retry loop logic changed"

    # --- Parse response body -------------------------------------------------
    try:
        response_json: dict = response.json()
    except Exception as exc:
        if response.status_code >= 400:
            raise AideApiError(
                code=str(response.status_code),
                message=(
                    f"HTTP {response.status_code} with non-JSON body "
                    f"from {url}"
                ),
            )
        if method.upper() == "DELETE":
            return {"status": "deleted"}
        if method.upper() == "PATCH":
            return {"status": "updated"}
        logger.debug("Non-JSON 2xx response: %s", exc)
        return {}

    # --- HTTP 202: async job (checked before error envelope) -----------------
    if response.status_code == 202:
        job = _extract_async_job(response_json)
        if job:
            return job
        return response_json

    # --- API-level error envelope --------------------------------------------
    api_error = _parse_error(response_json)
    if api_error:
        raise api_error

    # --- Non-2xx without an error envelope -----------------------------------
    if response.status_code >= 400:
        raise AideApiError(
            code=str(response.status_code),
            message=f"HTTP {response.status_code} from {url}",
        )

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
    max_pages: int = 1000,
) -> list[dict]:
    """Fetch every page of a paginated AIDE REST collection.

    Follows ``_links.next.href`` until no further pages are returned, then
    returns a flat list of all record entries across all pages.

    Parameters
    ----------
    method, path, params, body, timeout, use_data_services:
        Forwarded to :func:`aide_request` for each page request.
    records_key:
        The key inside each page response that holds the list of items
        (default ``"records"``).
    max_pages:
        Safety limit on the number of pages to fetch (default ``1000``).
        Prevents runaway loops if the API returns circular next links.

    Returns
    -------
    list[dict]
        Aggregated list of all record dicts across all pages.

    Raises
    ------
    AideConfigError, AideApiError:
        Propagated from :func:`aide_request`.
    """
    all_records: list[dict] = []
    next_href: str | None = path
    current_params = dict(params) if params else {}
    current_body: dict | None = body
    pages_fetched = 0

    while next_href is not None:
        if pages_fetched >= max_pages:
            logger.warning(
                "Pagination stopped after %d pages (max_pages=%d).",
                pages_fetched,
                max_pages,
            )
            break

        page = await aide_request(
            method,
            next_href,
            params=current_params,
            body=current_body,
            timeout=timeout,
            use_data_services=use_data_services,
        )
        pages_fetched += 1

        records = page.get(records_key)
        if isinstance(records, list):
            all_records.extend(records)

        links = page.get("_links", {})
        next_link = links.get("next", {})
        next_href = next_link.get("href") if isinstance(next_link, dict) else None

        # Subsequent pages use the fully-qualified href from _links.next,
        # so clear params and body to avoid duplicating cursor tokens or
        # re-sending a POST body on cursor pages.
        current_params = {}
        current_body = None

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
    max_pages: int = 1000,
) -> AsyncGenerator[dict, None]:
    """Async generator that yields individual records page-by-page.

    Unlike :func:`aide_request_all_pages` this does not accumulate all pages
    in memory — useful when iterating over very large collections.

    Parameters
    ----------
    max_pages:
        Safety limit on the number of pages to fetch (default ``1000``).

    Yields
    ------
    dict
        Individual record dicts.
    """
    next_href: str | None = path
    current_params = dict(params) if params else {}
    current_body: dict | None = body
    pages_fetched = 0

    while next_href is not None:
        if pages_fetched >= max_pages:
            logger.warning(
                "Pagination stopped after %d pages (max_pages=%d).",
                pages_fetched,
                max_pages,
            )
            break

        page = await aide_request(
            method,
            next_href,
            params=current_params,
            body=current_body,
            timeout=timeout,
            use_data_services=use_data_services,
        )
        pages_fetched += 1

        records = page.get(records_key)
        if isinstance(records, list):
            for record in records:
                yield record

        links = page.get("_links", {})
        next_link = links.get("next", {})
        next_href = next_link.get("href") if isinstance(next_link, dict) else None
        current_params = {}
        current_body = None
