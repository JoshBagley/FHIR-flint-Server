# PH-TS Local Development Setup Guide

## 📋 Prerequisites (One-Time Setup)

### Required Software

1. **Docker Desktop** (Required)
   ```bash
   # Check if installed
   docker --version
   # Should show: Docker version 20.10.0 or higher
   
   docker-compose --version
   # Should show: Docker Compose version 2.0.0 or higher
   ```
   
   **If not installed:**
   - **macOS**: Download from https://www.docker.com/products/docker-desktop
   - **Windows**: Download from https://www.docker.com/products/docker-desktop
   - **Linux**: 
     ```bash
     curl -fsSL https://get.docker.com -o get-docker.sh
     sudo sh get-docker.sh
     sudo usermod -aG docker $USER
     # Log out and back in
     ```

2. **Git** (Required)
   ```bash
   git --version
   # Should show: git version 2.0 or higher
   ```
   
   **If not installed:**
   - **macOS**: `brew install git` or download from https://git-scm.com
   - **Windows**: Download from https://git-scm.com
   - **Linux**: `sudo apt-get install git` (Ubuntu/Debian)

3. **Python 3.11+** (Optional - for migration tool)
   ```bash
   python3 --version
   # Should show: Python 3.11.0 or higher
   ```

4. **Node.js 18+** (Optional - for frontend development)
   ```bash
   node --version
   # Should show: v18.0.0 or higher
   ```

---

## 🎯 Quick Start (5 Minutes)

### Option 1: Automated Setup (Recommended)

```bash
# Step 1: Download and run setup script
curl -O https://raw.githubusercontent.com/your-org/ph-ts/main/setup.sh
chmod +x setup.sh
./setup.sh

# Step 2: Navigate to project
cd ph-ts

# Step 3: Initialize environment
./scripts/setup.sh

# Step 4: Start all services
make start

# Step 5: Wait for services to be ready (~2 minutes)
# Watch the logs
make logs

# Step 6: Access the application
# Open http://localhost in your browser
```

### Option 2: Manual Setup

```bash
# Step 1: Create project directory
mkdir ph-ts
cd ph-ts

# Step 2: Create all necessary files (see detailed steps below)
# ... (continue with manual file creation)
```

---

## 📦 Detailed Setup Steps

### Step 1: Create Project Structure

```bash
# Create project directory
mkdir ph-ts
cd ph-ts

# Create main directories
mkdir -p backend/{app,tests} frontend/src infrastructure/{docker,kubernetes} migration scripts config data
```

### Step 2: Create Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: phts-postgres
    environment:
      POSTGRES_DB: phts
      POSTGRES_USER: phts
      POSTGRES_PASSWORD: phts_dev_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - phts-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U phts"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Elasticsearch for Search
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    container_name: phts-elasticsearch
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
      - xpack.security.enabled=false
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"
    networks:
      - phts-network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5

  # Redis for Caching
  redis:
    image: redis:7-alpine
    container_name: phts-redis
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    networks:
      - phts-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Backend FHIR Server
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: phts-backend
    depends_on:
      postgres:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://phts:phts_dev_password@postgres:5432/phts
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
      REDIS_URL: redis://redis:6379
      LOG_LEVEL: debug
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    networks:
      - phts-network
    restart: unless-stopped

  # Frontend Web UI
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    container_name: phts-frontend
    depends_on:
      - backend
    ports:
      - "3000:3000"
    volumes:
      - ./frontend/src:/app/src
    networks:
      - phts-network
    environment:
      - VITE_API_URL=http://localhost:8000
    restart: unless-stopped

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    container_name: phts-nginx
    depends_on:
      - backend
      - frontend
    ports:
      - "80:80"
    volumes:
      - ./infrastructure/docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    networks:
      - phts-network
    restart: unless-stopped

networks:
  phts-network:
    driver: bridge

volumes:
  postgres_data:
  elasticsearch_data:
  redis_data:
