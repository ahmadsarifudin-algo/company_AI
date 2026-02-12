#!/bin/bash
# Quick test: find forecasting_agent and test it
AGENT_ID=$(curl -s http://localhost:8000/api/v1/admin/agents | python3 -c '
import json, sys
data = json.load(sys.stdin)
for a in data["agents"]:
    if "forecasting" in a["name"]:
        print(a["id"])
        break
')

echo "=== Testing forecasting_agent (ID: $AGENT_ID) ==="
echo ""

curl -s -X POST "http://localhost:8000/api/v1/admin/agents/$AGENT_ID/test" \
  -H "Content-Type: application/json" \
  -d '{"message": "Give me a 3-month cash flow projection for a small SaaS startup with $50k MRR"}' \
  | python3 -m json.tool
