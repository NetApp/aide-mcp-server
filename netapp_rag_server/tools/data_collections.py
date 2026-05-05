# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for data collections within a workspace: create, read, update, delete, and related options."""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..client import AideApiError, AideConfigError, aide_request

logger = logging.getLogger(__name__)

# ONTAP's `return_timeout` query parameter is bounded to this inclusive range.
_RETURN_TIMEOUT_MIN = 0
_RETURN_TIMEOUT_MAX = 120


def _format_api_error(e: AideApiError) -> str:
    """Format an AideApiError for the LLM response.

    Includes ``target`` so HTTP 409 conflicts identify which resource
    (e.g. ``data_collection.name``) triggered the uniqueness violation.
    """
    if e.code in ("timeout", "connection_error"):
        return f"Error: {e.message}"
    base = f"API Error {e.code}: {e.message}"
    if e.target:
        return f"{base} (target: {e.target})"
    return base


async def aide_data_collections_list(
    workspace_uuid: str,
    name: Optional[str] = None,
    type: Optional[str] = None,
    state: Optional[str] = None,
    embedding_enabled: Optional[bool] = None,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """
    List all data collections in a workspace. Data collections are curated
    subsets of workspace entities, optionally with vector embeddings for RAG
    search. Filter by name, type (manual=explicit entity list,
    dynamic=query-driven), state (draft, processing, published, failed,
    outdated), or embedding_enabled to find RAG-ready collections.

    Args:
        workspace_uuid (str): The UUID of the parent workspace.
        name (Optional[str]): Filter by collection name.
        type (Optional[str]): Filter by collection type (`manual` or `dynamic`).
        state (Optional[str]): Filter by lifecycle state (`draft`, `processing`,
            `published`, `failed`, `outdated`).
        embedding_enabled (Optional[bool]): Filter by whether vectorization is
            enabled (maps to API param `embedding.enabled`).
        max_records (Optional[int]): Limit number of records to return.
        return_timeout (Optional[int]): Seconds to wait for the response (0–120).
        fields (Optional[str]): CSV list of fields to include in the response.
        order_by (Optional[str]): Sort order, e.g. `name asc,create_time desc`.

    Returns:
        str: JSON string with `num_records` (count in this page),
        `total_records` (total matching the filter), and `records` (list of
        data collection objects).

    """
    if return_timeout is not None and not (
        _RETURN_TIMEOUT_MIN <= return_timeout <= _RETURN_TIMEOUT_MAX
    ):
        return (
            f"Error: return_timeout must be between {_RETURN_TIMEOUT_MIN} and "
            f"{_RETURN_TIMEOUT_MAX} seconds (got {return_timeout})"
        )

    # embedding_enabled maps to the dotted API param "embedding.enabled"
    candidate_params: list[tuple[str, object | None]] = [
        ("name", name),
        ("type", type),
        ("state", state),
        ("embedding.enabled", embedding_enabled),
        ("max_records", max_records),
        ("return_timeout", return_timeout),
        ("fields", fields),
        ("order_by", order_by),
    ]

    params: dict[str, str | int] = {}
    for query_param, value in candidate_params:
        if value is None:
            continue
        # ONTAP expects lowercase "true"/"false", not Python's "True"/"False".
        if isinstance(value, bool):
            params[query_param] = "true" if value else "false"
        elif isinstance(value, (str, int)):
            params[query_param] = value

    path = f"/data-engine/workspaces/{workspace_uuid}/data-collections"

    try:
        data = await aide_request(
            "GET",
            path,
            params=params if params else None,
            use_data_services=False,
        )
        return json.dumps(data, indent=2)
    except AideApiError as e:
        return _format_api_error(e)
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in aide_data_collections_list")
        return f"Error: {type(e).__name__}: {e}"


async def aide_data_collection_get(
    workspace_uuid: str,
    uuid: str,
    fields: Optional[str] = None,
) -> str:
    """
    Retrieve full details of a specific data collection including its embedding
    configuration, entity count, query expression, RAG URL, version info, and
    current state.
    Use `fields` to request a subset (e.g. `fields="state,errors,message"` for
    a quick status check).

    Args:
        workspace_uuid (str): The UUID of the parent workspace.
        uuid (str): The UUID of the data collection.
        fields (Optional[str]): CSV list of fields to include in the response.

    Returns:
        str: The data collection's details as a JSON string.

    """
    params: dict[str, str] = {}
    if fields is not None:
        params["fields"] = fields

    path = f"/data-engine/workspaces/{workspace_uuid}/data-collections/{uuid}"

    try:
        data = await aide_request(
            "GET",
            path,
            params=params if params else None,
            use_data_services=False,
        )
        return json.dumps(data, indent=2)
    except AideApiError as e:
        return _format_api_error(e)
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in aide_data_collection_get")
        return f"Error: {type(e).__name__}: {e}"


async def aide_data_collection_create(
    workspace_uuid: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    type: Optional[str] = None,
    query: Optional[dict] = None,
    entities: Optional[list[dict]] = None,
    embedding: Optional[dict] = None,
    return_timeout: Optional[int] = None,
) -> str:
    """
    Create a new data collection in a workspace.
    There are two types: `dynamic` (provide a `query` expression to
    automatically select matching entities) or `manual` (provide an explicit
    `entities` list of UUIDs). To enable RAG/semantic search, configure
    `embedding` with vectorization settings. Returns an async job UUID — the
    collection enters `processing` state and moves to `published` when done.

    Args:
        workspace_uuid (str): The UUID of the parent workspace.
        name (Optional[str]): Name for the collection.
        description (Optional[str]): Human-readable description.
        type (Optional[str]): `manual` or `dynamic`. If `query` is provided,
            the API defaults to `dynamic`; if `entities` is provided, the API
            defaults to `manual`.
        query (Optional[dict]): For dynamic collections, an expression or
            existing query reference. The `expression` value must be a valid
            JSON string (double-quoted keys/values), e.g.
            `{"expression": "{\"type\": \"pdf\"}"}` or
            `{"uuid": "existing-query-uuid"}`.
        entities (Optional[list[dict]]): For manual collections, an explicit
            list of entity references, e.g. `[{"uuid": "entity-uuid-1"}]`.
        embedding (Optional[dict]): Vectorization settings. When `enabled`
            is true, ONTAP requires `dimension`, `chunk_type`, and
            `quantization` to be set explicitly — it does not apply defaults
            for these. `chunk_size` is required only when `chunk_type` is
            `fixed_size` or `recursive`; it is ignored for `sentence`,
            `paragraph`, `full_file`, and `semantic`. `re_rank` is optional
            (omit to leave it unset). Valid example:
            `{"enabled": true, "dimension": 1024, "chunk_size": 512,
            "chunk_type": "fixed_size", "quantization": "fp32",
            "re_rank": true}`. Allowed values: `dimension` 512/768/1024;
            `chunk_size` 3–1536; `chunk_type` one of `sentence`, `paragraph`,
            `full_file`, `semantic`, `fixed_size`, `recursive`; `quantization`
            one of `fp32`, `fp16`, `fp8`, `uint8`; `re_rank` true/false.
        return_timeout (Optional[int]): Seconds to wait for the async job to
            finish before returning (0–120, default 0 = immediate 202).

    Returns:
        str: JSON string with the async job envelope
        (`{"job": {"uuid": ..., "state": "queued"}}`), or the created data
        collection object if the job completes within `return_timeout`.

    """
    if return_timeout is not None and not (
        _RETURN_TIMEOUT_MIN <= return_timeout <= _RETURN_TIMEOUT_MAX
    ):
        return (
            f"Error: return_timeout must be between {_RETURN_TIMEOUT_MIN} and "
            f"{_RETURN_TIMEOUT_MAX} seconds (got {return_timeout})"
        )

    candidate_body: list[tuple[str, object | None]] = [
        ("name", name),
        ("description", description),
        ("type", type),
        ("query", query),
        ("entities", entities),
        ("embedding", embedding),
    ]
    body: dict = {key: value for key, value in candidate_body if value is not None}

    params: dict[str, int] = {}
    if return_timeout is not None:
        params["return_timeout"] = return_timeout

    path = f"/data-engine/workspaces/{workspace_uuid}/data-collections"

    try:
        data = await aide_request(
            "POST",
            path,
            params=params if params else None,
            body=body,
            use_data_services=False,
        )
        # Add resource context to the bare status response.
        if isinstance(data, dict) and set(data.keys()) == {"status"}:
            extra = {"workspace_uuid": workspace_uuid}
            if name is not None:
                extra["name"] = name
            data = {**data, **extra}
        return json.dumps(data, indent=2)
    except AideApiError as e:
        return _format_api_error(e)
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in aide_data_collection_create")
        return f"Error: {type(e).__name__}: {e}"


async def aide_data_collection_update(
    workspace_uuid: str,
    uuid: str,
    description: Optional[str] = None,
    query: Optional[dict] = None,
    embedding: Optional[dict] = None,
    return_timeout: Optional[int] = None,
) -> str:
    """
    Update a data collection's description, query expression, or embedding
    settings. Changing the query or embedding triggers reprocessing (returns
    an async job UUID). This is also used to publish a draft collection —
    updating triggers the processing pipeline. Only provide the fields you
    want to change.

    Args:
        workspace_uuid (str): The UUID of the parent workspace.
        uuid (str): The UUID of the data collection to update.
        description (Optional[str]): New description.
        query (Optional[dict]): Updated query expression or reference. The
            `expression` value must be a valid JSON string (double-quoted
            keys/values), e.g. `{"expression": "{\"type\": \"pdf\"}"}`.
        embedding (Optional[dict]): Updated embedding settings.
        return_timeout (Optional[int]): Seconds to wait for the async job to
            finish before returning (0–120, default 0).

    Returns:
        str: JSON string with the updated data collection object, or the
        async job envelope when reprocessing is triggered.

    """
    if return_timeout is not None and not (
        _RETURN_TIMEOUT_MIN <= return_timeout <= _RETURN_TIMEOUT_MAX
    ):
        return (
            f"Error: return_timeout must be between {_RETURN_TIMEOUT_MIN} and "
            f"{_RETURN_TIMEOUT_MAX} seconds (got {return_timeout})"
        )

    # PATCH semantics: only include fields the caller provided.
    candidate_body: list[tuple[str, object | None]] = [
        ("description", description),
        ("query", query),
        ("embedding", embedding),
    ]
    body: dict = {key: value for key, value in candidate_body if value is not None}

    if not body:
        return "Error: at least one of description, query, or embedding must be provided"

    params: dict[str, int] = {}
    if return_timeout is not None:
        params["return_timeout"] = return_timeout

    path = f"/data-engine/workspaces/{workspace_uuid}/data-collections/{uuid}"

    try:
        data = await aide_request(
            "PATCH",
            path,
            params=params if params else None,
            body=body,
            use_data_services=False,
        )
        if isinstance(data, dict) and set(data.keys()) == {"status"}:
            data = {**data, "workspace_uuid": workspace_uuid, "uuid": uuid}
        return json.dumps(data, indent=2)
    except AideApiError as e:
        return _format_api_error(e)
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in aide_data_collection_update")
        return f"Error: {type(e).__name__}: {e}"


async def aide_data_collection_delete(
    workspace_uuid: str,
    uuid: str,
    return_timeout: Optional[int] = None,
) -> str:
    """
    Delete a data collection from a workspace. This removes all associated
    embeddings and search indexes. Returns an async job UUID for tracking.

    Args:
        workspace_uuid (str): The UUID of the parent workspace.
        uuid (str): The UUID of the data collection to delete.
        return_timeout (Optional[int]): Seconds to wait for the async job to
            finish before returning (0–120, default 0).

    Returns:
        str: JSON string — `{"status": "deleted"}` on synchronous success, or
        the async job envelope (`{"job": {"uuid": ..., "state": "queued"}}`).

    """
    if return_timeout is not None and not (
        _RETURN_TIMEOUT_MIN <= return_timeout <= _RETURN_TIMEOUT_MAX
    ):
        return (
            f"Error: return_timeout must be between {_RETURN_TIMEOUT_MIN} and "
            f"{_RETURN_TIMEOUT_MAX} seconds (got {return_timeout})"
        )

    params: dict[str, int] = {}
    if return_timeout is not None:
        params["return_timeout"] = return_timeout

    path = f"/data-engine/workspaces/{workspace_uuid}/data-collections/{uuid}"

    try:
        data = await aide_request(
            "DELETE",
            path,
            params=params if params else None,
            use_data_services=False,
        )
        if isinstance(data, dict) and set(data.keys()) == {"status"}:
            data = {**data, "workspace_uuid": workspace_uuid, "uuid": uuid}
        return json.dumps(data, indent=2)
    except AideApiError as e:
        return _format_api_error(e)
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in aide_data_collection_delete")
        return f"Error: {type(e).__name__}: {e}"
