#!/bin/bash
set -e

# Export env file
export ENV_FILE=.env.local

# Load the environment variables
set -a
source .env.local
set +a

# Ensure we're in the project root
cd "$(dirname "$0")/.."

# Stop and remove containers, networks, volumes, and images
echo "Cleaning up old containers and volumes..."
docker compose -f docker-compose.yml -f docker-compose.local.yml down -v

# Build and start the services
echo "Building and starting services..."
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build

echo "Services started successfully!"