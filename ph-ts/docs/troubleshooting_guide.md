# PH-TS Troubleshooting Guide

## 🔍 Diagnostic Flowchart

```
START: Is PH-TS not working?
│
├─→ Can't run `make start`?
│   ├─→ Is Docker installed? → Install Docker Desktop
│   ├─→ Is Docker running? → Start Docker Desktop
│   └─→ Permission denied? → chmod +x scripts/*.sh
│
├─→ Services won't start?
│   ├─→ Check: docker-compose ps
│   │   ├─→ All "Up"? → Services are healthy ✓
│   │   └─→ "Exit" or "Restarting"? → Check logs below
│   │
│   └─→ Port conflict?
│       ├─→ Check: lsof -i :80 -i :8000 -i :5432
│       ├─→ Kill conflicting process
│       └─→ Or change ports in docker-compose.yml
│
├─→ Can't access http://localhost?
│   ├─→ Is nginx running? → docker-compose ps nginx
│   ├─→ Check nginx logs → docker-compose logs nginx
│   └─→ Try direct URLs:
│       ├─→ http://localhost:8000 (backend)
│       └─→ http://localhost:3000 (frontend)
│
├─→ Backend errors?
│   ├─→ Database connection failed?
│   │   ├─→ Is postgres healthy? → docker-compose ps postgres
│   │   ├─→ Wait 30s → docker-compose restart backend
│   │   └─→ Check password → Verify POSTGRES_PASSWORD in .env
│   │
│   ├─→ Elasticsearch connection failed?
│   │   ├─→ Is it healthy? → curl localhost:9200/_cluster/health
│   │   ├─→ Yellow/Red status? → Increase Docker memory to 4GB+
│   │   └─→ Restart: docker-compose restart elasticsearch
│   │
│   └─→ Redis connection failed?
│       ├─→ Is it running? → docker-compose exec redis redis-cli ping
│       └─→ Restart: docker-compose restart redis
│
├─→ Frontend errors?
│   ├─→ Blank page?
│   │   ├─→ Check console (F12) → Look for errors
│   │   ├─→ Check frontend logs → docker-compose logs frontend
│   │   └─→ Rebuild: docker-compose up -d --build frontend
│   │
│   └─→ API calls failing?
│       ├─→ Check CORS → Backend should allow localhost:3000
│       └─→ Check network tab → Verify API endpoint
│
└─→ Performance issues?
    ├─→ Slow startup?
    │   ├─→ First time? → Normal, pulling images takes time
    │   ├─→ Low memory? → Increase Docker memory allocation
    │   └─→ Check: docker stats → Look for high CPU/memory
    │
    └─→ Slow responses?
        ├─→ Check logs for errors
        ├─→ Check database connections
        └─→ Enable caching in Redis

SOLUTION FOUND? → Great! ✓
STILL STUCK? → See detailed guide below ↓
```

---

## 🔧 Detailed Troubleshooting

### Problem 1: `make start` fails

**Symptoms:**
```
make: docker-compose: Command not found
```

**Solution:**
```bash
# Install Docker Desktop
# macOS/Windows: Download from docker.com
# Linux:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

---

### Problem 2: Port conflicts

**Symptoms:**
```
Error: port is already allocated
```

**Diagnosis:**
```bash
# Find what's using the port
lsof -i :80        # macOS/Linux
lsof -i :8000
lsof -i :5432

# Windows
netstat -ano | findstr :80
netstat -ano | findstr :8000
```

**Solution A: Kill the process**
```bash
# macOS/Linux
kill -9 <PID>

# Windows
taskkill /PID <PID> /F
```

**Solution B: Change ports**
Edit `docker-compose.yml`:
```yaml
services:
  nginx:
    ports:
      - "8080:80"  # Changed from 80:80
  backend:
    ports:
      - "8001:8000"  # Changed from 8000:8000
```

---

### Problem 3: Database connection errors

**Symptoms:**
```
ERROR: connection to server failed
could not connect to database
```

**Check database health:**
```bash
docker-compose ps postgres
# Should show: Up (healthy)
```

**If not healthy:**
```bash
# View logs
docker-compose logs postgres

# Common issues:
# 1. Still initializing → Wait 30 seconds
# 2. Data directory corrupt → make clean && make start
# 3. Password mismatch → Check .env file
```

**Force restart:**
```bash
docker-compose stop postgres
docker-compose rm -f postgres
docker-compose up -d postgres

# Wait for "ready to accept connections"
docker-compose logs postgres | grep "ready"

# Then restart backend
docker-compose restart backend
```

---

### Problem 4: Elasticsearch issues

**Symptoms:**
```
Elasticsearch cluster is not healthy
Connection refused to elasticsearch:9200
```

**Check health:**
```bash
curl http://localhost:9200/_cluster/health?pretty
```

**Expected response:**
```json
{
  "status": "green" or "yellow"  # yellow is OK for single node
}
```

**If red or unreachable:**
```bash
# Check logs
docker-compose logs elasticsearch

# Common issues:
# 1. Out of memory → Increase Docker memory to 4GB+
# 2. Disk space → Check: docker system df
# 3. Java heap → Reduce ES_JAVA_OPTS in docker-compose.yml
```

**Fix memory issue:**
Edit `docker-compose.yml`:
```yaml
elasticsearch:
  environment:
    - "ES_JAVA_OPTS=-Xms256m -Xmx256m"  # Reduced from 512m
