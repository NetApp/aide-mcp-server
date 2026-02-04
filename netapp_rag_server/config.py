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

    # Default web_based_auth to False if not provided
    if 'web_based_auth' not in config:
        config['web_based_auth'] = False

    if not isinstance(config['web_based_auth'], bool):
        raise ValueError("'web_based_auth' must be a boolean in '.netapp' file.")

    if 'token_request_endpoint_url' not in config:
        raise ValueError("Missing required key 'token_request_endpoint_url' in '.netapp' file.")

    if 'token_request_params' not in config:
        raise ValueError("Missing required key 'token_request_params' in '.netapp' file.")

    if not isinstance(config['token_request_params'], dict):
        raise ValueError("'token_request_params' must be a JSON object in '.netapp' file.")

    if config['web_based_auth']:
        # Web-based OAuth2/OIDC flow requirements
        web_auth_required = [
            'client_id',
            'redirect_uri'
        ]

        for key in web_auth_required:
            if key not in config['token_request_params']:
                raise ValueError(f"Missing required key 'token_request_params.{key}' in '.netapp' file.")

    else:
        # Non-web grant requirements
        if 'grant_type' not in config['token_request_params']:
            raise ValueError("Missing required key 'token_request_params.grant_type' in '.netapp' file.")

        grant_type = config['token_request_params']['grant_type']

        if grant_type == 'password':
            password_required = [
                'client_id',
                'client_secret',
                'scope',
                'username',
                'password'
            ]

            for key in password_required:
                if key not in config['token_request_params']:
                    raise ValueError(f"Missing required key 'token_request_params.{key}' in '.netapp' file.")

        elif grant_type == 'client_credentials':
            client_credentials_required = [
                'client_id',
                'client_secret',
                'scope'
            ]

            for key in client_credentials_required:
                if key not in config['token_request_params']:
                    raise ValueError(f"Missing required key 'token_request_params.{key}' in '.netapp' file.")

        else:
            raise ValueError("Unsupported grant_type. Use 'password' or 'client_credentials'.")

    return config # Returns the validated configuration dictionary