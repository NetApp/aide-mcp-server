from typing import Optional

import httpx
import json

from ..config import load_credentials
from ..oauth2 import get_access_token


async def netapp_data_engine_search(
    prompt: str,
    max_records: Optional[int] = None,
    return_timeout: Optional[int] = None,
) -> str:
    """Search documents using the configured RAG API with OAuth2."""

    try:
        config = load_credentials()
        access_token = await get_access_token(config)

        api_params = {"prompt": prompt}
        if max_records is not None:
            api_params["max_records"] = max_records

        async with httpx.AsyncClient(verify=config["verify_ssl"]) as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            timeout = return_timeout if return_timeout else 15

            response = await client.get(
                config["rag_search_api_endpoint_url"],
                params=api_params,
                headers=headers,
                **({"timeout": timeout} if timeout is not None else {}),
            )

            try:
                json_response = response.json()

                if isinstance(json_response, dict) and "error" in json_response:
                    error_info = json_response["error"]
                    error_message = error_info.get("message", "Unknown error")
                    error_code = error_info.get("code", "Unknown code")
                    return f"API Error {error_code}: {error_message}"

                return json.dumps(json_response, indent=2)

            except Exception as json_error:
                return f"Failed to parse JSON response: {json_error}. Raw response: {response.text}"

    except Exception as e:
        return f"Error performing search: {str(e)}"
