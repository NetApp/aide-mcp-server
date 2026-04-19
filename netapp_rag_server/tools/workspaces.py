# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for workspace lifecycle: list, get, create, update, and delete."""

import json
from typing import Optional


async def aide_workspaces_list(
    name: Optional[str] = None,
    state: Optional[str] = None,
    owner: Optional[str] = None,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
) -> str:
    """List all AIDE workspaces visible to the caller.

    Use filter parameters to narrow results: ``name`` for a specific
    workspace, ``state`` to find workspaces in a particular lifecycle state
    (processing, ready, failed, outdated), or ``owner`` to find workspaces
    owned by a specific user.  Returns workspace summaries including entity
    counts, space usage, and current state.
    """
    dummy_response = {
        "num_records": 1,
        "total_records": 1,
        "records": [
            {
                "uuid": "4ea7a442-86d1-11e0-ae1c-123478563412",
                "name": "Example Workspace",
                "state": "ready",
                "owner": "admin",
                "description": "Dummy workspace for development testing",
                "entity_count": 42,
                "data_collection_count": 2,
                "space": {
                    "total": 1073741824,
                    "used": 536870912,
                    "available": 536870912,
                },
                "last_refresh_time": "2026-04-10T12:00:00Z",
                "refresh_interval": "PT1H",
                "create_time": "2026-03-15T08:30:00Z",
                "update_time": "2026-04-10T12:00:00Z",
            }
        ],
    }
    return json.dumps(dummy_response, indent=2)

