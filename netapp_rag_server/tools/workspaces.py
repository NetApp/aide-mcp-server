# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for workspace lifecycle: list, get, create, update, and delete."""

from __future__ import annotations

import json
from typing import Optional

from ..client import AideApiError, AideConfigError, aide_request


async def aide_workspaces_list(
    name: Optional[str] = None,
    state: Optional[str] = None,
    owner: Optional[str] = None,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """
    List all AIDE workspaces visible to the caller. Use filter parameters to
    narrow results: `name` for a specific workspace, `state` to find workspaces
    in a particular lifecycle state (processing, ready, failed, outdated), or
    `owner` to find workspaces owned by a specific user. Returns workspace
    summaries including entity counts, space usage, and current state.

    Args:
        name (Optional[str]): Filter by workspace name (exact match or wildcard *).
        state (Optional[str]): Filter by state: processing, ready, failed, outdated.
        owner (Optional[str]): Filter by workspace owner.
        max_records (Optional[int]): Limit number of results (>= 1).
        return_timeout (Optional[int]): Seconds to wait for response (0–120, default 15).
        fields (Optional[str]): CSV list of fields to include in the response.
        order_by (Optional[str]): Sort order, e.g. "name asc,create_time desc".

    Returns:
        str: JSON string with num_records, total_records, and records array.

    """
    params: dict[str, str | int] = {}
    if name is not None:
        params["name"] = name
    if state is not None:
        params["state"] = state
    if owner is not None:
        params["owner"] = owner
    if max_records is not None:
        params["max_records"] = max_records
    if return_timeout is not None:
        params["return_timeout"] = return_timeout
    if fields is not None:
        params["fields"] = fields
    if order_by is not None:
        params["order_by"] = order_by

    try:
        data = await aide_request(
            "GET",
            "/data-engine/workspaces",
            params=params if params else None,
            use_data_services=False,
        )
        return json.dumps(data, indent=2)
    except AideApiError as e:
        if e.code in ("timeout", "connection_error"):
            return f"Error: {e.message}"
        return f"API Error {e.code}: {e.message}"
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


async def aide_workspace_get(
    uuid: str,
    fields: Optional[str] = None,
) -> str:
    """
    Retrieve full details of a specific AIDE workspace by its UUID. Returns the
    workspace's name, state, owner, entity count, data collection count, space
    usage, version info, attached policies, refresh interval, and any errors.
    Use `fields` to request only specific properties (e.g.
    `fields="state,errors,last_refresh_time"` for a quick health check).

    Args:
        uuid (str): Unique identifier of the workspace.
        fields (Optional[str]): CSV list of fields to include in the response.

    Returns:
        str: JSON string with the workspace object.

    """
    params: dict[str, str] = {}
    if fields is not None:
        params["fields"] = fields

    try:
        data = await aide_request(
            "GET",
            f"/data-engine/workspaces/{uuid}",
            params=params if params else None,
            use_data_services=False,
        )
        return json.dumps(data, indent=2)
    except AideApiError as e:
        if e.code in ("timeout", "connection_error"):
            return f"Error: {e.message}"
        return f"API Error {e.code}: {e.message}"
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
