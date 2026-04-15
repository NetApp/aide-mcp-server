# Copyright 2026 NetApp, Inc. All Rights Reserved.

# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Set the home directory to the /config directory where the .netapp file is mounted.
ENV HOME=/config \
    PATH="/usr/local/bin:$PATH" 

# Create a non-root user to run the application
# Pick a deterministic, safe UID/GID like 10000
ARG APP_UID=10000
ARG APP_GID=10000

RUN groupadd --gid ${APP_GID} appgroup && \
    useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --home-dir /app appuser

# Copy the application source code into the container and install dependencies
COPY pyproject.toml .
COPY README.md .
COPY netapp_rag_server/ ./netapp_rag_server/
RUN pip install --no-cache-dir uv && \
    uv pip install --system .

# Create the config directory
RUN mkdir -p /config

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appgroup /app /usr/local/lib/python*/site-packages/ /config

# Switch to the non-root user
USER appuser

# Command to run the application
# The server will be started when the container launches.
# A volume containing the .netapp configuration file should be mounted at /config
CMD ["python", "-m", "netapp_rag_server.main"]