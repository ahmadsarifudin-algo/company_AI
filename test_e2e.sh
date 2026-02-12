#!/usr/bin/env bash
# End-to-end API test script for Multi-Agentic AI Enterprise OS
set -e

BASE="http://localhost:8000"
API="$BASE/api/v1"

echo "=========================================="
echo "  E2E Test: Multi-Agentic AI Enterprise OS"
echo "=========================================="

# 1. Health Check
echo ""
echo "=== 1. Health Check ==="
curl -s "$BASE/health" | python3 -m json.tool

# 2. Register User
echo ""
echo "=== 2. Register User ==="
REGISTER=$(curl -s -X POST "$API/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@company.ai",
    "password": "testpass123",
    "name": "Test User",
    "department": "engineering",
    "role": "admin"
  }')
echo "$REGISTER" | python3 -m json.tool 2>/dev/null || echo "$REGISTER"

# Extract token
TOKEN=$(echo "$REGISTER" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

if [ -z "$TOKEN" ]; then
  echo "Registration may have failed (user exists?). Trying login..."
  LOGIN=$(curl -s -X POST "$API/auth/login" \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test@company.ai",
      "password": "testpass123"
    }')
  echo "$LOGIN" | python3 -m json.tool 2>/dev/null || echo "$LOGIN"
  TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
fi

echo "TOKEN: ${TOKEN:0:20}..."
AUTH="Authorization: Bearer $TOKEN"

# 3. Create Agent
echo ""
echo "=== 3. Create Agent ==="
AGENT=$(curl -s -X POST "$API/agents" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{
    "name": "TechAgent-Alpha",
    "department": "engineering",
    "tier": "standard",
    "description": "A test engineering agent",
    "system_prompt": "You are an expert software engineer."
  }')
echo "$AGENT" | python3 -m json.tool 2>/dev/null || echo "$AGENT"
AGENT_ID=$(echo "$AGENT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

# 4. Create Task
echo ""
echo "=== 4. Create Task ==="
TASK=$(curl -s -X POST "$API/tasks" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d "{
    \"title\": \"Analyze API Performance\",
    \"description\": \"Review and optimize API response times\",
    \"department\": \"engineering\",
    \"priority\": \"P1\",
    \"assigned_agent_id\": \"$AGENT_ID\"
  }")
echo "$TASK" | python3 -m json.tool 2>/dev/null || echo "$TASK"

# 5. List Agents
echo ""
echo "=== 5. List Agents ==="
curl -s "$API/agents" | python3 -m json.tool 2>/dev/null

# 6. List Tasks
echo ""
echo "=== 6. List Tasks ==="
curl -s "$API/tasks" | python3 -m json.tool 2>/dev/null

# 7. Knowledge: Ingest Document
echo ""
echo "=== 7. Knowledge: Ingest Document ==="
INGEST=$(curl -s -X POST "$API/knowledge/ingest" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{
    "title": "Company Engineering Standards",
    "content": "Our engineering team follows strict coding standards. All code must have unit tests with at least 80% coverage. We use Python 3.11+ with type hints. Database migrations must be reversible. API endpoints must include OpenAPI documentation. Code reviews require at least two approvals. Performance budgets: API responses under 200ms, page loads under 3 seconds.",
    "department": "engineering",
    "doc_type": "policy",
    "source": "internal-wiki"
  }')
echo "$INGEST" | python3 -m json.tool 2>/dev/null || echo "$INGEST"

# 8. Knowledge: Search
echo ""
echo "=== 8. Knowledge: Search ==="
SEARCH=$(curl -s -X POST "$API/knowledge/search" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{
    "query": "What are the code review requirements?",
    "department": "engineering",
    "top_k": 3
  }')
echo "$SEARCH" | python3 -m json.tool 2>/dev/null || echo "$SEARCH"

# 9. Knowledge: List Documents
echo ""
echo "=== 9. Knowledge: List Documents ==="
curl -s "$API/knowledge/documents" \
  -H "$AUTH" | python3 -m json.tool 2>/dev/null

# 10. Agent Stats
echo ""
echo "=== 10. Agent Stats ==="
curl -s "$API/agents/stats/summary" | python3 -m json.tool 2>/dev/null

echo ""
echo "=========================================="
echo "  All tests completed!"
echo "=========================================="
