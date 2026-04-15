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

# In-memory cache: access_token, refresh_token (optional), expires_at, issued_at, ttl_seconds
_token_cache: dict = {}

# Serialize refresh and interactive login per cache key so concurrent callers cannot issue duplicate refresh grants (refresh token rotation would invalidate the token after the first).
_refresh_locks: dict[str, asyncio.Lock] = {}
_refresh_locks_lock = asyncio.Lock()


async def _get_refresh_lock(cache_key: str) -> asyncio.Lock:
    async with _refresh_locks_lock:
        if cache_key not in _refresh_locks:
            _refresh_locks[cache_key] = asyncio.Lock()
        return _refresh_locks[cache_key]


# Cache keys that already logged the missing-refresh warning (avoids repeating the same log line).
_warned_no_refresh: set = set()


def _get_cache_key(config: dict) -> str:
    auth_flow = config.get("auth_flow")
    if auth_flow == "pkce":
        authorization_endpoint = config["token_request_endpoint_url"]
        web_auth = config["token_request_params"]
        client_id = web_auth.get("client_id") or ""
        return f"pkce:{client_id}:{authorization_endpoint}"
    if auth_flow == "device_code":
        token_endpoint = config["token_request_endpoint_url"]
        device_endpoint = config["device_code_endpoint_url"]
        device_auth = config["token_request_params"]
        client_id = device_auth.get("client_id") or ""
        return f"device_code:{client_id}:{token_endpoint}:{device_endpoint}"
    raise ValueError("auth_flow must be pkce or device_code.")


def _get_token_endpoint(config: dict) -> str:
    # Resolves the POST URL for authorization-code exchange and refresh_token grants.
    auth_flow = config["auth_flow"]
    if auth_flow == "pkce":
        authorization_endpoint = config["token_request_endpoint_url"]
        return config.get("token_exchange_endpoint_url") or authorization_endpoint.replace(
            "/authorize", "/token"
        )
    if auth_flow == "device_code":
        return config["token_request_endpoint_url"]
    raise ValueError("auth_flow must be pkce or device_code.")


def _store_token_response(cache_key: str, body: dict) -> None:
    # Writes token fields into the cache; keeps the previous refresh_token if the body omits it.
    raw_expires = body.get("expires_in", 3599)
    try:
        expires_in = int(raw_expires)
    except (TypeError, ValueError):
        logging.warning(
            "OAuth token response had invalid expires_in %r; using default 3599", raw_expires
        )
        expires_in = 3599

    access_token = body.get("access_token")
    if not access_token:
        raise ValueError("OAuth token response missing access_token")

    now = time.time()
    old = _token_cache.get(cache_key, {})
    new_refresh = body.get("refresh_token")
    refresh_token = new_refresh if new_refresh is not None else old.get("refresh_token")

    _token_cache[cache_key] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": now + expires_in,
        "issued_at": now,
        "ttl_seconds": expires_in,
    }

    if not refresh_token and cache_key not in _warned_no_refresh:
        logging.warning(
            "OAuth token response had no refresh_token; you will need to restart the "
            "server after the access token expires."
        )
        _warned_no_refresh.add(cache_key)


def _cached_access_valid(cache_key: str) -> bool:
    # True while the access token is not within five minutes of expiry.
    token_data = _token_cache.get(cache_key)
    if not token_data:
        return False
    return time.time() < token_data["expires_at"] - 300


async def _refresh_access_token(config: dict, cache_key: str, refresh_token: str) -> None:
    # POSTs grant_type=refresh_token and replaces cache contents from the JSON response.
    token_endpoint = _get_token_endpoint(config)
    params = config["token_request_params"]
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": params["client_id"],
    }
    if params.get("scope"):
        data["scope"] = params["scope"]
    if params.get("client_secret"):
        data["client_secret"] = params["client_secret"]

    async with httpx.AsyncClient(verify=config["verify_ssl"]) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        raise Exception(f"Token refresh failed: {response.status_code} - {response.text}")

    _store_token_response(cache_key, response.json())


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


def clear_token_cache() -> None:
    """Remove all cached tokens so the next ``get_access_token()`` call
    triggers a refresh or interactive re-authentication."""
    _token_cache.clear()


async def authenticate_eagerly(config: dict) -> None:
    """Runs interactive OAuth2 once so the token cache is populated before MCP serves requests."""
    await get_access_token(config)


def start_token_refresh_loop(config: dict) -> asyncio.Task:
    """Starts a background coroutine that refreshes the access token before it expires."""
    # Runs on the same asyncio loop as the MCP server; cancel when the transport stops.
    return asyncio.create_task(_token_refresh_background(config), name="oauth_token_refresh")


