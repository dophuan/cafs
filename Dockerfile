FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including PostgreSQL client
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy dependency files first
COPY ./backend/pyproject.toml /app/

# Install dependencies using uv pip
# Add --dev to install dev dependencies too, or remove if not needed in production
RUN uv pip install --system . && \
    uv pip install --system pytest mypy ruff pre-commit types-passlib coverage uvicorn

# Copy the rest of the application
COPY ./backend /app

# Copy the Zalo verification file to a static directory
RUN mkdir -p /app/static
COPY zalo_verifierE8_WTUc2QoyViSuAciPh2tEnv1MVnp98DZ8t.html /app/static/

# Set environment variables
ENV PORT=8080
ENV HOST=0.0.0.0
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Add default values for required settings
ENV PROJECT_NAME="Webhook Service"
ENV API_V1_STR="/api/v1"
ENV ENVIRONMENT="production"
ENV SENTRY_DSN=""
ENV CORS_ORIGINS="*"

# Create directory for Cloud SQL Unix socket
RUN mkdir -p /cloudsql

EXPOSE 8080

# Modify healthcheck to use proper health check endpoint and increase timeout
HEALTHCHECK --interval=30s --timeout=30s --start-period=5m --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/utils/health-check/ || exit 1

# Start with 1 worker, enable proxy headers, and increase timeout
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--timeout-keep-alive", "75", "--log-level", "info"]