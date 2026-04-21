# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for workspace entities (files/objects): list with filters and get by id."""

from __future__ import annotations

import json
from typing import Optional

from ..client import AideApiError, AideConfigError, aide_request


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
        if e.code == "timeout":
            return f"Error: {e.message}"
        return f"API Error {e.code}: {e.message}"
    except AideConfigError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
