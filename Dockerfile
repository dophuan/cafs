FROM python:3.11-slim as backend

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

# Copy backend dependency files
COPY ./backend/pyproject.toml /app/
COPY ./backend/poetry.lock /app/

# Install all dependencies using uv pip
RUN uv pip install --system .

# Copy the backend application
COPY ./backend /app

# Copy the Zalo verification file to a static directory
RUN mkdir -p /app/static
COPY zalo_verifierE8_WTUc2QoyViSuAciPh2tEnv1MVnp98DZ8t.html /app/static/

# Frontend build stage
FROM node:20 AS frontend-build

WORKDIR /app

COPY ./frontend/package*.json ./

RUN npm install

COPY ./frontend/ ./

# Create env file with API URL pointing to the same host
RUN echo "VITE_API_URL=http://localhost:8080" > .env

RUN npm run build

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install Nginx
RUN apt-get update && apt-get install -y \
    nginx \
    curl \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy backend from backend stage
COPY --from=backend /app /app
COPY --from=backend /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy frontend build from frontend stage
COPY --from=frontend-build /app/dist /usr/share/nginx/html

# Copy Nginx configuration
COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY ./frontend/nginx-backend-not-found.conf /etc/nginx/extra-conf.d/backend-not-found.conf

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

# Create startup script
RUN echo '#!/bin/bash\n\
nginx\n\
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1 --proxy-headers --timeout-keep-alive 75' > /app/start.sh && \
chmod +x /app/start.sh

CMD ["/app/start.sh"]