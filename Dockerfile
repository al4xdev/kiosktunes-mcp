# Multi-stage / lightweight container for Glama verification and MCP stdio execution
FROM python:3.12-slim

# Install mpv and system dependencies required for headless audio runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    mpv \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests first for optimal caching
COPY pyproject.toml uv.lock ./

# Install dependencies into project virtualenv
RUN uv sync --frozen --no-dev

# Copy application source code
COPY src ./src
COPY README.md LICENSE ./

# Run the MCP stdio server
ENTRYPOINT ["uv", "run", "kiosktunes-mcp"]
