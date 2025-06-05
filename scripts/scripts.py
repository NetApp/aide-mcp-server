import subprocess

def server():
    subprocess.run(["python3", "-m", "netapp_rag_server.main"], check=True)

def inspector():
    subprocess.run(["npx", "@modelcontextprotocol/inspector", "python3", "-m", "netapp_rag_server.main"], check=True)