# Copyright 2026 NetApp, Inc. All Rights Reserved.

import json
import os

def load_credentials():

    """

    Loads and validates the JSON configuration from the .netapp file

    Returns:
        dict: loaded configuration as a Python dictionary

    Raises:
        FileNotFoundError: If the .netapp file is not found in any expected location.
        ValueError: If required keys are missing from the configuration.

    """
    
    # Path to the .netapp credentials file in the user's home directory
    credentials_path = os.path.expanduser('~/.netapp')
    
    # If path not found, raise an error that .netapp file doesn't exist
    if not os.path.exists(credentials_path):
        raise FileNotFoundError("Credentials file '.netapp' not found in the user's home directory.")
    
    # Opens the file specified, reads its contents, parses the contents as JSON, and stores the resulting data
    with open(credentials_path, 'r') as f:
        config = json.load(f)
    
    # List of top-level keys required in the config
    required_keys = [
        'rag_search_api_endpoint_url',
        'verify_ssl'
    ]

    # Ensures all required top-level keys are present
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required key '{key}' in '.netapp' file.")

    if 'token_request_params' not in config:
        raise ValueError("Missing required key 'token_request_params' in '.netapp' file.")

    if not isinstance(config['token_request_params'], dict):
        raise ValueError("'token_request_params' must be a JSON object in '.netapp' file.")

    auth_flow = config.get('auth_flow')

    if not auth_flow:
        raise ValueError("Missing required key 'auth_flow' in '.netapp' file.")

    if auth_flow not in {'pkce', 'device_code'}:
        raise ValueError("'auth_flow' must be one of: pkce, device_code.")

    if 'token_request_endpoint_url' not in config:
        raise ValueError("Missing required key 'token_request_endpoint_url' in '.netapp' file.")

    if auth_flow == 'pkce':

        web_auth_required = [
            'client_id',
            'redirect_uri'
        ]

        for key in web_auth_required:
            if key not in config['token_request_params']:
                raise ValueError(f"Missing required key 'token_request_params.{key}' in '.netapp' file.")

        config['token_request_params'].setdefault('use_pkce', True)

    elif auth_flow == 'device_code':
        if 'device_code_endpoint_url' not in config:
            raise ValueError("Missing required key 'device_code_endpoint_url' in '.netapp' file.")

        device_required = [
            'client_id'
        ]

        for key in device_required:
            if key not in config['token_request_params']:
                raise ValueError(f"Missing required key 'token_request_params.{key}' in '.netapp' file.")

    return config # Returns the validated configuration dictionary