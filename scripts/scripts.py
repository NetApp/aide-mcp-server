import subprocess
import os

def setup_cache_dir():
    # gets cache directory from environment or uses default
    cache_dir = os.environ.get("UV_CACHE_DIR", os.path.expanduser("~/tmp/uv_cache"))

    # ensures the cache directory exists
    os.makedirs(cache_dir, exist_ok=True)
    
    return cache_dir

# Initializes cache directory when the module is imported
cache_dir = setup_cache_dir()

def server():

    subprocess.run(["uv", "run", "--cache-dir", cache_dir, "python3", "-m", "netapp_rag_server.main"], check=True)

def inspector():

    subprocess.run(["uv", "run", "--cache-dir", cache_dir, "npx", "@modelcontextprotocol/inspector", "python3", "-m", "netapp_rag_server.main"], check=True)