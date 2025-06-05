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
        'token_request_endpoint',
        'token_request_params',
        'verify_ssl'
    ]

    # Ensures all required top-level keys are present
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required key '{key}' in '.netapp' file.")

    return config # Returns thhe validated configuration dictionary