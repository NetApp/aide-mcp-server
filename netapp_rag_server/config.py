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
    
    # List of paths to check for the .netapp credentials file
    credentials_paths = [
        '.netapp',
        os.path.expanduser('~/.netapp'),
        os.path.join(os.path.dirname(__file__), '.netapp')
    ]
    
    config = None

    # Tries to find and load the credentials file from one of the possible locations
    for path in credentials_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                config = json.load(f)
            break # Stops searching once file is found and loaded

    if not config:
        # If still none, the file is not found
        raise FileNotFoundError("Credentials file '.netapp' not found.")
    
    # List of top-level keys required in the config
    required_keys = [
        'rag_search_api_endpoint_url',
        'token_request_endpoint',
        'token_request_params',
        'verify_ssl'
    ]

    # Ensures all required top-level keys are present
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required key '{key}' in '.netapp' file.")

    return config # Returns thhe validated configuration dictionary