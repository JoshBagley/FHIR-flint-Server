#!/bin/bash
# Initial setup script
set -e

echo "Setting up PH-TS (Public Health Terminology Service)..."

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed. Aborting."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose is required but not installed. Aborting."; exit 1; }

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file from template"
fi

# Generate secure keys
SECRET_KEY=$(openssl rand -hex 32)
sed -i.bak "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
echo "Generated secure SECRET_KEY"

# Create data directories
mkdir -p data/backups data/exports data/uploads
chmod 755 data

echo "Setup complete!"
echo "Next steps:"
echo "  1. Edit .env with your configuration"
echo "  2. Run 'make start' to start all services"
echo "  3. Access the application at http://localhost"

