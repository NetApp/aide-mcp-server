import time
import asyncio
import base64
import hashlib
import http.server
import logging
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

    auth_flow = config.get("auth_flow")

    if not auth_flow:
        raise Exception("Missing required auth_flow. Use 'pkce' or 'device_code'.")

    if auth_flow == "pkce":
        return await _get_access_token_web_based(config)

    if auth_flow == "device_code":
        return await _get_access_token_device_code(config)

    raise Exception("Unsupported auth_flow. Use 'pkce' or 'device_code'.")

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

    use_pkce = bool(web_auth.get("use_pkce")) or config.get("auth_flow") == "pkce"
    code_verifier = None

    if use_pkce:
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)
        auth_params["code_challenge"] = code_challenge
        auth_params["code_challenge_method"] = web_auth.get("code_challenge_method", "S256")

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

    token_data = await _exchange_code_for_token(config, code, code_verifier)

    expires_in = token_data.get('expires_in', 3599)
    _token_cache[cache_key] = {
        'access_token': token_data['access_token'],
        'expires_at': time.time() + expires_in
    }

    return token_data['access_token']

async def _exchange_code_for_token(config, code: str, code_verifier: str | None = None):
    authorization_endpoint = config['token_request_endpoint_url']
    token_endpoint = config.get('token_exchange_endpoint_url') or authorization_endpoint.replace("/authorize", "/token")
    web_auth = config['token_request_params']

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": web_auth["redirect_uri"],
        "client_id": web_auth["client_id"],
    }

    if web_auth.get("scope"):
        data["scope"] = web_auth["scope"]

    if web_auth.get("client_secret"):
        data["client_secret"] = web_auth["client_secret"]

    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient(verify=config['verify_ssl']) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")

        return response.json()

def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)

def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")

async def _get_access_token_device_code(config):
    token_endpoint = config['token_request_endpoint_url']
    device_endpoint = config['device_code_endpoint_url']
    device_auth = config['token_request_params']

    cache_key = f"token_{hash((token_endpoint, device_endpoint, device_auth.get('client_id'), 'device_code'))}"

    if cache_key in _token_cache:
        token_data = _token_cache[cache_key]
        if time.time() < token_data['expires_at'] - 300:
            return token_data['access_token']

    data = {
        "client_id": device_auth["client_id"]
    }

    if device_auth.get("scope"):
        data["scope"] = device_auth["scope"]

    async with httpx.AsyncClient(verify=config['verify_ssl']) as client:
        response = await client.post(
            device_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            raise Exception(f"Device code request failed: {response.status_code} - {response.text}")

        device_data = response.json()

    device_code = device_data.get("device_code")
    user_code = device_data.get("user_code")
    verification_uri = device_data.get("verification_uri")
    verification_uri_complete = device_data.get("verification_uri_complete")
    expires_in = device_data.get("expires_in", 900)
    interval = int(device_data.get("interval", 5))

    if not device_code or not (verification_uri or verification_uri_complete):
        raise Exception("Device code response missing required fields.")

    if verification_uri_complete:
        logging.info("Opening verification URL in browser...")
        webbrowser.open(verification_uri_complete)
    else:
        logging.info("Open the verification URL and enter the user code.")
        logging.info(f"Verification URL: {verification_uri}")
        if user_code:
            logging.info(f"User code: {user_code}")
        webbrowser.open(verification_uri)

    start_time = time.time()

    while time.time() < start_time + expires_in:
        await asyncio.sleep(interval)

        token_request = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": device_auth["client_id"]
        }

        if device_auth.get("client_secret"):
            token_request["client_secret"] = device_auth["client_secret"]

        async with httpx.AsyncClient(verify=config['verify_ssl']) as client:
            response = await client.post(
                token_endpoint,
                data=token_request,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

        if response.status_code == 200:
            token_data = response.json()
            expires_in_token = token_data.get('expires_in', 3599)
            _token_cache[cache_key] = {
                'access_token': token_data['access_token'],
                'expires_at': time.time() + expires_in_token
            }
            return token_data['access_token']

        try:
            error_data = response.json()
        except Exception:
            raise Exception(f"Device token polling failed: {response.status_code} - {response.text}")

        error = error_data.get("error")

        if error == "authorization_pending":
            continue

        if error == "slow_down":
            interval += 5
            continue

        if error in {"access_denied", "expired_token"}:
            raise Exception(f"Device code flow failed: {error}")

        raise Exception(f"Device token polling failed: {error_data}")

    raise TimeoutError("Device code authorization timed out.")