# Copyright 2026 NetApp, Inc. All Rights Reserved.

# Entry point to setup and run the MCP server

import argparse
import asyncio
import contextlib
import importlib
import logging
import sys
from collections import defaultdict

from fastmcp import FastMCP

from .client import close_client, set_config
from .config import load_credentials
from .oauth2 import authenticate_eagerly, start_token_refresh_loop

logger = logging.getLogger(__name__)

# Shared base for data-engineer and data-scientist (Phase 1).
# Read-only on workspaces (#1–2 only; no #3–5).
# Admin: collections read-only — no #14–16 (spec §7.3).
#
# Phase 2+ divergence (ACL tools — not yet assigned tool numbers):
#   data-engineer  — adds workspace ACLs (readonly) + collection ACLs (all)
#   data-scientist — no ACL access
# When ACL tool numbers are assigned, add them to _DATA_ENGINEER_TOOLS only.
_DATA_USER_TOOLS_BASE: set[int] = {
    1, 2, 6, 7, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
}

_DATA_ENGINEER_TOOLS:  set[int] = _DATA_USER_TOOLS_BASE | set()
_DATA_SCIENTIST_TOOLS: set[int] = _DATA_USER_TOOLS_BASE | set()

_DATA_USER_COMPOSITES: set[str] = {"C1", "C2", "C3"}

PERSONAS = {
    "admin": {
        "description": "Storage Administrator",
        "tools": {
            1, 2, 3, 4, 5,
            6, 7, 8, 9, 10, 11,
            12, 13,
            18, 19, 20, 21,
        },
        "composites": {"C1", "C2", "C3"},
        "requires_base_url": True,
        "requires_data_services": False,
    },
    "data-engineer": {
        "description": "Data Engineer",
        "tools": set(_DATA_ENGINEER_TOOLS),
        "composites": set(_DATA_USER_COMPOSITES),
        "requires_base_url": False,
        "requires_data_services": True,
    },
    "data-scientist": {
        "description": "Data Scientist",
        "tools": set(_DATA_SCIENTIST_TOOLS),
        "composites": set(_DATA_USER_COMPOSITES),
        "requires_base_url": False,
        "requires_data_services": True,
    },
    "search-only": {
        "description": "Search Consumer",
        "tools": {17},
        "composites": set(),
        "requires_base_url": False,
        "requires_data_services": True,
    },
    "all": {
        "description": "All Roles",
        "tools": set(range(1, 22)),
        "composites": {"C1", "C2", "C3"},
        "requires_base_url": False,
        "requires_data_services": True,
    },
}

# Maps each tool number (1–21) to (module_path, function_name) within tools/.
TOOL_REGISTRY: dict[int, tuple[str, str]] = {
    1:  ("netapp_rag_server.tools.workspaces",       "aide_workspaces_list"),
    2:  ("netapp_rag_server.tools.workspaces",       "aide_workspace_get"),
    3:  ("netapp_rag_server.tools.workspaces",       "aide_workspace_create"),
    4:  ("netapp_rag_server.tools.workspaces",       "aide_workspace_update"),
    5:  ("netapp_rag_server.tools.workspaces",       "aide_workspace_delete"),
    6:  ("netapp_rag_server.tools.data_sources",     "aide_data_sources_list"),
    7:  ("netapp_rag_server.tools.data_sources",     "aide_data_source_get"),
    8:  ("netapp_rag_server.tools.data_sources",     "aide_workspace_data_sources_list"),
    9:  ("netapp_rag_server.tools.data_sources",     "aide_workspace_data_source_get"),
    10: ("netapp_rag_server.tools.data_sources",     "aide_workspace_data_source_create"),
    11: ("netapp_rag_server.tools.data_sources",     "aide_workspace_data_source_delete"),
    12: ("netapp_rag_server.tools.data_collections", "aide_data_collections_list"),
    13: ("netapp_rag_server.tools.data_collections", "aide_data_collection_get"),
    14: ("netapp_rag_server.tools.data_collections", "aide_data_collection_create"),
    15: ("netapp_rag_server.tools.data_collections", "aide_data_collection_update"),
    16: ("netapp_rag_server.tools.data_collections", "aide_data_collection_delete"),
    17: ("netapp_rag_server.tools",                  "netapp_data_engine_search"),
    18: ("netapp_rag_server.tools.jobs",             "aide_jobs_list"),
    19: ("netapp_rag_server.tools.jobs",             "aide_job_get"),
    20: ("netapp_rag_server.tools.entities",         "aide_workspace_entities_list"),
    21: ("netapp_rag_server.tools.entities",         "aide_workspace_entity_get"),
}

# Maps each composite ID ("C1"–"C3") to (module_path, function_name, dependency tool numbers).
COMPOSITE_REGISTRY: dict[str, tuple[str, str, set[int]]] = {
    "C1": ("netapp_rag_server.tools.composites", "aide_workspace_status",        {2}),
    "C2": ("netapp_rag_server.tools.composites", "aide_data_collection_status",  {13}),
    "C3": ("netapp_rag_server.tools.composites", "aide_poll_job_until_complete", {19}),
}