```

---

### Problem 5: Frontend blank page

**Symptoms:**
- Browser shows blank page
- Console shows errors

**Check:**
```bash
# 1. Is frontend running?
docker-compose ps frontend

# 2. Check logs
docker-compose logs frontend

# 3. Check browser console (F12)
```

**Common fixes:**
```bash
# Rebuild frontend
docker-compose up -d --build frontend

# Clear browser cache
# Ctrl+Shift+R (hard refresh)

# Check if API is accessible
curl http://localhost:8000/health
```

---

### Problem 6: Out of memory

**Symptoms:**
```
Elasticsearch: OutOfMemoryError
Container keeps restarting
docker stats shows 90%+ memory usage
```

**Solution:**
```bash
# 1. Increase Docker memory
# Docker Desktop → Settings → Resources → Memory
# Set to at least 8GB for full stack

# 2. Reduce individual service memory
# Edit docker-compose.yml:

elasticsearch:
  environment:
    - "ES_JAVA_OPTS=-Xms256m -Xmx256m"

# 3. Run minimal stack (no Elasticsearch)
docker-compose up -d postgres redis backend
```

---

### Problem 7: Permission denied errors

**Symptoms:**
```
bash: ./setup.sh: Permission denied
mkdir: cannot create directory: Permission denied
```

**Solution:**
```bash
# Make scripts executable
chmod +x scripts/*.sh

# Fix file ownership
sudo chown -R $USER:$USER .

# If on Linux with SELinux
sudo chcon -R -t container_file_t .
```

---

### Problem 8: Slow performance

**Symptoms:**
- Long startup times
- Slow API responses
- Browser lag

**Diagnosis:**
```bash
# Check resource usage
docker stats

# Check disk space
docker system df

# Check for errors
make logs | grep ERROR
```

**Solutions:**
```bash
# 1. Prune unused Docker resources
docker system prune -a

# 2. Optimize database
docker-compose exec postgres vacuumdb -U phts -d phts

# 3. Clear Redis cache
docker-compose exec redis redis-cli FLUSHALL

# 4. Restart everything
make restart
```

---

### Problem 9: Cannot connect to API

**Symptoms:**
```
Failed to fetch
Network error
CORS error
```

**Check:**
```bash
# 1. Is backend running?
docker-compose ps backend

# 2. Test directly
curl http://localhost:8000/health

# 3. Check CORS settings
docker-compose logs backend | grep CORS
```

**Fix CORS:**
Edit `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### Problem 10: Docker Desktop not starting

**macOS:**
```bash
# Reset Docker
rm -rf ~/Library/Containers/com.docker.docker
# Reinstall Docker Desktop
```

**Windows:**
```powershell
# Reset Docker
Get-Process "*docker*" | Stop-Process
# Restart Docker Desktop as Administrator
```

**Linux:**
```bash
# Restart Docker daemon
sudo systemctl restart docker

# If that fails
sudo systemctl status docker
# Check error messages
```

---

## 🚨 Emergency Recovery

### Complete reset (nuclear option)

```bash
# 1. Stop everything
docker-compose down -v

# 2. Remove all containers
docker container prune -f

# 3. Remove all volumes
docker volume prune -f

# 4. Remove all images (optional)
docker image prune -a -f

# 5. Remove project data
rm -rf data/*

# 6. Fresh start
./scripts/setup.sh
make start
```

---

## 📋 Health Check Checklist

Run these commands to verify everything:

```bash
# 1. Docker running?
docker ps
# ✓ Should show containers

# 2. All services up?
docker-compose ps
# ✓ All should show "Up" or "Up (healthy)"

# 3. Backend responding?
curl http://localhost:8000/health
# ✓ Should return: {"status":"healthy"}

# 4. Database accessible?
docker-compose exec postgres psql -U phts -d phts -c "SELECT 1"
# ✓ Should return: 1

# 5. Elasticsearch healthy?
curl http://localhost:9200/_cluster/health
# ✓ Should return: "status":"green" or "yellow"

# 6. Redis responding?
docker-compose exec redis redis-cli ping
# ✓ Should return: PONG

# 7. Frontend loading?
curl http://localhost:3000
# ✓ Should return HTML

# 8. Nginx routing?
curl http://localhost/fhir/metadata
# ✓ Should return JSON
```

---

## 📞 Getting Help

### Before asking for help, provide:

1. **Your environment:**
   ```bash
   docker --version
   docker-compose --version
   uname -a  # or OS version
   ```

2. **Service status:**
   ```bash
   docker-compose ps
   ```

3. **Relevant logs:**
   ```bash
   docker-compose logs backend > backend.log
   docker-compose logs postgres > postgres.log
   # Attach these files
   ```

4. **What you tried:**
   - List all troubleshooting steps attempted
   - Include any error messages

---

## 🎓 Prevention Tips

1. **Always use `make` commands** instead of raw docker commands
2. **Check logs immediately** if something seems wrong
3. **Wait for health checks** before accessing services
4. **Keep Docker Desktop updated** to latest version
5. **Allocate enough memory** (8GB recommended)
6. **Don't modify .env** while services are running
7. **Use `make clean`** before major updates

---

## ✅ Success Indicators

Your setup is working correctly when:

- ✅ `docker-compose ps` shows all services as "Up (healthy)"
- ✅ http://localhost loads without errors
- ✅ http://localhost:8000/docs shows API documentation
- ✅ `make logs` shows no ERROR messages
- ✅ Database queries work
- ✅ Search returns results
- ✅ No constant container restarts

**If all above are ✅, you're good to go!** 🎉
