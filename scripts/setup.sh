#!/bin/bash

# Creates the cache directory
mkdir -p /tmp/$USER/.cache/uv

# Sets the UV_CACHE_DIR environment variable
export UV_CACHE_DIR=/tmp/$USER/.cache/uv

# Adds the environment variable to .bashrc if not already present
if ! grep -q "export UV_CACHE_DIR=/tmp/$USER/.cache/uv" ~/.bashrc; then
    echo 'export UV_CACHE_DIR=/tmp/$USER/.cache/uv' >> ~/.bashrc
fi

# Source .bashrc to apply changes
source ~/.bashrc

# Checks if requirements.txt exists, if not, create it from pyproject.toml
if [ ! -f requirements.txt ]; then
    echo "Generating requirements.txt from pyproject.toml..."
    pip-compile pyproject.toml --output-file requirements.txt
fi

# Installs the dependencies listed in requirements.txt
pip install -r requirements.txt

# Verifies the installation
pip list | grep fastmcp

echo "Setup complete. Please ensure the correct Python interpreter is selected in your environment."