_SEARCH_TOOL_NUMBERS: set[int] = {17}


def resolve_tools(
    persona_name: str,
    config: dict,
) -> list[tuple[str, str]]:
    """Return the list of (module_path, function_name) tuples that should be
    registered for *persona_name* given the loaded *config*.

    The algorithm (spec §7.4):
      1. Start with the persona's full tool set.
      2. If ``base_url`` is absent → intersect with search tool (#17).
      3. If neither ``data_services_base_url`` nor
         ``rag_search_api_endpoint_url`` is present → remove #17.
      4. Include composites only when all primitive deps survived.
    """
    persona = PERSONAS[persona_name]
    allowed: set[int] = set(persona["tools"])

    has_base_url = "base_url" in config
    has_data_services = (
        "data_services_base_url" in config
        or "rag_search_api_endpoint_url" in config
    )

    if persona.get("requires_base_url") and not has_base_url:
        logger.warning(
            "Persona '%s' expects 'base_url' but it is not configured.",
            persona_name,
        )

    if persona.get("requires_data_services") and not has_data_services:
        logger.warning(
            "Persona '%s' expects a data-services URL but neither "
            "'data_services_base_url' nor 'rag_search_api_endpoint_url' "
            "is configured.",
            persona_name,
        )

    # Cluster-management APIs need base_url; without it only tool #17 (search) can
    # run, and only if the persona allows it (intersection).
    if not has_base_url:
        allowed &= _SEARCH_TOOL_NUMBERS

    # Search needs data_services_base_url or rag_search_api_endpoint_url.
    if not has_data_services:
        allowed -= _SEARCH_TOOL_NUMBERS

    resolved: list[tuple[str, str]] = []
    for tool_num in sorted(allowed):
        entry = TOOL_REGISTRY.get(tool_num)
        if entry is not None:
            resolved.append(entry)

    for comp_id in sorted(persona["composites"]):
        comp = COMPOSITE_REGISTRY.get(comp_id)
        if comp is None:
            continue
        module_path, func_name, deps = comp
        if deps <= allowed:
            resolved.append((module_path, func_name))

    return resolved


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="netapp-data-engine-mcp"
    )
    parser.add_argument(
        "--persona",
        choices=list(PERSONAS.keys()),
        default=None,
        help="AIDE role that determines which tools are registered.",
    )
    args = parser.parse_args(argv)
    if args.persona is None:
        parser.print_help(sys.stderr)
        parser.exit(
            2,
            "\nerror: the following arguments are required: --persona\n",
        )
    return args


async def _async_main(args: argparse.Namespace) -> None:
    try:
        config = load_credentials()
    except Exception as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)

    set_config(config)

    logging.info("Starting OAuth2 login (complete in the browser if prompted)...")
    await authenticate_eagerly(config)

    persona = PERSONAS[args.persona]
    resolved = resolve_tools(args.persona, config)

    logger.info(
        "Persona '%s' (%s): registering %d tools.",
        args.persona,
        persona["description"],
        len(resolved),
    )

    if not resolved:
        logger.error(
            "Persona '%s' (%s) has zero available tools with the current "
            "config profile.  Check that your ~/.netapp file includes the "
            "endpoint keys required by this persona.",
            args.persona,
            persona["description"],
        )
        sys.exit(1)

    mcp = FastMCP(f"NetApp AIDE Server ({args.persona})")

    # Dynamically import each tool function and register it with mcp.tool().
    by_module: defaultdict[str, list[str]] = defaultdict(list)
    for module_path, func_name in resolved:
        by_module[module_path].append(func_name)

    registered = 0
    for module_path, func_names in by_module.items():
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            for name in func_names:
                logger.warning("Skipping tool %s: %s", name, exc)
            continue
        for name in func_names:
            try:
                fn = getattr(mod, name)
                mcp.tool()(fn)
                registered += 1
            except AttributeError as exc:
                logger.warning("Skipping tool %s: %s", name, exc)

    if registered == 0:
        logger.error(
            "Persona '%s' (%s) resolved %d tools but none could be imported. "
            "Tool modules may not be implemented yet.",
            args.persona,
            persona["description"],
            len(resolved),
        )
        sys.exit(1)

    logger.info(
        "Persona '%s' (%s): registered %d of %d resolved tools.",
        args.persona,
        persona["description"],
        registered,
        len(resolved),
    )

    refresh_task = start_token_refresh_loop(config)

    try:
        await mcp.run_async(transport="stdio")
    finally:
        refresh_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await refresh_task
        await close_client()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    try:
        asyncio.run(_async_main(args))
    except Exception as e:
        logging.error(f"Server startup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
