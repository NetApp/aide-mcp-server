from typing import Optional
from .config import load_credentials
from .oauth2 import get_access_token
import httpx
import json

async def netapp_data_engine_search(prompt: str, max_records: Optional[int] = None, return_timeout: Optional[int] = None) -> str:

    """
    
    Searches for documents using a RAG API with OAuth2 authentication.

    Args:
        prompt (str): The search query (required)
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

        # Builds the request parameters for the RAG search API call
        api_params = {"prompt": prompt} 
        if max_records is not None:
            api_params["max_records"] = max_records

        # Makes the authenticated API request using the access token
        async with httpx.AsyncClient(verify=config['verify_ssl']) as client:

            headers = {
                "Authorization": f"Bearer {access_token}"
            }

            timeout = return_timeout if return_timeout else 15  

            response = await client.get(
                config['rag_search_api_endpoint_url'],
                params=api_params,
                headers=headers,
                **({"timeout": timeout} if timeout is not None else {})  # Sends timeout parameter if return_timeout available, else don't send anything
            )
            
            # Try to parse JSON response
            try:
                json_response = response.json()
                
                # Check if the response contains an error
                if isinstance(json_response, dict) and 'error' in json_response:
                    error_info = json_response['error']
                    error_message = error_info.get('message', 'Unknown error')
                    error_code = error_info.get('code', 'Unknown code')
                    return f"API Error {error_code}: {error_message}"
                
                # Convert successful response to formatted string
                return json.dumps(json_response, indent=2)
                
            except Exception as json_error:
                return f"Failed to parse JSON response: {json_error}. Raw response: {response.text}"
        
    except Exception as e:
        # Returns an error message if anything fails
        return f"Error performing search: {str(e)}"