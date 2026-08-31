# Multi-stage Dockerfile for Nykaa AI Discovery Platform
FROM python:3.11-slim as base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and Docs
COPY . .

# Create data directories
RUN mkdir -p data/raw_db data/samples

# Expose port for FastAPI backend & web dashboard
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/overview || exit 1

# Default command: run FastAPI production server
CMD ["python", "-m", "src.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