async def _token_refresh_background(config: dict) -> None:
    cache_key = _get_cache_key(config)
    try:
        while True:
            token_data = _token_cache.get(cache_key)
            if not token_data:
                # Cache empty until eager auth completes.
                await asyncio.sleep(30)
                continue

            if not token_data.get("refresh_token"):
                # IdP did not issue a refresh token; nothing to renew until the next login.
                await asyncio.sleep(30)
                continue

            ttl = int(token_data.get("ttl_seconds", 3600))
            delay = max(30, int(0.8 * ttl))
            issued_at = float(token_data.get("issued_at", time.time()))
            next_refresh_at = issued_at + delay
            sleep_for = max(0.0, next_refresh_at - time.time())
            issued_at_before_sleep = issued_at
            # Sleep until ~80% of the access token lifetime (at least 30s after issue), then
            # re-read the cache under the lock and compare issued_at to issued_at_before_sleep.
            await asyncio.sleep(sleep_for)

            refresh_err: Exception | None = None
            lock = await _get_refresh_lock(cache_key)
            async with lock:
                token_data = _token_cache.get(cache_key)
                if not token_data or not token_data.get("refresh_token"):
                    continue
                if float(token_data.get("issued_at", 0)) > issued_at_before_sleep:
                    # Token already renewed during the wait.
                    continue
                try:
                    await _refresh_access_token(config, cache_key, token_data["refresh_token"])
                    logging.info("OAuth access token refreshed in the background.")
                except Exception as e:
                    logging.error("Background token refresh failed: %s", e)
                    refresh_err = e
            if refresh_err is not None:
                # Wait before the next background refresh attempt.
                await asyncio.sleep(30)


async def get_access_token(config: dict) -> str:
    """Returns a valid access token from cache, refresh, or interactive login."""
    auth_flow = config.get("auth_flow")
    if not auth_flow:
        raise Exception("Missing required auth_flow. Use 'pkce' or 'device_code'.")
    if auth_flow not in {"pkce", "device_code"}:
        raise Exception("Unsupported auth_flow. Use 'pkce' or 'device_code'.")

    cache_key = _get_cache_key(config)

    # Return immediately if the cached access token is still valid.
    if _cached_access_valid(cache_key):
        return _token_cache[cache_key]["access_token"]

    lock = await _get_refresh_lock(cache_key)
    async with lock:
        # Re-check cache after acquiring the lock.
        if _cached_access_valid(cache_key):
            return _token_cache[cache_key]["access_token"]

        td = _token_cache.get(cache_key)
        if td and td.get("refresh_token"):
            try:
                # Avoid browser or device-code login when a refresh_token can extend the session.
                await _refresh_access_token(config, cache_key, td["refresh_token"])
                return _token_cache[cache_key]["access_token"]
            except Exception as e:
                logging.warning("OAuth refresh failed (%s); starting interactive login.", e)
                del _token_cache[cache_key]

        elif td:
            # Drop expired cache rows that have no refresh_token so interactive login runs cleanly.
            del _token_cache[cache_key]

        # Browser redirect (PKCE) or device-code polling; both end in _store_token_response.
        if auth_flow == "pkce":
            return await _pkce_interactive_login(config, cache_key)
        return await _device_code_interactive_login(config, cache_key)


async def _pkce_interactive_login(config: dict, cache_key: str) -> str:
    # Authorization code + PKCE: open the browser, wait for redirect, exchange code for tokens.
    authorization_endpoint = config["token_request_endpoint_url"]
    web_auth = config["token_request_params"]

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
    _store_token_response(cache_key, token_data)
    return token_data["access_token"]


async def _exchange_code_for_token(config: dict, code: str, code_verifier: str | None = None):
    authorization_endpoint = config["token_request_endpoint_url"]
    token_endpoint = config.get("token_exchange_endpoint_url") or authorization_endpoint.replace(
        "/authorize", "/token"
    )
    web_auth = config["token_request_params"]

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

    async with httpx.AsyncClient(verify=config["verify_ssl"]) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")

        return response.json()


def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")


async def _device_code_interactive_login(config: dict, cache_key: str) -> str:
    # RFC 8628: show user code / verification URI, poll the token endpoint until authorized.
    token_endpoint = config["token_request_endpoint_url"]
    device_endpoint = config["device_code_endpoint_url"]
    device_auth = config["token_request_params"]

    data = {"client_id": device_auth["client_id"]}

    if device_auth.get("scope"):
        data["scope"] = device_auth["scope"]

    async with httpx.AsyncClient(verify=config["verify_ssl"]) as client:
        response = await client.post(
            device_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
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
            "client_id": device_auth["client_id"],
        }

        if device_auth.get("client_secret"):
            token_request["client_secret"] = device_auth["client_secret"]

        async with httpx.AsyncClient(verify=config["verify_ssl"]) as client:
            response = await client.post(
                token_endpoint,
                data=token_request,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code == 200:
            token_data = response.json()
            _store_token_response(cache_key, token_data)
            return token_data["access_token"]

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
