# syntax=docker/dockerfile:1

# Official Playwright image — Python 3.11 + Chromium pre-installed
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

# Install Python dependencies first (layer cached unless pyproject.toml changes)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source
COPY src/ src/

# Tell the crawler it's running inside Docker (enables --no-sandbox for Chromium)
ENV DOCKER_ENV=1

# Default: print help. Override with the URL and flags you need.
CMD ["python", "-m", "src.main", "--help"]
