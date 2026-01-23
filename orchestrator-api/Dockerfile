FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy orchestrator-api requirements
COPY orchestrator-api/requirements.txt /app/orchestrator-api/
RUN pip install --no-cache-dir -r /app/orchestrator-api/requirements.txt

# Copy orchestrator module (parent package)
COPY pyproject.toml /app/
COPY orchestrator/ /app/orchestrator/

# Install orchestrator package
RUN pip install --no-cache-dir -e .

# Copy orchestrator-api code
COPY orchestrator-api/ /app/orchestrator-api/

# Create projects directory
RUN mkdir -p /app/projects

EXPOSE 8090

ENV ORCHESTRATOR_API_PORT=8090
ENV PYTHONPATH=/app

CMD ["python", "-m", "orchestrator-api.main"]
