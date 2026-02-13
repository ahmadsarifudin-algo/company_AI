---
description: Start the local development environment (all services via Docker)
---

## Start Dev Environment (Docker)

Semua service berjalan di Docker via WSL. Tidak perlu install dependency lokal.

// turbo-all

1. Start all services via Docker Compose:
```
wsl -e bash -lc "docker compose -f /mnt/c/Users/sarif/Documents/project_antigravity/company_AI/docker-compose.yml up -d 2>&1"
```
Wait for all containers to show "Started" or "Running".

2. Verify services are running:
```
wsl -e bash -lc "docker compose -f /mnt/c/Users/sarif/Documents/project_antigravity/company_AI/docker-compose.yml ps 2>&1"
```
All 5 services should show "Up": db, redis, app, worker, frontend.

3. Test backend is responding:
```
wsl -e bash -lc "curl -s http://localhost:8000/ 2>/dev/null"
```
Should return JSON with system info.

4. Report the URLs to the user:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Stop Dev Environment

```
wsl -e bash -lc "docker compose -f /mnt/c/Users/sarif/Documents/project_antigravity/company_AI/docker-compose.yml down 2>&1"
```

## Rebuild After Dependency Changes

If `pyproject.toml` or `package.json` changed:
```
wsl -e bash -lc "docker compose -f /mnt/c/Users/sarif/Documents/project_antigravity/company_AI/docker-compose.yml up -d --build 2>&1"
```
