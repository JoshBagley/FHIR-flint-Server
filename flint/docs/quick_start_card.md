# Flint - Quick Start Reference Card

## ⚡ Ultra-Fast Setup (3 Commands)

```bash
# 1. Run automated setup
curl -sL https://raw.githubusercontent.com/your-org/flint/main/setup.sh | bash

# 2. Navigate and initialize
cd ph-ts && ./scripts/setup.sh

# 3. Start everything
make start
```

**⏱️ Total time: 5 minutes**

---

## 🎯 Essential Commands

| Command | Description |
|---------|-------------|
| `make start` | Start core services |
| `make start-obs` | Core + observability + Adminer |
| `make start-full` | All services including pgAdmin and Kibana |
| `make stop` | Stop all services |
| `make logs` | View real-time logs |
| `make clean` | Remove all data volumes (full reset) |
| `make restart` | Restart all services |

---

## 🌐 Access Points

| Service | URL | Available with |
|---------|-----|----------------|
| **Web UI** | http://localhost | `make start` |
| **API** | http://localhost:8000 | `make start` |
| **API Docs** | http://localhost:8000/docs | `make start` |
| **Adminer** | http://localhost:8181 | `make start-obs` |
| **Prometheus** | http://localhost:9090 | `make start-obs` |
| **Grafana** | http://localhost:3001 | `make start-obs` (admin/admin) |
| **pgAdmin** | http://localhost:5050 | `make start-full` |
| **Kibana** | http://localhost:5601 | `make start-full` |

---

## 🔍 Health Checks

```bash
# Quick health check
curl http://localhost:8000/health

# Check all services
docker compose ps

# View specific service logs
docker compose logs backend
docker compose logs postgres
```

---

## 🐛 Common Issues & Fixes

### Services won't start
```bash
# Check Docker is running
docker ps

# Restart Docker Desktop
# Then try again: make start
```

### Port already in use
```bash
# Find what's using port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill the process or change ports in docker-compose.yml
```

### Database connection errors
```bash
# Wait for database to be ready
docker compose logs postgres | grep "ready"

# Then restart backend
docker compose restart backend
```

### Out of memory
```bash
# Increase Docker memory allocation
# Docker Desktop → Settings → Resources → Memory → 8GB
```

---

## 📦 What Gets Installed?

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | Python/FastAPI | FHIR API server |
| Database | PostgreSQL | Data storage |
| Search | Elasticsearch | Fast search |
| Cache | Redis | Performance |
| Frontend | React/Vite | Web interface |
| Proxy | Nginx | Load balancer |

---

## 🔄 Development Workflow

### 1. Make code changes
```bash
# Backend: backend/app/main.py
# Frontend: frontend/src/main.jsx
```

### 2. See changes
- **Backend**: Auto-reloads (uvicorn --reload)
- **Frontend**: Auto-reloads (Vite HMR)

### 3. Test changes
```bash
# Backend
docker compose exec backend pytest

# Frontend  
docker compose exec frontend npm test
```

### 4. Commit
```bash
git add .
git commit -m "Your changes"
```

---

## 📊 Monitor Resources

```bash
# View resource usage
docker stats

# View logs
make logs

# Check disk space
docker system df
```

---

## 🛑 Shutdown Options

### Keep data (normal shutdown)
```bash
make stop
```

### Remove everything (fresh start)
```bash
make clean
```

### Restart specific service
```bash
docker compose restart backend
docker compose restart frontend
```

---

## 🔐 Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| PostgreSQL | flint | flint_dev_password |
| Grafana | admin | admin |
| pgAdmin | admin@example.com | admin |

**⚠️ Change these in production!**

---

## 📁 Project Structure

```
flint/
├── backend/          # Python FastAPI server
├── frontend/         # React web app
├── infrastructure/   # Docker, K8s configs
├── migration/        # Data migration tools
├── scripts/          # Utility scripts
└── docker-compose.yml
```

---

## 🎓 Next Steps

1. ✅ Load sample data: `python migration/migrate.py`
2. ✅ Explore API: http://localhost:8000/docs
3. ✅ Read docs: `docs/ARCHITECTURE.md`
4. ✅ Make changes: Edit files and see live reload
5. ✅ Deploy: `./scripts/deploy.sh`

---

## 🆘 Help Resources

- **Logs**: `make logs`
- **Docs**: http://localhost:8000/docs
- **GitHub**: https://github.com/your-org/ph-ts
- **Issues**: Open a GitHub issue

---

## 💡 Pro Tips

1. **Use make commands** - They're easier than docker-compose
2. **Check logs first** - Most issues show up in logs
3. **Wait for health checks** - Give services 60s to start
4. **Use tmux/screen** - Keep logs running in background
5. **Bookmark /docs** - Interactive API testing

---

## 🎯 Performance Tips

```bash
# Reduce log verbosity
# In .env: LOG_LEVEL=warning

# Reduce Elasticsearch memory
# In docker-compose.yml: ES_JAVA_OPTS=-Xms256m -Xmx256m

# Enable Redis persistence
# In docker-compose.yml: Add --appendonly yes
```

---

## 📞 Quick Support

**Something not working?**

1. `make logs` - Check what failed
2. `make status` - See service health
3. `make clean && make start` - Fresh start
4. Check troubleshooting guide in docs

---

## ✨ Features Available

- ✅ FHIR R4 API
- ✅ Fast search (Elasticsearch)
- ✅ Version control
- ✅ Concept mapping
- ✅ Analytics dashboard
- ✅ Real-time updates
- ✅ Multi-format export

**Everything runs locally with one command!** 🚀

---

**Print this card and keep it handy!** 📌
