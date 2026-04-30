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
import re
from typing import Optional

from ..client import AideApiError, AideConfigError, aide_request

# Compiled UUID pattern reused across all tools for early input validation.
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Tool #6 — aide_data_sources_list
# ---------------------------------------------------------------------------

async def aide_data_sources_list(
    ds_type: Optional[str] = None,
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
        ds_type (str):
            Optional. Filter by data source type — `"volume"` or `"bucket"`.
        state (str):
            Optional. Filter by lifecycle state — `"processing"`, `"ready"`,
            `"failed"`, `"outdated"`, or `"deleted"`.
        local_storage_name (str):
            Optional. Filter by local storage name
            (maps to API param `local_storage.name`).
        local_storage_svm_name (str):
            Optional. Filter by SVM name
            (maps to `local_storage.svm.name`).
        remote_storage_name (str):
            Optional. Filter by remote storage name
            (maps to `remote_storage.name`).
        remote_storage_cluster_name (str):
            Optional. Filter by remote cluster name
            (maps to `remote_storage.cluster.name`).
        max_records (int):
            Optional. Maximum number of records to return (≥ 1).
        return_timeout (int):
            Optional. Seconds to wait for results (0–120, default 15).
        fields (str):
            Optional. Comma-separated list of fields to include in the response.
        order_by (str):
            Optional. Sort order, e.g. `"name asc,create_time desc"`.

    Returns:
        str: JSON string with the following fields:
            - `num_records` (int): Number of records returned in this page.
            - `total_records` (int): Total number of matching records.
            - `records` (list): List of data source objects. By default, each
              record contains only `uuid`. Use the `fields` parameter to request
              additional fields:
                - `uuid` (str): Unique identifier of the data source.
                - `workspaces` (list): Workspaces this data source belongs to, each with `uuid` and `name`.
                - `type` (str): Data source type — `"volume"` or `"bucket"`.
                - `space` (dict): Space usage with `total`, `used`, and `available` in bytes.
                - `message` (str): Human-readable status message.
                - `last_refresh_time` (str): ISO 8601 timestamp of the last scan.
                - `state` (str): Lifecycle state — `"processing"`, `"ready"`, `"failed"`, `"outdated"`, or `"deleted"`.
                - `local_storage` (dict): Local storage info with `uuid`, `name`, and `svm` (`uuid`, `name`).
                - `remote_storage` (dict): Remote storage info, if applicable. Omitted when not set.
                - `errors` (list): Any errors associated with the data source. Omitted when empty.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.

    """
    # ONTAP uses dotted path notation for nested filter params
    candidate_params: list[tuple[str, object | None]] = [
        ("type", ds_type),
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
        # Guard for future bool params (none currently, but kept for consistency)
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

    Returns type, state, local/remote storage info, space usage and errors.

    Args:
        uuid (str):
            Required. Unique identifier of the data source.
        fields (str):
            Optional. Comma-separated list of fields to include in the response.

    Returns:
        str: JSON string with a single data source object containing:
            - `uuid` (str): Unique identifier of the data source.
            - `workspaces` (list): Workspaces this data source belongs to, each with `uuid` and `name`.
            - `type` (str): Data source type — `"volume"` or `"bucket"`.
            - `space` (dict): Space usage with `total`, `used`, and `available` in bytes.
            - `message` (str): Human-readable status message.
            - `last_refresh_time` (str): ISO 8601 timestamp of the last scan.
            - `state` (str): Lifecycle state — `"processing"`, `"ready"`, `"failed"`, `"outdated"`, or `"deleted"`.
            - `local_storage` (dict): Local storage info with `uuid`, `name`, and `svm` (`uuid`, `name`).
            - `remote_storage` (dict): Remote storage info, if applicable. Omitted when not set.
            - `errors` (list): Any errors associated with the data source. Omitted when empty.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Returns ``'Error: invalid UUID format: "..."'`` immediately if `uuid`
        is not a valid UUID (e.g. ``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx``).
        HTTP 404 / error code `4` indicates the data source does not exist.

    """
    if not _UUID_RE.match(uuid):
        return f'Error: invalid UUID format: "{uuid}"'

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
    ds_type: Optional[str] = None,
    state: Optional[str] = None,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """
    List data sources within a specific workspace.

    Use this when you need to see what storage volumes or buckets a workspace
    is scanning. Same response shape as `aide_data_sources_list` but scoped
    to one workspace.

    Args:
        workspace_uuid (str):
            Required. UUID of the workspace containing the data sources.
        ds_type (str):
            Optional. Filter by data source type — `"volume"` or `"bucket"`.
        state (str):
            Optional. Filter by lifecycle state — `"processing"`, `"ready"`,
            `"failed"`, `"outdated"`, or `"deleted"`.
        max_records (int):
            Optional. Maximum number of records to return (≥ 1).
        return_timeout (int):
            Optional. Seconds to wait for results (0–120, default 15).
        fields (str):
            Optional. Comma-separated list of fields to include in the response.
        order_by (str):
            Optional. Sort order, e.g. `"name asc,create_time desc"`.

    Returns:
        str: JSON string with the following fields:
            - `num_records` (int): Number of records returned in this page.
            - `total_records` (int): Total number of matching records.
            - `records` (list): List of data source objects. By default, each
              record contains only `uuid`. Use the `fields` parameter to request
              additional fields:
                - `workspace` (dict): The parent workspace, containing `uuid`.
                - `uuid` (str): Unique identifier of the data source.
                - `type` (str): Data source type — `"volume"` or `"bucket"`.
                - `space` (dict): Space usage with `total`, `used`, and `available` in bytes.
                - `message` (str): Human-readable status message.
                - `last_refresh_time` (str): ISO 8601 timestamp of the last scan.
                - `state` (str): Lifecycle state — `"processing"`, `"ready"`, `"failed"`, `"outdated"`, or `"deleted"`.
                - `local_storage` (dict): Local storage info with `uuid`, `name`, and `svm` (`uuid`, `name`).
                - `remote_storage` (dict): Remote storage info, if applicable. Omitted when not set.
                - `errors` (list): Any errors associated with the data source. Omitted when empty.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Returns ``'Error: invalid UUID format: "..."'`` immediately if
        `workspace_uuid` is not a valid UUID.

    """
    if not _UUID_RE.match(workspace_uuid):
        return f'Error: invalid UUID format: "{workspace_uuid}"'

    candidate_params: list[tuple[str, object | None]] = [
        ("type", ds_type),
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
        # Guard for future bool params (none currently, but kept for consistency)
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

    Returns the same detail as `aide_data_source_get` but scoped to the
    workspace context.

    Args:
        workspace_uuid (str):
            Required. UUID of the parent workspace.
        uuid (str):
            Required. UUID of the data source to retrieve.
        fields (str):
            Optional. Comma-separated list of fields to include in the response.

    Returns:
        str: JSON string with a single data source object containing:
            - `workspace` (dict): The parent workspace, containing `uuid`.
            - `uuid` (str): Unique identifier of the data source.
            - `type` (str): Data source type — `"volume"` or `"bucket"`.
            - `space` (dict): Space usage with `total`, `used`, and `available` in bytes.
            - `message` (str): Human-readable status message.
            - `last_refresh_time` (str): ISO 8601 timestamp of the last scan.
            - `state` (str): Lifecycle state — `"processing"`, `"ready"`, `"failed"`, `"outdated"`, or `"deleted"`.
            - `local_storage` (dict): Local storage info with `uuid`, `name`, and `svm` (`uuid`, `name`).
            - `remote_storage` (dict): Remote storage info, if applicable. Omitted when not set.
            - `errors` (list): Any errors associated with the data source. Omitted when empty.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Returns ``'Error: invalid UUID format: "..."'`` immediately if
        `workspace_uuid` or `uuid` is not a valid UUID.
        HTTP 404 / error code `4` indicates the data source does not exist.

    """
    if not _UUID_RE.match(workspace_uuid):
        return f'Error: invalid UUID format: "{workspace_uuid}"'
    if not _UUID_RE.match(uuid):
        return f'Error: invalid UUID format: "{uuid}"'

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
    ds_type: str,
    local_storage: dict,
    remote_storage: Optional[dict] = None,
    return_timeout: int = 0,
) -> str:
    """
    Add a data source (storage volume or bucket) to a workspace.

    The workspace will begin scanning this data source for entities. Requires
    `type` ("volume" or "bucket") and `local_storage` with the volume/
    bucket name and SVM. Returns an async job UUID. For cross-cluster data
    sources, also provide `remote_storage`.

    Args:
        workspace_uuid (str):
            Required. UUID of the workspace to add the data source to.
        ds_type (str):
            Required. Data source type — `"volume"` or `"bucket"`.
        local_storage (dict):
            Required. Local storage configuration. For volumes:
            `{"name": "vol1", "svm": {"name": "svm1"}}`. For remote
            data sources, only SVM details are required.
        remote_storage (dict):
            Optional. Remote storage configuration for cross-cluster sources:
            `{"name": "...", "cluster": {"name": "..."}, "svm": {"name": "..."}}`.
        return_timeout (int):
            Optional. Seconds to wait for the async job to complete
            before returning (0–120, default 0 = return immediately with job UUID).

    Returns:
        str: JSON string. Typically HTTP 202 async job with:
            - `job.uuid` (str): UUID of the async job to track progress.
            - `job.state` (str): Initial job state, typically `"queued"`.
            - `job._links` (dict): Links to poll job status.

        If `return_timeout` > 0 and the job finishes within that window,
        returns the created data source object (HTTP 201) with:
            - `uuid` (str): UUID of the newly created data source.
            - `type` (str): Data source type — `"volume"` or `"bucket"`.
            - `state` (str): Initial state, typically `"processing"`.
            - `local_storage` (dict): Local storage info with `name` and `svm.name`.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Returns ``'Error: invalid UUID format: "..."'`` immediately if
        `workspace_uuid` is not a valid UUID. Returns ``'Error: ds_type must
        be "volume" or "bucket"'`` for an invalid type. Returns
        ``'Error: local_storage must be a dict with at least a "name" key'``
        for a malformed local_storage argument.

    """
    if not _UUID_RE.match(workspace_uuid):
        return f'Error: invalid UUID format: "{workspace_uuid}"'

    if ds_type not in ("volume", "bucket"):
        return f'Error: ds_type must be "volume" or "bucket", got "{ds_type}"'

    if not isinstance(local_storage, dict) or "name" not in local_storage:
        return 'Error: local_storage must be a dict with at least a "name" key, e.g. {"name": "vol1", "svm": {"name": "svm1"}}'

    body: dict = {"type": ds_type, "local_storage": local_storage}
    if remote_storage is not None:
        body["remote_storage"] = remote_storage

    params: dict[str, int] = {"return_timeout": return_timeout}

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
        workspace_uuid (str):
            Required. UUID of the parent workspace.
        uuid (str):
            Required. UUID of the data source to remove.

    Returns:
        str: JSON string. HTTP 200 synchronous deletion with:
            - `status` (str): Set to `"deleted"` on success.

        HTTP 202 async job with:
            - `job.uuid` (str): UUID of the async job to track progress.
            - `job.state` (str): Initial job state, typically `"queued"`.
            - `job._links` (dict): Links to poll job status.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Returns ``'Error: invalid UUID format: "..."'`` immediately if
        `workspace_uuid` or `uuid` is not a valid UUID.

    """
    if not _UUID_RE.match(workspace_uuid):
        return f'Error: invalid UUID format: "{workspace_uuid}"'
    if not _UUID_RE.match(uuid):
        return f'Error: invalid UUID format: "{uuid}"'

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
