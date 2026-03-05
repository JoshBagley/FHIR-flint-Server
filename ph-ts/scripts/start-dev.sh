#!/bin/bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
echo "Development environment started"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "API Docs: http://localhost:8000/docs"

