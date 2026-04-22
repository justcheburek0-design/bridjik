FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build stage
FROM base AS build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy all files needed for installation
COPY . .

# Install dependencies
RUN pip install --no-cache-dir \
    aiogram==3.22.0 \
    httpx==0.28.1 \
    openai>=2.0 \
    python-dotenv==1.1.1 \
    nextcord==2.6.0 \
    google-generativeai==0.8.5 \
    rlottie-python==1.3.8 \
    Pillow==11.2.1 \
    edge-tts==7.2.3 \
    aiohttp==3.11.11 \
    pydantic-settings>=2.13 \
    tenacity>=9.0 \
    structlog>=25.0 \
    cachetools>=6.0 \
    msgspec>=0.20 \
    bleach>=6.0 \
    markdown-it-py>=3.0 \
    pydantic-ai>=0.0.49

# Production stage
FROM base AS production

# Copy installed packages from build stage
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data photos voices

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port for health check
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
