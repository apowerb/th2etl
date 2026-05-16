# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Install uv, the Python package installer
RUN pip install uv

# Create a virtual environment
RUN uv venv

# Add the virtual environment to the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy the dependency definition files
COPY pyproject.toml ./

# Install project dependencies into the virtual environment
# --no-cache is used to keep the image size small
RUN uv pip sync --no-cache pyproject.toml

# Copy the rest of the application source code
COPY ./src ./src
COPY ./datasets ./datasets

# Expose the port the app runs on
EXPOSE 8000

# Set default environment variables
# These can be overridden at runtime
ENV DATABASE_HOST="db"
ENV DATABASE_PORT="5432"

# The command to run the API server
# The host is set to 0.0.0.0 to allow external connections
CMD ["uv", "run", "th2etl", "--serve-api", "--host", "0.0.0.0", "--port", "8000"]
