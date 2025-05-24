#!/bin/bash
set -e

# Export env file
export ENV_FILE=.env.prod

# Load the environment variables
set -a
source .env.prod
set +a

# Ensure we're in the project root
cd "$(dirname "$0")/.."

# Stop and remove containers
echo "Cleaning up old containers..."
docker compose -f docker-compose.yml down

# Build and start the services
echo "Building and starting services..."
docker compose -f docker-compose.yml up -d --build

echo "Services started successfully!"