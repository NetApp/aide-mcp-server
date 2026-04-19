# Copyright 2026 NetApp, Inc. All Rights Reserved.

"""MCP tools for semantic search over a data collection (RAG-style queries)."""

import json
from typing import Optional

import httpx

from ..config import load_credentials
from ..oauth2 import get_access_token


async def netapp_data_engine_search(
    prompt: str,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
) -> str:

    """
    
    Searches for documents using NetApp AIDE's RAG API. This RAG API implements a vector-based semantic similarity search engine that retrieves relevant documents based on the provided query. The prompt arg represents the search query. Queries should be crafted based on vector search best practices to ensure optimal results. For example, using specific keywords, phrases, or context that align with the content of the documents being searched can help improve the relevance of the results. The max_records arg allows you to limit the number of search results returned by the API. If not provided, it will return all matching records. The return_timeout arg specifies how long to wait for a response from the API before timing out. If not provided, it defaults to 15 seconds.

    Args:
        prompt (str): The search query (required)
        max_records (Optional[int]): Max number of records to return (optional)
        return_timeout (Optional[int]): Request timeout in seconds (optional)

    Returns:
        str: The API response as a string, or an error message

    """

    try:
        config = load_credentials()
        access_token = await get_access_token(config)

        api_params = {"prompt": prompt}
        if max_records is not None:
            api_params["max_records"] = max_records

        async with httpx.AsyncClient(verify=config["verify_ssl"]) as client:

            headers = {
                "Authorization": f"Bearer {access_token}"
            }

            timeout = return_timeout if return_timeout is not None else 15

            response = await client.get(
                config["rag_search_api_endpoint_url"],
                params=api_params,
                headers=headers,
                timeout=timeout,
            )

            # Parse the response body as JSON.
            try:
                json_response = response.json()
            except (ValueError, httpx.DecodingError) as json_error:
                return f"Failed to parse JSON response: {json_error}. Raw response: {response.text}"

            if not response.is_success:
                if isinstance(json_response, dict) and "error" in json_response:
                    error_info = json_response["error"]
                    if isinstance(error_info, dict):
                        error_message = error_info.get("message", "Unknown error")
                        error_code = error_info.get("code", "Unknown code")
                    else:
                        error_message = str(error_info)
                        error_code = response.status_code
                    return f"API Error {error_code}: {error_message}"
                response.raise_for_status()

            return json.dumps(json_response, indent=2)

    except Exception as e:
        return f"Error performing search: {str(e)}"
