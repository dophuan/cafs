FROM python:3.11-slim

# Install Node.js and npm
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    libpq-dev \
    gcc \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN pip install uv

# Copy backend dependency files
COPY ./backend/pyproject.toml /app/
COPY ./backend/poetry.lock /app/

# Install all backend dependencies using uv pip
RUN uv pip install --system .

# Copy the backend application
COPY ./backend /app

# Setup frontend
WORKDIR /app/frontend

# Copy frontend dependency files
COPY ./frontend/package*.json ./
COPY ./frontend/tsconfig*.json ./
COPY ./frontend/vite.config.ts ./
COPY ./frontend/.env* ./

# Install frontend dependencies
RUN npm ci

# Copy frontend source code
COPY ./frontend/src ./src
COPY ./frontend/public ./public
COPY ./frontend/index.html ./

# Build frontend
RUN npm run build

# Move back to main app directory
WORKDIR /app

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
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/utils/health-check/ || exit 1

# Start with 1 worker, enable proxy headers, and increase timeout
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--timeout-keep-alive", "75"]