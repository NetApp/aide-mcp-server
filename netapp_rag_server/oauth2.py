import time
import httpx

# In-memory cache for storing the OAuth2 access token and its expiry time
_token_cache = {}

async def get_access_token(config):

    """

    Acquires an OAuth2 token using the provided config.
    Caches the token until it is close to expiration.
    
    Args:
        config (dict): The configuration dictionary loaded from .netapp.

    Returns:
        str: The access token string

    Raises:
        Exception: If the token request failes or the response is invalid
    
    """

    token_endpoint = config['token_request_endpoint_url'] 

    # Uses the token endpoint URL as a cache key (hashed for uniqueness)
    cache_key = f"token_{hash(token_endpoint)}"
    
    # Checks if a valid token is already cached
    if cache_key in _token_cache:
        token_data = _token_cache[cache_key]

        # If the token is not close to expiring (5 min buffer), reuses it
        if time.time() < token_data['expires_at'] - 300:
            return token_data['access_token']

    # No valid cached token, so requests for a new one
    async with httpx.AsyncClient(verify=config['verify_ssl']) as client:

        response = await client.post(
            token_endpoint,
            data=config['token_request_params'],
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
        return token_data['access_token'] # Returns the access token as a string