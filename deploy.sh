#!/usr/bin/env bash
# ============================================
# Company AI — One-Command Deploy Script
# Run from WSL: bash deploy.sh [--fresh]
# ============================================
set -e

# ── Config ─────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
FRONTEND_DIR="$PROJECT_DIR/frontend"
API_URL="http://localhost:8000"
ADMIN_EMAIL="admin@company.ai"
ADMIN_PASSWORD="admin123"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# ── Helper ─────────────────────────────────
info()  { echo -e "${CYAN}ℹ️  $1${NC}"; }
ok()    { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail()  { echo -e "${RED}❌ $1${NC}"; }
header(){ echo -e "\n${BOLD}═══ $1 ═══${NC}"; }

# ── Parse Args ─────────────────────────────
FRESH=false
for arg in "$@"; do
  case "$arg" in
    --fresh) FRESH=true ;;
  esac
done

# ── Step 1: Stop existing containers ───────
header "Step 1/5: Stopping existing containers"
if sudo docker compose -f "$COMPOSE_FILE" ps -q 2>/dev/null | grep -q .; then
  sudo docker compose -f "$COMPOSE_FILE" down
  ok "Containers stopped"
else
  info "No running containers found"
fi

# Fresh install: also remove volumes
if [ "$FRESH" = true ]; then
  warn "Fresh mode: removing Docker volumes (database will be reset)"
  sudo docker compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true
  ok "Volumes removed"
fi

# ── Step 2: Build & Start ──────────────────
header "Step 2/5: Building and starting Docker stack"
sudo docker compose -f "$COMPOSE_FILE" up -d --build
ok "Docker stack started"

# ── Step 3: Wait for health ────────────────
header "Step 3/5: Waiting for services to be healthy"
MAX_WAIT=60
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
  DB_HEALTHY=$(sudo docker inspect --format='{{.State.Health.Status}}' company_ai_db 2>/dev/null || echo "unhealthy")
  REDIS_HEALTHY=$(sudo docker inspect --format='{{.State.Health.Status}}' company_ai_redis 2>/dev/null || echo "unhealthy")
  APP_RUNNING=$(sudo docker inspect --format='{{.State.Status}}' company_ai_app 2>/dev/null || echo "not running")

  if [ "$DB_HEALTHY" = "healthy" ] && [ "$REDIS_HEALTHY" = "healthy" ] && [ "$APP_RUNNING" = "running" ]; then
    break
  fi

  sleep 2
  ELAPSED=$((ELAPSED + 2))
  echo -ne "\r  Waiting... ${ELAPSED}s (db=$DB_HEALTHY redis=$REDIS_HEALTHY app=$APP_RUNNING)   "
done
echo ""

if [ $ELAPSED -ge $MAX_WAIT ]; then
  fail "Services did not become healthy within ${MAX_WAIT}s"
  sudo docker compose -f "$COMPOSE_FILE" logs --tail 20
  exit 1
fi
ok "All services healthy"

# Wait a bit more for app startup (seed, tool registration, etc.)
info "Waiting 5s for app initialization..."
sleep 5

# ── Step 4: Show seed logs ─────────────────
header "Step 4/5: App startup logs"
echo "---"
sudo docker logs company_ai_app --tail 20 2>&1 | grep -E "✅|ℹ️|⚠️|🚀|🌱|ERROR|error|Traceback" || true
echo "---"

# ── Step 5: Test login ─────────────────────
header "Step 5/5: Testing login API"

LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" 2>&1)

# Check if response contains access_token
if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
  ok "Login test: PASSED"

  # Extract token and test /auth/me
  TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
  if [ -n "$TOKEN" ]; then
    ME_RESPONSE=$(curl -s "$API_URL/api/v1/auth/me" \
      -H "Authorization: Bearer $TOKEN" 2>&1)
    if echo "$ME_RESPONSE" | grep -q "$ADMIN_EMAIL"; then
      ok "Session validation (/auth/me): PASSED"
    else
      warn "Session validation: unexpected response"
      echo "  $ME_RESPONSE"
    fi
  fi
else
  fail "Login test: FAILED"
  echo "  Response: $LOGIN_RESPONSE"
  echo ""
  warn "Checking app logs for errors..."
  sudo docker logs company_ai_app --tail 30 2>&1 | tail -15
  exit 1
fi

# ── Summary ────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         🚀 Company AI — Ready!               ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║${NC}  Backend API:  ${CYAN}http://localhost:8000${NC}          ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}  API Docs:     ${CYAN}http://localhost:8000/docs${NC}     ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}  Frontend:     ${CYAN}http://localhost:3000${NC}          ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}                                              ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}  Admin Login:                                ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}    Email:    ${GREEN}admin@company.ai${NC}               ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}    Password: ${GREEN}admin123${NC}                       ${BOLD}║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║${NC}  ${YELLOW}Start frontend separately:${NC}                  ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}    cd frontend && npm run dev                ${BOLD}║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
