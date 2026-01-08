# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Install git for cloning repositories
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV HOME="/tmp"

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Make files readable/executable by any user (OpenShift uses random UIDs)
RUN chmod -R 755 /app && chmod -R 755 /opt/venv

# Create cache directory for Claude CLI (OpenShift runs with random UID)
RUN mkdir -p /tmp/.cache/claude-cli-nodejs && chmod -R 777 /tmp/.cache

WORKDIR /app/backend

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
