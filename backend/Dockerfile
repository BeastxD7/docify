FROM python:3.12-slim

WORKDIR /app

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (better layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev

# Copy source
COPY . .

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
