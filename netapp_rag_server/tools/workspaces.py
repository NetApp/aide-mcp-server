# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for workspace lifecycle: list, get, create, update, and delete."""

from __future__ import annotations

import json
import re
from typing import Optional

from ..client import AideApiError, AideConfigError, aide_request

# Compiled UUID pattern reused for early input validation on write operations.
# Matches the same pattern used in tools/data_sources.py for consistency.
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

# ONTAP's `return_timeout` query parameter is bounded to this inclusive range.
_RETURN_TIMEOUT_MIN = 0
_RETURN_TIMEOUT_MAX = 120


def _is_valid_return_timeout(value: int) -> bool:
    """Return True when *value* is a non-bool int within the API's accepted
    return_timeout range. ``bool`` is rejected explicitly because ``bool`` is a
    subclass of ``int`` in Python and we don't want ``True``/``False`` to be
    accepted as 1/0.
    """
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and _RETURN_TIMEOUT_MIN <= value <= _RETURN_TIMEOUT_MAX
    )


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


async def aide_workspace_create(
    name: str,
    data_sources: list[dict],
    description: Optional[str] = None,
    policies: Optional[list[dict]] = None,
    refresh_interval: Optional[str] = None,
    return_timeout: int = 0,
) -> str:
    """
    Create a new AIDE workspace. Requires a `name` and at least one entry in
    `data_sources` specifying the storage volume or bucket to scan. Returns an
    async job UUID — use `aide_job_get` or `aide_poll_job_until_complete` to
    track progress. Optionally set `description`, `policies` to attach
    governance rules, and `refresh_interval` (ISO-8601 duration like "PT1H")
    to control automatic refresh frequency.

    Args:
        name (str):
            Required. Name for the new workspace.
        data_sources (list[dict]):
            Required. Non-empty list of data sources to attach.

            **Each entry MUST include BOTH the ONTAP volume/bucket UUID
            and the SVM UUID.** The workspace-create endpoint does not
            accept by-name lookup; it identifies the storage object by
            UUID.

            If only volume + SVM names are known, **first call**
            `aide_data_sources_list` **yourself** with
            `local_storage_name=<volume>`,
            `local_storage_svm_name=<svm>`, and
            `fields="uuid,type,local_storage"`. Then immediately call
            this tool with the UUIDs from `records[0]`. **Do not** ask
            the user for UUIDs, narrate the steps, or print code
            snippets — chain the tool calls and report only the final
            result. From `records[0]`, extract:

              - `local_storage.uuid` → use as `data_source.uuid` here.
                **This is the ONTAP volume/bucket UUID.** Do NOT use
                `records[0].uuid` — that is the AIDE record UUID and
                will not work here.
              - `local_storage.svm.uuid` → use as `data_source.svm.uuid`.

            Per-entry fields:

              - `type` (str, required): `"volume"` or `"bucket"`.
              - `uuid` (str, required): ONTAP volume/bucket UUID (from
                `records[].local_storage.uuid` in the list response).
              - `svm` (dict, required): Must contain `uuid` (the SVM
                UUID, from `records[].local_storage.svm.uuid`). `name`
                is optional context.
              - `name` (str, optional): Volume/bucket name — context only.
              - `cluster`, `is_remote`, `peer_svm`: Optional. For
                cross-cluster sources only.

            Each entry is wrapped in `{"data_source": ...}` internally
            before being sent to the API.
        description (Optional[str]):
            Human-readable description for the workspace.
        policies (Optional[list[dict]]):
            Policies to attach. Each dict must include either `uuid` or `name`,
            e.g. `[{"name": "Default Policy"}]`.
        refresh_interval (Optional[str]):
            ISO-8601 duration controlling automatic refresh frequency, e.g.
            `"PT1H"` (1 hour) or `"PT30M"` (30 minutes).
        return_timeout (int):
            Optional. Seconds to wait for the async job to complete before
            returning (0–120, default 0 = return immediately with job UUID).

    Returns:
        str: JSON string. Typically HTTP 202 async job with:
            - `job.uuid` (str): UUID of the async job to track progress.
            - `job.state` (str): Initial job state, typically `"queued"`.
            - `job._links` (dict): Links to poll job status.

        If `return_timeout` > 0 and the job finishes within that window, returns
        the created workspace object (HTTP 201).

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Validation errors are returned for: empty `name`; empty `data_sources`;
        any entry that is not a dict; any entry whose `type` is not `"volume"`
        or `"bucket"`; any entry missing `uuid` or whose `uuid` is not a valid
        UUID; any entry whose `svm` is not a dict containing a valid `uuid`;
        `policies` entries without `uuid` or `name`; empty `refresh_interval`;
        out-of-range `return_timeout`.

    """
    if not isinstance(name, str) or not name.strip():
        return 'Error: name must be a non-empty string'

    if not isinstance(data_sources, list) or len(data_sources) == 0:
        return 'Error: data_sources must be a non-empty list'

    for idx, entry in enumerate(data_sources):
        if not isinstance(entry, dict):
            return (
                f'Error: data_sources[{idx}] must be a dict, e.g. '
                f'{{"type": "volume", "uuid": "<ds-uuid>", '
                f'"svm": {{"uuid": "<svm-uuid>"}}}}'
            )
        ds_type = entry.get("type")
        if ds_type not in ("volume", "bucket"):
            return (
                f'Error: data_sources[{idx}]["type"] must be '
                f'"volume" or "bucket", got "{ds_type}"'
            )
        ds_uuid = entry.get("uuid")
        if not isinstance(ds_uuid, str) or not _UUID_RE.match(ds_uuid):
            return (
                f'Error: data_sources[{idx}]["uuid"] is required and must be '
                f'a valid UUID — the ONTAP volume/bucket UUID. Use '
                f'aide_data_sources_list with local_storage_name=<volume> '
                f'and fields="uuid,type,local_storage", then take '
                f'records[0].local_storage.uuid (NOT records[0].uuid, which '
                f'is the AIDE record UUID).'
            )
        svm = entry.get("svm")
        if not isinstance(svm, dict):
            return (
                f'Error: data_sources[{idx}]["svm"] is required and must be '
                f'a dict containing the SVM UUID, e.g. '
                f'{{"uuid": "<svm-uuid>"}}'
            )
        svm_uuid = svm.get("uuid")
        if not isinstance(svm_uuid, str) or not _UUID_RE.match(svm_uuid):
            return (
                f'Error: data_sources[{idx}]["svm"]["uuid"] is required and '
                f'must be a valid UUID — the SVM UUID. Find it via '
                f'aide_data_sources_list with '
                f'fields="uuid,type,local_storage" (returned as '
                f'records[].local_storage.svm.uuid).'
            )

    if policies is not None:
        if not isinstance(policies, list):
            return 'Error: policies must be a list of dicts'
        for idx, pol in enumerate(policies):
            if not isinstance(pol, dict):
                return f'Error: policies[{idx}] must be a dict'
            if "uuid" not in pol and "name" not in pol:
                return (
                    f'Error: policies[{idx}] must include either '
                    f'"uuid" or "name"'
                )

    if refresh_interval is not None:
        if not isinstance(refresh_interval, str) or not refresh_interval.strip():
            return 'Error: refresh_interval must be a non-empty ISO-8601 duration string, e.g. "PT1H"'

    if not _is_valid_return_timeout(return_timeout):
        return (
            f'Error: return_timeout must be an integer between '
            f'{_RETURN_TIMEOUT_MIN} and {_RETURN_TIMEOUT_MAX}'
        )

    # Wrap each flat entry in the "data_source" envelope the API requires.
    wrapped_data_sources = [{"data_source": entry} for entry in data_sources]

    body: dict = {"name": name, "data_sources": wrapped_data_sources}
    if description is not None:
        body["description"] = description
    if policies is not None:
        body["policies"] = policies
    if refresh_interval is not None:
        body["refresh_interval"] = refresh_interval

    params: dict[str, int] = {"return_timeout": return_timeout}

    try:
        data = await aide_request(
            "POST",
            "/data-engine/workspaces",
            params=params,
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


async def aide_workspace_update(
    uuid: str,
    description: Optional[str] = None,
    policies: Optional[list[dict]] = None,
    refresh_interval: Optional[str] = None,
    return_timeout: int = 0,
) -> str:
    """
    Update an existing AIDE workspace. You can modify the `description`,
    `refresh_interval`, or `policies`. Only provide the fields you want to
    change — omitted fields are left unchanged (PATCH semantics). May return
    an async job UUID if the update triggers reprocessing.

    Args:
        uuid (str):
            Required. UUID of the workspace to update.
        description (Optional[str]):
            New description for the workspace.
        policies (Optional[list[dict]]):
            Replacement policy list (this replaces the existing list — it is
            not a merge). Each dict must include either `uuid` or `name`.
        refresh_interval (Optional[str]):
            New refresh interval as an ISO-8601 duration, e.g. `"PT2H"`. Takes
            effect on the next refresh cycle.
        return_timeout (int):
            Optional. Seconds to wait for the async job to complete before
            returning (0–120, default 0 = return immediately).

    Returns:
        str: JSON string. HTTP 200 synchronous update with:
            - `status` (str): Set to `"updated"` on success.

        HTTP 202 async job with:
            - `job.uuid` (str): UUID of the async job to track progress.
            - `job.state` (str): Initial job state, typically `"queued"`.
            - `job._links` (dict): Links to poll job status.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Returns ``'Error: invalid UUID format: "..."'`` immediately if `uuid`
        is not a valid UUID. Returns ``'Error: at least one of description,
        policies, or refresh_interval must be provided'`` when no update fields
        are given (a PATCH with an empty body is a no-op). Returns validation
        errors for malformed `policies` entries, empty `refresh_interval`, or
        out-of-range `return_timeout`.

    """
    if not _UUID_RE.match(uuid):
        return f'Error: invalid UUID format: "{uuid}"'

    if description is None and policies is None and refresh_interval is None:
        return (
            'Error: at least one of description, policies, or '
            'refresh_interval must be provided'
        )

    if policies is not None:
        if not isinstance(policies, list):
            return 'Error: policies must be a list of dicts'
        for idx, pol in enumerate(policies):
            if not isinstance(pol, dict):
                return f'Error: policies[{idx}] must be a dict'
            if "uuid" not in pol and "name" not in pol:
                return (
                    f'Error: policies[{idx}] must include either '
                    f'"uuid" or "name"'
                )

    if refresh_interval is not None:
        if not isinstance(refresh_interval, str) or not refresh_interval.strip():
            return 'Error: refresh_interval must be a non-empty ISO-8601 duration string, e.g. "PT1H"'

    if not _is_valid_return_timeout(return_timeout):
        return (
            f'Error: return_timeout must be an integer between '
            f'{_RETURN_TIMEOUT_MIN} and {_RETURN_TIMEOUT_MAX}'
        )

    body: dict = {}
    if description is not None:
        body["description"] = description
    if policies is not None:
        body["policies"] = policies
    if refresh_interval is not None:
        body["refresh_interval"] = refresh_interval

    params: dict[str, int] = {"return_timeout": return_timeout}

    try:
        data = await aide_request(
            "PATCH",
            f"/data-engine/workspaces/{uuid}",
            params=params,
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


async def aide_workspace_delete(
    uuid: str,
    delete_data_collections: bool = False,
    return_timeout: int = 0,
) -> str:
    """
    Delete an AIDE workspace. By default this fails if the workspace has data
    collections — set `delete_data_collections=True` to cascade-delete them.
    Returns an async job UUID for tracking, or a synchronous deletion status.

    Args:
        uuid (str):
            Required. UUID of the workspace to delete.
        delete_data_collections (bool):
            Optional. If `True`, cascade-deletes all data collections in the
            workspace. If `False` (default), the request fails when the
            workspace has any data collections.
        return_timeout (int):
            Optional. Seconds to wait for the async job to complete before
            returning (0–120, default 0 = return immediately).

    Returns:
        str: JSON string. HTTP 200 synchronous deletion with:
            - `status` (str): Set to `"deleted"` on success.

        HTTP 202 async job with:
            - `job.uuid` (str): UUID of the async job to track progress.
            - `job.state` (str): Initial job state, typically `"queued"`.
            - `job._links` (dict): Links to poll job status.

        On error, returns a string beginning with `"API Error"` or `"Error:"`.
        Returns ``'Error: invalid UUID format: "..."'`` immediately if `uuid`
        is not a valid UUID. Returns
        ``'Error: delete_data_collections must be a bool'`` if the flag has
        the wrong type. Returns
        ``'Error: return_timeout must be an integer between 0 and 120'`` for
        an out-of-range `return_timeout`.

    """
    if not _UUID_RE.match(uuid):
        return f'Error: invalid UUID format: "{uuid}"'

    if not isinstance(delete_data_collections, bool):
        return 'Error: delete_data_collections must be a bool'

    if not _is_valid_return_timeout(return_timeout):
        return (
            f'Error: return_timeout must be an integer between '
            f'{_RETURN_TIMEOUT_MIN} and {_RETURN_TIMEOUT_MAX}'
        )

    # ONTAP expects lowercase "true"/"false" for boolean query params.
    params: dict[str, str | int] = {
        "delete_data_collections": "true" if delete_data_collections else "false",
        "return_timeout": return_timeout,
    }

    try:
        data = await aide_request(
            "DELETE",
            f"/data-engine/workspaces/{uuid}",
            params=params,
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