```

### Step 3: Create Backend Application

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

Create `backend/requirements.txt`:

```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
asyncpg==0.29.0
sqlalchemy==2.0.23
elasticsearch==8.11.0
redis==5.0.1
python-dotenv==1.0.0
```

Create `backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="PH-TS API",
    description="Public Health Terminology Service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "PH-TS",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/fhir/metadata")
async def metadata():
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "fhirVersion": "4.0.1",
        "format": ["json"]
    }
```

### Step 4: Create Frontend Application

Create `frontend/Dockerfile.dev`:

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

Create `frontend/package.json`:

```json
{
  "name": "ph-ts-frontend",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.1",
    "vite": "^5.0.8"
  }
}
```

Create `frontend/vite.config.js`:

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000
  }
})
```

Create `frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PH-TS - Public Health Terminology Service</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

Create `frontend/src/main.jsx`:

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'

function App() {
  return (
    <div style={{ padding: '2rem', fontFamily: 'system-ui' }}>
      <h1>PH-TS - Public Health Terminology Service</h1>
      <p>Welcome to the terminology server!</p>
      <div style={{ marginTop: '2rem' }}>
        <a href="http://localhost:8000/docs" target="_blank">
          API Documentation →
        </a>
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
```

### Step 5: Create Nginx Configuration

Create `infrastructure/docker/nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }

    upstream frontend {
        server frontend:3000;
    }

    server {
        listen 80;

        location /fhir/ {
            proxy_pass http://backend/fhir/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /docs {
            proxy_pass http://backend/docs;
            proxy_set_header Host $host;
        }

        location / {
            proxy_pass http://frontend/;
            proxy_set_header Host $host;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

### Step 6: Create Makefile

Create `Makefile`:

```makefile
.PHONY: start stop restart logs clean

start:
	@echo "Starting PH-TS services..."
	docker-compose up -d
	@echo "✓ Services started!"
	@echo ""
	@echo "Access points:"
	@echo "  - Web UI:      http://localhost"
	@echo "  - API:         http://localhost:8000"
	@echo "  - API Docs:    http://localhost:8000/docs"
	@echo ""
	@echo "Run 'make logs' to view logs"

