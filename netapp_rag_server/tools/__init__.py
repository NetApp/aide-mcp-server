# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""Public MCP tool callables for this package.

As functions are added in workspaces, data_sources, data_collections, search, jobs,
entities, and composites, import them here and extend ``__all__`` so callers can use
``from netapp_rag_server.tools import ...`` consistently.
"""

from .data_collections import aide_data_collection_get, aide_data_collections_list
from .data_sources import (
    aide_data_source_get,
    aide_data_sources_list,
    aide_workspace_data_source_create,
    aide_workspace_data_source_delete,
    aide_workspace_data_source_get,
    aide_workspace_data_sources_list,
)
from .entities import aide_workspace_entities_list, aide_workspace_entity_get
from .search import netapp_data_engine_search
from .workspaces import (
    aide_workspace_create,
    aide_workspace_delete,
    aide_workspace_get,
    aide_workspace_update,
    aide_workspaces_list,
)

__all__ = [
    "aide_workspace_entity_get",
    "netapp_data_engine_search",
    "aide_workspace_create",
    "aide_workspace_delete",
    "aide_workspace_get",
    "aide_workspace_update",
    "aide_workspaces_list",
    "aide_data_collection_get",
    "aide_data_collections_list",
    "aide_data_source_get",
    "aide_data_sources_list",
    "aide_workspace_data_source_create",
    "aide_workspace_data_source_delete",
    "aide_workspace_data_source_get",
    "aide_workspace_data_sources_list",
    "aide_workspace_entities_list",
]
