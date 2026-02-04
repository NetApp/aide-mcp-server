import time
import asyncio
import http.server
import secrets
import threading
import urllib.parse
import webbrowser
import httpx

# In-memory cache for storing the OAuth2 access token and its expiry time
_token_cache = {}

def _start_local_callback_server(redirect_uri: str):
    parsed = urllib.parse.urlparse(redirect_uri)

    if parsed.scheme != "http":
        raise ValueError("web_based_auth redirect_uri must use http.")

    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("web_based_auth redirect_uri must use localhost or 127.0.0.1.")

    host = parsed.hostname
    port = parsed.port or 80
    expected_path = parsed.path or "/"

    event = threading.Event()
    result = {}

    class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            request = urllib.parse.urlparse(self.path)
            if request.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return

            params = urllib.parse.parse_qs(request.query)
            result["code"] = params.get("code", [None])[0]
            result["state"] = params.get("state", [None])[0]
            result["error"] = params.get("error", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authentication complete. You can close this window.")

            event.set()

        def log_message(self, format, *args):
            return

    server = http.server.HTTPServer((host, port), OAuthCallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return event, result, server

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

    if config.get("web_based_auth"):
        return await _get_access_token_web_based(config)

    return await _get_access_token_password_grant(config)

async def _get_access_token_password_grant(config):
    token_endpoint = config['token_request_endpoint_url']

    # Uses the token endpoint URL as a cache key (hashed for uniqueness)
    cache_key = f"token_{hash((token_endpoint, 'password'))}"

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

        return token_data['access_token']

async def _get_access_token_web_based(config):
    authorization_endpoint = config['token_request_endpoint_url']
    web_auth = config['token_request_params']

    cache_key = f"token_{hash((authorization_endpoint, web_auth.get('client_id'), 'web'))}"

    if cache_key in _token_cache:
        token_data = _token_cache[cache_key]
        if time.time() < token_data['expires_at'] - 300:
            return token_data['access_token']

    state = secrets.token_urlsafe(16)

    auth_params = {
        "client_id": web_auth["client_id"],
        "response_type": "code",
        "redirect_uri": web_auth["redirect_uri"],
        "scope": web_auth.get("scope", "openid profile email"),
        "state": state,
    }

    auth_url = f"{authorization_endpoint}?{urllib.parse.urlencode(auth_params)}"

    event, result, server = _start_local_callback_server(web_auth["redirect_uri"])
    auth_timeout = web_auth.get("auth_timeout_seconds", 300)

    try:
        webbrowser.open(auth_url)
        await asyncio.to_thread(event.wait, auth_timeout)
    finally:
        server.server_close()

    if not event.is_set():
        raise TimeoutError("Authentication timed out waiting for the browser redirect.")

    if result.get("error"):
        raise Exception(f"Authorization error: {result['error']}")

    if result.get("state") != state:
        raise Exception("Authorization state mismatch.")

    code = result.get("code")
    if not code:
        raise Exception("Authorization code not found in redirect.")

    token_data = await _exchange_code_for_token(config, code)

    expires_in = token_data.get('expires_in', 3599)
    _token_cache[cache_key] = {
        'access_token': token_data['access_token'],
        'expires_at': time.time() + expires_in
    }

    return token_data['access_token']

async def _exchange_code_for_token(config, code: str):
    authorization_endpoint = config['token_request_endpoint_url']
    token_endpoint = authorization_endpoint.replace("/authorize", "/token")
    web_auth = config['token_request_params']

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": web_auth["redirect_uri"],
        "client_id": web_auth["client_id"],
    }

    if web_auth.get("client_secret"):
        data["client_secret"] = web_auth["client_secret"]

    async with httpx.AsyncClient(verify=config['verify_ssl']) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")

        return response.json()