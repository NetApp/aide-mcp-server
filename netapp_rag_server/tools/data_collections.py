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
    List all data collections in a workspace.
    Data collections are curated subsets of workspace entities, optionally with
    vector embeddings for RAG search. Filter by `name`, `type` (`manual` =
    explicit entity list, `dynamic` = query-driven), `state` (`draft`,
    `processing`, `published`, `failed`, `outdated`), or `embedding_enabled`
    to find RAG-ready collections.

    Args:
        workspace_uuid (str): The UUID of the parent workspace.
        name (Optional[str]): Filter by collection name.
        type (Optional[str]): Filter by collection type (`manual` or `dynamic`).
        state (Optional[str]): Filter by lifecycle state (`draft`, `processing`,
            `published`, `failed`, `outdated`).
        embedding_enabled (Optional[bool]): Filter by whether vectorization is
            enabled (maps to API param `embedding.enabled`).
        max_records (Optional[int]): Maximum number of records to return in this page.
        return_timeout (Optional[int]): Seconds to wait for the response (0–120).
        fields (Optional[str]): CSV list of fields to include in the response.
        order_by (Optional[str]): Sort order, e.g. `name asc,create_time desc`.

    Returns:
        str: The list of matching data collections as a JSON string. The envelope
        includes `num_records` (count in this page), `total_records` (total matching
        the filter across the whole collection), and `records` (list of data
        collection objects).

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
        if e.code in ("timeout", "connection_error"):
            return f"Error: {e.message}"
        return f"API Error {e.code}: {e.message}"
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
        if e.code in ("timeout", "connection_error"):
            return f"Error: {e.message}"
        return f"API Error {e.code}: {e.message}"
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in aide_data_collection_get")
        return f"Error: {type(e).__name__}: {e}"
