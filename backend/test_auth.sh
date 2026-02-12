#!/usr/bin/env bash
# Test auth + protected endpoints
set -e

API="http://localhost:8000/api/v1"

echo "=== 1) Test: Unauthenticated → 401 ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API/admin/dashboard")
echo "GET /admin/dashboard without token: HTTP $STATUS"
if [ "$STATUS" == "401" ]; then echo "✅ PASS"; else echo "❌ FAIL"; fi

echo ""
echo "=== 2) Login as admin ==="
LOGIN=$(curl -s -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.ai","password":"admin123"}')
echo "Response: $LOGIN"

TOKEN=$(echo "$LOGIN" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("access_token","FAILED"))' 2>/dev/null || echo "FAILED")
if [ "$TOKEN" == "FAILED" ]; then
  echo "❌ Login FAILED"
  exit 1
fi
echo "✅ Got token: ${TOKEN:0:20}..."

echo ""
echo "=== 3) Test: Dashboard with token ==="
DASH=$(curl -s "$API/admin/dashboard" -H "Authorization: Bearer $TOKEN")
echo "$DASH" | python3 -m json.tool 2>/dev/null || echo "$DASH"

echo ""
echo "=== 4) Test: Traces list ==="
TRACES=$(curl -s "$API/admin/traces?limit=5" -H "Authorization: Bearer $TOKEN")
echo "$TRACES" | python3 -m json.tool 2>/dev/null || echo "$TRACES"

echo ""
echo "=== 5) Test: Agents list ==="
AGENTS=$(curl -s "$API/admin/agents" -H "Authorization: Bearer $TOKEN")
echo "$AGENTS" | python3 -m json.tool 2>/dev/null || echo "$AGENTS"

echo ""
echo "=== 6) Test: Approvals list ==="
APPROVALS=$(curl -s "$API/admin/approvals?limit=5" -H "Authorization: Bearer $TOKEN")
echo "$APPROVALS" | python3 -m json.tool 2>/dev/null || echo "$APPROVALS"

echo ""
echo "=== 7) Test: Users list (manager+ required) ==="
USERS=$(curl -s "$API/admin/users" -H "Authorization: Bearer $TOKEN")
echo "$USERS" | python3 -m json.tool 2>/dev/null || echo "$USERS"

echo ""
echo "=== ALL TESTS DONE ==="
