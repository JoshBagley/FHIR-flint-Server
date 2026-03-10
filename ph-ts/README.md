# PH-TS - Public Health Terminology Service

A high-performance FHIR R4 terminology server for public health vocabulary management.

## Features

- 🚀 Fast search with Elasticsearch
- 📊 Real-time analytics and reporting
- 🔄 Version control with git-style diffs
- 🤖 AI-powered semantic search
- 🗺️ Automated concept mapping
- 📱 Modern React web interface
- 🔐 Enterprise-grade security
- 📈 Horizontal scalability

## Quick Start

```bash
# Clone repository
git clone <repo-url>
cd ph-ts

# Copy environment file
cp .env.example .env

# Start all services
make start

# View logs
make logs

# Access services
# - API: http://localhost:8000
# - Web UI: http://localhost
# - API Docs: http://localhost:8000/docs
# - Grafana: http://localhost:3001
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Development Setup](docs/DEVELOPMENT.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [API Documentation](docs/API.md)
- [Migration Guide](docs/MIGRATION.md)

## Project Structure

See [Project Structure](docs/ARCHITECTURE.md#project-structure) for detailed information.

## License

MIT License - see LICENSE file for details.
