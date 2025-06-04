import time
from urllib.parse import urlparse
import httpx

# In-memory cache for storing the OAuth2 access token and its expiry time
_token_cache = {}

def _determine_provider(token_request_endpoint_url):

    """
    Determines the OIDC provider (Microsoft Entra or ADFS) based on the token endpoint URL.
    """

    parsed_url = urlparse(token_request_endpoint_url)

    if "login.microsoftonline.com" in parsed_url.netloc:
        return "microsoft_entra"
    elif "adfs" in parsed_url.netloc:
        return "adfs"
    else:
        raise ValueError("Unsupported OIDC provider.")
    
def _prepare_token_params(provider, params):

    """
    Prepares the token request parameters according to the provider and authentication method.
    Removes unnecessary or conflicting parameteres for each flow.
    """

    # Copies params to avoid mutating the original config
    data = params.copy()

    # Determines auth method: shared secret or certificate
    if "client_secret" in data:

        # Shared secret flow
        # Removes assertion fields if present
        data.pop("client_assertion_type", None)
        data.pop("client_assertion", None)

        # For ADFS, 'scope' is optional and removed if empty
        if provider == "adfs" and not data.get("scope"):
            data.pop("scope", None)

    elif "client_assertion" in data:

        # Certificate flow
        # Removes secret if present
        data.pop("client_secret", None)

        # For ADFS, 'scope' and 'client_id' are optional, and removed if empty
        if provider == "adfs":
            if not data.get("client_id"):
                data.pop("client_id", None)
            if not data.get("scope"):
                data.pop("scope", None)

    else:
        # Raises an error if neither method is found
        raise ValueError("Neither client_secret nor client_assertion present in params.")
    
    return data

async def get_access_token(config):

    """

    Acquires an OAuth2 token using the provided config.
    - Supports both Microsoft Entra ID and ADFS.
    - Handles both shared secret and certificate aithentication flows.
    - Caches the token until it is close to expiration.
    
    Args:
        config (dict): The configuration dictionary loaded from .netapp.

    Returns:
        str: The access token string

    Raises:
        Exception: If the token request failes or the response is invalid
    
    """

    token_endpoint = config['token_request_endpoint']

    # Uses the token endpoint URL as a cache key (hashed for uniqueness)
    cache_key = f"token_{hash(token_endpoint)}"
    
    # Checks if a valid token is already cached
    if cache_key in _token_cache:
        token_data = _token_cache[cache_key]

        # If the token is not close to expiring (5 min buffer), reuses it
        if time.time() < token_data['expires_at'] - 300:
            return token_data['access_token']
        
    # Detects provider
    provider = _determine_provider(token_endpoint)

    # Prepares parameters for token request
    params = _prepare_token_params(provider, config['token_request_params'])

    # No valid cached token, so makes an async HTTP POST request to acquire a new token
    async with httpx.AsyncClient(verify=config['verify_ssl']) as client:

        response = await client.post(
            token_endpoint,
            data=params,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

    # If request fails, raises an exception with the error details
        if response.status_code != 200:
            raise Exception(f"Token acquisition failed: {response.status_code} - {response.text}")
        
        token_data = response.json()

        # Uses 'expires_in' from response if present, otherwise default to 3599 seconds (~1 hour)
        expires_in = token_data.get('expires_in', 3599)

        # Caches the token with its expiration time (current time + expires_in seconds)
        _token_cache[cache_key] = {
            'access_token': token_data['access_token'],
            'expires_at': time.time() + expires_in
        }
        return token_data['access_token'] # Returns the access token asa string