stop:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	rm -rf data/*

status:
	docker-compose ps
```

### Step 7: Create Setup Script

Create `scripts/setup.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Setting up PH-TS..."

# Create .env if doesn't exist
if [ ! -f .env ]; then
    cat > .env << EOF
POSTGRES_PASSWORD=$(openssl rand -hex 16)
SECRET_KEY=$(openssl rand -hex 32)
EOF
    echo "✓ Created .env file"
fi

# Create data directories
mkdir -p data/{backups,exports,uploads}
echo "✓ Created data directories"

# Create backend __init__.py files
mkdir -p backend/app
touch backend/app/__init__.py
echo "✓ Created backend structure"

# Create frontend src directory
mkdir -p frontend/src
echo "✓ Created frontend structure"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Run 'make start' to start all services"
echo "  2. Wait ~60 seconds for services to initialize"
echo "  3. Open http://localhost in your browser"
```

```bash
chmod +x scripts/setup.sh
```

---

## 🚀 Running the Application

### Method 1: Using Make (Recommended)

```bash
# Start all services
make start

# View logs
make logs

# Check status
make status

# Stop services
make stop

# Clean up everything
make clean
```

### Method 2: Using Docker Compose Directly

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

---

## ✅ Verification Steps

### 1. Check All Services Are Running

```bash
docker-compose ps
```

You should see:
```
NAME                STATUS              PORTS
phts-backend        Up (healthy)        0.0.0.0:8000->8000/tcp
phts-frontend       Up                  0.0.0.0:3000->3000/tcp
phts-postgres       Up (healthy)        0.0.0.0:5432->5432/tcp
phts-elasticsearch  Up (healthy)        0.0.0.0:9200->9200/tcp
phts-redis          Up (healthy)        0.0.0.0:6379->6379/tcp
phts-nginx          Up                  0.0.0.0:80->80/tcp
```

### 2. Test Backend API

```bash
# Health check
curl http://localhost:8000/health

# Should return: {"status":"healthy"}

# FHIR metadata
curl http://localhost:8000/fhir/metadata
```

### 3. Test Frontend

Open your browser to:
- **Web UI**: http://localhost
- **API Docs**: http://localhost:8000/docs

### 4. Test Database Connection

```bash
docker-compose exec postgres psql -U phts -d phts -c "SELECT version();"
```

### 5. Test Elasticsearch

```bash
curl http://localhost:9200/_cluster/health?pretty
```

### 6. Test Redis

```bash
docker-compose exec redis redis-cli ping
# Should return: PONG
```

---

## 🐛 Troubleshooting

### Issue: Services Won't Start

```bash
# Check Docker is running
docker ps

# Check for port conflicts
lsof -i :80   # macOS/Linux
netstat -ano | findstr :80   # Windows

# View detailed logs
docker-compose logs backend
docker-compose logs postgres
```

### Issue: Database Connection Error

```bash
# Wait for PostgreSQL to be ready
docker-compose logs postgres | grep "ready to accept connections"

# Restart backend after database is ready
docker-compose restart backend
```

### Issue: "Permission Denied" Errors

```bash
# Fix permissions
chmod +x scripts/*.sh
sudo chown -R $USER:$USER .
```

### Issue: Port Already in Use

Edit `docker-compose.yml` and change ports:
```yaml
ports:
  - "8080:8000"  # Instead of 8000:8000
  - "3001:3000"  # Instead of 3000:3000
```

### Issue: Out of Memory

```bash
# Increase Docker memory
# Docker Desktop → Settings → Resources → Memory → 4GB+

# Reduce Elasticsearch memory
# In docker-compose.yml:
ES_JAVA_OPTS: "-Xms256m -Xmx256m"
```

---

## 📊 Monitoring

### View Real-time Logs

```bash
# All services
make logs

# Specific service
docker-compose logs -f backend
docker-compose logs -f postgres
```

### Resource Usage

```bash
# View resource consumption
docker stats

# View disk usage
docker system df
```

---

## 🔄 Development Workflow

### Making Code Changes

#### Backend Changes:
```bash
# Edit files in backend/app/
vim backend/app/main.py

# Backend auto-reloads (if using --reload flag)
# Or restart manually:
docker-compose restart backend
```

#### Frontend Changes:
```bash
# Edit files in frontend/src/
vim frontend/src/main.jsx

# Frontend auto-reloads via Vite HMR
```

### Running Tests

```bash
# Backend tests
docker-compose exec backend pytest tests/

# Frontend tests
docker-compose exec frontend npm test
```

### Database Migrations

```bash
# Create migration
docker-compose exec backend alembic revision -m "description"

# Run migrations
docker-compose exec backend alembic upgrade head
```

---

## 🛑 Stopping and Cleanup

### Stop Services (Keep Data)

```bash
make stop
# OR
docker-compose down
```

### Complete Cleanup (Remove All Data)

```bash
make clean
# OR
docker-compose down -v
rm -rf data/*
```

---

## 📚 Next Steps

Once running locally:

1. ✅ **Load Sample Data**: See [Migration Guide](MIGRATION.md)
2. ✅ **API Development**: See [API Documentation](API.md)
3. ✅ **Frontend Development**: See [Frontend Guide](FRONTEND.md)
4. ✅ **Deploy to Cloud**: See [Deployment Guide](DEPLOYMENT.md)

---

## 🆘 Getting Help

- **Check logs**: `make logs`
- **View status**: `make status`
- **GitHub Issues**: https://github.com/your-org/ph-ts/issues
- **Documentation**: http://localhost:8000/docs (when running)

---

## 📝 Summary Commands

```bash
# Quick reference
make start    # Start everything
make logs     # View logs
make status   # Check health
make stop     # Stop services
make clean    # Complete cleanup
```

**Total setup time**: ~10 minutes (first time)  
**Startup time**: ~60 seconds  
**Shutdown time**: ~10 seconds
