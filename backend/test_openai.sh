#!/bin/bash
# Test OpenAI API key directly
curl -s https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Say hi in one word"}], "max_tokens": 10}' | python3 -m json.tool
