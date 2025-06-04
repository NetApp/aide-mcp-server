from typing import Optional
from .config import load_credentials
from .oauth2 import get_access_token
import httpx

async def netapp_data_engine_search(query: str, max_records: Optional[int] = None, return_timeout: Optional[int] = None) -> str:

    """
    
    Searches for documents using a RAG API with OAuth2 authentication.

    Args:
        query (str): The search query (required)
        max_records (Optional[int]): Max number of records to return (optional)
        return_timeout (Optional[int]): Request timeout in seconds (optional)
    
    Returns:
        str: The API response as a string, or an error message

    """

    try:
        # Loads configuration (credentials and endpoints) from .netapp file
        config = load_credentials()

        # acquires a valid OAuth2 access token
        access_token = await get_access_token(config)

        # Builds the request payload for the RAG search API
        api_params = {"query": query}
        if max_records is not None:
            api_params["max_records"] = max_records
        if return_timeout is not None:
            api_params["return_timeout"] = return_timeout

        # Makes the authenticated API request using the access token
        async with httpx.AsyncClient(verify=config['verify_ssl']) as client:

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            timeout = return_timeout if return_timeout else None

            response = await client.post(
                config['rag_search_api_endpoint_url'],
                json=api_params,
                headers=headers,
                **({"timeout": timeout} if timeout is not None else {}) 
                # Sends timeout parameter if return_timeout available, else don't send anything
            )

            # Raises an error for HTTP error codes
            response.raise_for_status()
            return response.text # Returns API response as a string
        
    except Exception as e:
        # Returns an error message if anything fails
        return f"Error performing search: {str(e)}"