#!/bin/bash
# Test Gemini agent endpoint
AGENT_ID="0ff4f2ee-936c-4f0d-85d1-f2aac6165a27"
API_URL="http://localhost:8000/api/v1/admin/agents/${AGENT_ID}/test"

echo "=== Testing agent via Gemini: ${AGENT_ID} ==="
echo ""

curl -s -X POST "${API_URL}" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what is your role in this company?"}' | python3 -m json.tool

echo ""
echo "=== Done ==="
