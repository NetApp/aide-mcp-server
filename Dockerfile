# Create a non-root user to run the application
RUN useradd --create-home --home-dir /app appuser

# Install dependencies
# We copy only the requirements file first to leverage Docker's cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code into the container
COPY netapp_rag_server/ ./netapp_rag_server/

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Command to run the application
# The server will be started when the container launches.
# The .netapp configuration file should be mounted at /app/.netapp
CMD ["python", "-m", "netapp_rag_server.main"]