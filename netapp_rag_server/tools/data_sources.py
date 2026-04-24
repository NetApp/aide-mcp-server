# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for data sources: cluster-wide and per-workspace storage (e.g. volumes, buckets).

Tools implemented here
----------------------
#6  aide_data_sources_list               — GET  /data-engine/data-sources
#7  aide_data_source_get                 — GET  /data-engine/data-sources/{uuid}
#8  aide_workspace_data_sources_list     — GET  /data-engine/workspaces/{workspace_uuid}/data-sources
#9  aide_workspace_data_source_get       — GET  /data-engine/workspaces/{workspace_uuid}/data-sources/{uuid}
#10 aide_workspace_data_source_create    — POST /data-engine/workspaces/{workspace_uuid}/data-sources
#11 aide_workspace_data_source_delete    — DELETE /data-engine/workspaces/{workspace_uuid}/data-sources/{uuid}
"""

from __future__ import annotations

import json
from typing import Optional

from ..client import AideApiError, AideConfigError, aide_request


# ---------------------------------------------------------------------------
# Tool #6 — aide_data_sources_list
# ---------------------------------------------------------------------------

async def aide_data_sources_list(
    type: Optional[str] = None,
    state: Optional[str] = None,
    local_storage_name: Optional[str] = None,
    local_storage_svm_name: Optional[str] = None,
    remote_storage_name: Optional[str] = None,
    remote_storage_cluster_name: Optional[str] = None,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """
    List all data sources across the ONTAP cluster.

    Data sources are the storage volumes and buckets that AIDE scans. Use
    filters to find data sources by type (volume/bucket), state, or storage
    name. Returns storage details, space usage, associated workspaces, and
    current state.

    Args:
        type (Optional[str]): Filter by data source type — ``"volume"`` or ``"bucket"``.
        state (Optional[str]): Filter by lifecycle state — ``"processing"``, ``"ready"``,
            ``"failed"``, ``"outdated"``, or ``"deleted"``.
        local_storage_name (Optional[str]): Filter by local storage name
            (maps to API param ``local_storage.name``).
        local_storage_svm_name (Optional[str]): Filter by SVM name
            (maps to ``local_storage.svm.name``).
        remote_storage_name (Optional[str]): Filter by remote storage name
            (maps to ``remote_storage.name``).
        remote_storage_cluster_name (Optional[str]): Filter by remote cluster name
            (maps to ``remote_storage.cluster.name``).
        max_records (Optional[int]): Maximum number of records to return (≥ 1).
        return_timeout (Optional[int]): Seconds to wait for results (0–120, default 15).
        fields (Optional[str]): Comma-separated list of fields to include in the response.
        order_by (Optional[str]): Sort order, e.g. ``"name asc,create_time desc"``.

    Returns:
        str: JSON string with ``num_records``, ``total_records``, and ``records[]``.
        Each record includes ``uuid``, ``type``, ``state``, ``local_storage``,
        ``remote_storage``, ``space``, ``last_refresh_time``, ``workspaces``,
        ``errors``, and ``message``.
        On error, returns a string beginning with ``"API Error"`` or ``"Error:"``.

    """
    # ONTAP uses dotted path notation for nested filter params
    candidate_params: list[tuple[str, object | None]] = [
        ("type", type),
        ("state", state),
        ("local_storage.name", local_storage_name),
        ("local_storage.svm.name", local_storage_svm_name),
        ("remote_storage.name", remote_storage_name),
        ("remote_storage.cluster.name", remote_storage_cluster_name),
        ("max_records", max_records),
        ("return_timeout", return_timeout),
        ("fields", fields),
        ("order_by", order_by),
    ]

    params: dict[str, str | int] = {}
    for query_param, value in candidate_params:
        if value is None:
            continue
        if isinstance(value, bool):
            params[query_param] = "true" if value else "false"
        elif isinstance(value, (str, int)):
            params[query_param] = value

    try:
        data = await aide_request(
            "GET",
            "/data-engine/data-sources",
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


# ---------------------------------------------------------------------------
# Tool #7 — aide_data_source_get
# ---------------------------------------------------------------------------

async def aide_data_source_get(
    uuid: str,
    fields: Optional[str] = None,
) -> str:
    """
    Retrieve details of a specific cluster-wide data source by UUID.

    Returns type, state, local/remote storage info, space usage, associated
    workspaces, and errors.

    Args:
        uuid (str): Unique identifier of the data source.
        fields (Optional[str]): Comma-separated list of fields to include in the response.

    Returns:
        str: JSON string with a single data source object containing ``uuid``,
        ``type``, ``state``, ``local_storage``, ``remote_storage``, ``space``,
        ``last_refresh_time``, ``workspaces``, ``errors``, and ``message``.
        On error, returns a string beginning with ``"API Error"`` or ``"Error:"``.
        HTTP 404 / error code ``4`` indicates the data source does not exist.

    """
    params: dict[str, str] = {}
    if fields is not None:
        params["fields"] = fields

    path = f"/data-engine/data-sources/{uuid}"

    try:
        data = await aide_request(
            "GET",
            path,
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


# ---------------------------------------------------------------------------
# Tool #8 — aide_workspace_data_sources_list
# ---------------------------------------------------------------------------

async def aide_workspace_data_sources_list(
    workspace_uuid: str,
    type: Optional[str] = None,
    state: Optional[str] = None,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """
    List data sources within a specific workspace.

    Use this when you need to see what storage volumes or buckets a workspace
    is scanning. Same response shape as ``aide_data_sources_list`` but scoped
    to one workspace.

    Args:
        workspace_uuid (str): UUID of the workspace containing the data sources.
        type (Optional[str]): Filter by data source type — ``"volume"`` or ``"bucket"``.
        state (Optional[str]): Filter by lifecycle state — ``"processing"``, ``"ready"``,
            ``"failed"``, ``"outdated"``, or ``"deleted"``.
        max_records (Optional[int]): Maximum number of records to return (≥ 1).
        return_timeout (Optional[int]): Seconds to wait for results (0–120, default 15).
        fields (Optional[str]): Comma-separated list of fields to include in the response.
        order_by (Optional[str]): Sort order, e.g. ``"name asc,create_time desc"``.

    Returns:
        str: JSON string with ``num_records``, ``total_records``, and ``records[]``.
        Each record has the same shape as ``aide_data_sources_list`` results
        but is scoped to the given workspace.
        On error, returns a string beginning with ``"API Error"`` or ``"Error:"``.

    """
    candidate_params: list[tuple[str, object | None]] = [
        ("type", type),
        ("state", state),
        ("max_records", max_records),
        ("return_timeout", return_timeout),
        ("fields", fields),
        ("order_by", order_by),
    ]

    params: dict[str, str | int] = {}
    for query_param, value in candidate_params:
        if value is None:
            continue
        if isinstance(value, bool):
            params[query_param] = "true" if value else "false"
        elif isinstance(value, (str, int)):
            params[query_param] = value

    path = f"/data-engine/workspaces/{workspace_uuid}/data-sources"

    try:
        data = await aide_request(
            "GET",
            path,
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


# ---------------------------------------------------------------------------
# Tool #9 — aide_workspace_data_source_get
# ---------------------------------------------------------------------------

async def aide_workspace_data_source_get(
    workspace_uuid: str,
    uuid: str,
    fields: Optional[str] = None,
) -> str:
    """
    Retrieve a specific data source within a workspace.

    Returns the same detail as ``aide_data_source_get`` but scoped to the
    workspace context.

    Args:
        workspace_uuid (str): UUID of the parent workspace.
        uuid (str): UUID of the data source to retrieve.
        fields (Optional[str]): Comma-separated list of fields to include in the response.

    Returns:
        str: JSON string with a single data source object (same shape as
        ``aide_data_source_get``) scoped to the workspace.
        On error, returns a string beginning with ``"API Error"`` or ``"Error:"``.
        HTTP 404 / error code ``4`` indicates the data source does not exist.

    """
    params: dict[str, str] = {}
    if fields is not None:
        params["fields"] = fields

    path = f"/data-engine/workspaces/{workspace_uuid}/data-sources/{uuid}"

    try:
        data = await aide_request(
            "GET",
            path,
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


# ---------------------------------------------------------------------------
# Tool #10 — aide_workspace_data_source_create
# ---------------------------------------------------------------------------

async def aide_workspace_data_source_create(
    workspace_uuid: str,
    type: str,
    local_storage: dict,
    remote_storage: Optional[dict] = None,
    return_timeout: Optional[int] = None,
) -> str:
    """
    Add a data source (storage volume or bucket) to a workspace.

    The workspace will begin scanning this data source for entities. Requires
    ``type`` ("volume" or "bucket") and ``local_storage`` with the volume/
    bucket name and SVM. Returns an async job UUID. For cross-cluster data
    sources, also provide ``remote_storage``.

    Args:
        workspace_uuid (str): UUID of the workspace to add the data source to.
        type (str): Data source type — ``"volume"`` or ``"bucket"``.
        local_storage (dict): Local storage configuration. For volumes:
            ``{"name": "vol1", "svm": {"name": "svm1"}}``. For remote
            data sources, only SVM details are required.
        remote_storage (Optional[dict]): Remote storage configuration for
            cross-cluster sources:
            ``{"name": "...", "cluster": {"name": "..."}, "svm": {"name": "..."}}``.
        return_timeout (Optional[int]): Seconds to wait for the async job to complete
            before returning (0–120, default 0 = return immediately with job UUID).

    Returns:
        str: JSON string. Typically HTTP 202 async job:
        ``{"job": {"uuid": "...", "state": "queued", "_links": {...}}}``.
        If ``return_timeout`` > 0 and the job finishes within that window,
        returns the created data source object (HTTP 201).
        On error, returns a string beginning with ``"API Error"`` or ``"Error:"``.

    """
    body: dict = {"type": type, "local_storage": local_storage}
    if remote_storage is not None:
        body["remote_storage"] = remote_storage

    params: dict[str, int] = {}
    if return_timeout is not None:
        params["return_timeout"] = return_timeout

    path = f"/data-engine/workspaces/{workspace_uuid}/data-sources"

    try:
        data = await aide_request(
            "POST",
            path,
            params=params if params else None,
            body=body,
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


# ---------------------------------------------------------------------------
# Tool #11 — aide_workspace_data_source_delete
# ---------------------------------------------------------------------------

async def aide_workspace_data_source_delete(
    workspace_uuid: str,
    uuid: str,
) -> str:
    """
    Remove a data source from a workspace.

    Entities from this data source will be removed from the workspace on the
    next refresh. May return an async job UUID.

    Args:
        workspace_uuid (str): UUID of the parent workspace.
        uuid (str): UUID of the data source to remove.

    Returns:
        str: JSON string. HTTP 200 synchronous deletion: ``{"status": "deleted"}``.
        HTTP 202 async job: ``{"job": {"uuid": "...", "state": "queued", "_links": {...}}}``.
        On error, returns a string beginning with ``"API Error"`` or ``"Error:"``.

    """
    path = f"/data-engine/workspaces/{workspace_uuid}/data-sources/{uuid}"

    try:
        data = await aide_request(
            "DELETE",
            path,
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
