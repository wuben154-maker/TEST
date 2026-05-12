# Deep Agent Security Service Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create app directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/

# Copy skills directory (SKILL.md files for sub-agents)
COPY skills/ skills/

# Official subagent bundles (AGENT.md + skills/ layout; registry in config/)
COPY subagents/ subagents/

# Copy config directory (LABELS.md, EVENTS.md, subagents.registry.yaml)
COPY config/ config/

# Create non-root user
RUN useradd --create-home --shell /bin/bash agent && \
    chown -R agent:agent /app

USER agent

# Expose port
EXPOSE 9090

# Health check - increased start-period to allow app to fully start
HEALTHCHECK --interval=30s --timeout=30s --start-period=120s --retries=5 \
    CMD sh -c 'curl -f http://localhost:${PORT:-9090}/health || exit 1'

# Run the application
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9090}"]
