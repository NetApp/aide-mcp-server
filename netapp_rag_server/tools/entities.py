# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for workspace entities (files/objects): list with filters and get by id."""

from __future__ import annotations

import json
from typing import Optional

from ..client import AideApiError, AideConfigError, aide_request


async def aide_workspace_entities_list(
    workspace_uuid: str,
    name: Optional[str] = None,
    type: Optional[str] = None,
    format: Optional[str] = None,
    extension: Optional[str] = None,
    has_pii: Optional[bool] = None,
    size: Optional[int] = None,
    datasource_uuid: Optional[str] = None,
    datasource_name: Optional[str] = None,
    attributes_system_key: Optional[str] = None,
    attributes_system_value: Optional[str] = None,
    attributes_custom_key: Optional[str] = None,
    attributes_custom_value: Optional[str] = None,
    attributes_content_key: Optional[str] = None,
    attributes_content_value: Optional[str] = None,
    attributes_extended_key: Optional[str] = None,
    attributes_extended_value: Optional[str] = None,
    can_preview: Optional[bool] = None,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """
    List and filter entities (files/objects) in a workspace. 
    This is the metadata search tool — use filter parameters for structured discovery. 
    Common filters: `name` (filename, supports wildcards), `type` (file/object), `format` (pdf, docx, jpeg, etc.), `extension`, `has_pii` (true/false to find sensitive data), `size`, and attribute filters for system/custom/content/extended metadata key-value pairs. 
    Use `datasource_name` or `datasource_uuid` to scope to a specific storage source. 
    Results include full entity metadata, attributes, and permissions.

    Args:
        workspace_uuid (str): The UUID of the workspace to list entities from.
        name (Optional[str]): Filter by entity name (supports wildcards).
        type (Optional[str]): Filter by entity type (`file` or `object`).
        format (Optional[str]): Filter by content format (e.g. `pdf`, `docx`, `jpeg`, `mp4`).
        extension (Optional[str]): Filter by file extension.
        has_pii (Optional[bool]): Filter by PII flag — `True` to find entities containing personally identifiable information.
        size (Optional[int]): Filter by entity size in bytes.
        datasource_uuid (Optional[str]): Filter by originating data source UUID (maps to API param `datasource.uuid`).
        datasource_name (Optional[str]): Filter by originating data source name (maps to `datasource.name`).
        attributes_system_key (Optional[str]): Filter by system attribute key (maps to `attributes.system.key`).
        attributes_system_value (Optional[str]): Filter by system attribute value (maps to `attributes.system.value`).
        attributes_custom_key (Optional[str]): Filter by custom attribute key (maps to `attributes.custom.key`).
        attributes_custom_value (Optional[str]): Filter by custom attribute value (maps to `attributes.custom.value`).
        attributes_content_key (Optional[str]): Filter by content attribute key (maps to `attributes.content.key`).
        attributes_content_value (Optional[str]): Filter by content attribute value (maps to `attributes.content.value`).
        attributes_extended_key (Optional[str]): Filter by extended attribute key (maps to `attributes.extended.key`).
        attributes_extended_value (Optional[str]): Filter by extended attribute value (maps to `attributes.extended.value`).
        can_preview (Optional[bool]): Filter by whether the entity content can be previewed.
        max_records (Optional[int]): Maximum number of records to return in this page.
        return_timeout (Optional[int]): Seconds to wait for the response (0–120).
        fields (Optional[str]): CSV list of fields to include in the response.
        order_by (Optional[str]): Sort order, e.g. `name asc,size desc`.

    Returns:
        str: The list of matching entities as a JSON string. The envelope includes
        `num_records` (count in this page), `total_records` (total matching the filter
        across the whole collection), and `records` (list of entity objects).

    """
    # ONTAP nests several query parameters under dotted paths
    # (datasource.*, attributes.<scope>.*) which Python identifiers cannot
    # express; map the snake_case args to their wire-format names below.
    candidate_params: list[tuple[str, object | None]] = [
        ("name", name),
        ("type", type),
        ("format", format),
        ("extension", extension),
        ("has_pii", has_pii),
        ("size", size),
        ("datasource.uuid", datasource_uuid),
        ("datasource.name", datasource_name),
        ("attributes.system.key", attributes_system_key),
        ("attributes.system.value", attributes_system_value),
        ("attributes.custom.key", attributes_custom_key),
        ("attributes.custom.value", attributes_custom_value),
        ("attributes.content.key", attributes_content_key),
        ("attributes.content.value", attributes_content_value),
        ("attributes.extended.key", attributes_extended_key),
        ("attributes.extended.value", attributes_extended_value),
        ("can_preview", can_preview),
        ("max_records", max_records),
        ("return_timeout", return_timeout),
        ("fields", fields),
        ("order_by", order_by),
    ]

    params: dict[str, str | int] = {}
    for query_param, value in candidate_params:
        if value is None:
            continue
        # bool must be checked before int because bool is a subclass of int;
        # ONTAP expects lowercase "true"/"false" while httpx would otherwise
        # serialize Python booleans via str() as "True"/"False".
        if isinstance(value, bool):
            params[query_param] = "true" if value else "false"
        elif isinstance(value, (str, int)):
            params[query_param] = value

    path = f"/data-engine/workspaces/{workspace_uuid}/entities"

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


async def aide_workspace_entity_get(
    workspace_uuid: str,
    uuid: str,
    workspace_version_uuid: Optional[str] = None,
    fields: Optional[str] = None,
) -> str:
    """
    Retrieve full details of a specific entity (file or object) in a workspace.
    Returns the entity's name, type, format, size, URI, PII flag, all attributes (system, custom, content, extended), permissions, data source info, and timestamps.
    Optionally specify `workspace_version_uuid` to see the entity as it was in a previous workspace version.

    Args:
        workspace_uuid (str): The UUID of the workspace.
        uuid (str): The UUID of the entity.
        workspace_version_uuid (Optional[str]): The UUID of the workspace version.
        fields (Optional[str]): The fields to return.

    Returns:
        str: The entity's details as a JSON string.

    """
    params: dict[str, str] = {}
    if workspace_version_uuid is not None:
        params["workspace.version.uuid"] = workspace_version_uuid
    if fields is not None:
        params["fields"] = fields

    path = f"/data-engine/workspaces/{workspace_uuid}/entities/{uuid}"

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
