"""Quick E2E test — run inside Docker container."""
import asyncio
import httpx
import json
import traceback

BASE = "http://localhost:8000"
API = f"{BASE}/api/v1"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        # 1. Health
        print("=== 1. Health ===")
        r = await client.get("/health")
        print(json.dumps(r.json(), indent=2))

        # 2. Register or Login
        print("\n=== 2. Register ===")
        r = await client.post(f"{API}/auth/register", json={
            "email": "admin2@company.ai",
            "password": "SecurePass123",
            "name": "Admin User",
            "department": "engineering",
            "role": "admin",
        })
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type')}")
        print(f"Body length: {len(r.content)}")
        print(f"Body: {r.text[:500]}")
        
        token = None
        try:
            data = r.json()
            token = data.get("access_token")
        except Exception as e:
            print(f"JSON parse failed: {e}")

        if not token and r.status_code == 400:
            # User exists, try login
            print("\n=== 2b. Login ===")
            r = await client.post(f"{API}/auth/login", json={
                "email": "admin2@company.ai",
                "password": "SecurePass123",
            })
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:500]}")
            try:
                data = r.json()
                token = data.get("access_token")
            except Exception as e:
                print(f"JSON parse failed: {e}")

        if not token:
            print("ERROR: Could not get auth token!")
            return

        headers = {"Authorization": f"Bearer {token}"}
        print(f"Token obtained: {token[:25]}...")

        # 3. Create Agent
        print("\n=== 3. Create Agent ===")
        r = await client.post(f"{API}/agents", json={
            "name": "TechAgent-Beta",
            "department": "engineering",
            "tier": "standard",
            "description": "A test engineering agent",
            "system_prompt": "You are an expert software engineer.",
        }, headers=headers)
        print(f"Status: {r.status_code}")
        print(r.text[:300])
        agent_data = r.json()
        agent_id = agent_data.get("id", "")

        # 4. Create Task
        print("\n=== 4. Create Task ===")
        r = await client.post(f"{API}/tasks", json={
            "title": "Analyze API Performance",
            "description": "Review and optimize API response times",
            "department": "engineering",
            "priority": "P1",
            "assigned_agent_id": agent_id,
        }, headers=headers)
        print(f"Status: {r.status_code}")
        print(r.text[:300])

        # 5. List Agents
        print("\n=== 5. List Agents ===")
        r = await client.get(f"{API}/agents")
        agents = r.json()
        print(f"Status: {r.status_code}, Count: {len(agents)}")
        for a in agents:
            print(f"  - {a['name']} ({a['department']}/{a['tier']})")

        # 6. List Tasks
        print("\n=== 6. List Tasks ===")
        r = await client.get(f"{API}/tasks")
        tasks = r.json()
        print(f"Status: {r.status_code}, Count: {len(tasks)}")
        for t in tasks:
            print(f"  - {t['title']} [{t['status']}]")

        # 7. Knowledge: Ingest Document
        print("\n=== 7. Knowledge: Ingest ===")
        r = await client.post(f"{API}/knowledge/ingest", json={
            "title": "Company Engineering Standards",
            "content": (
                "Our engineering team follows strict coding standards. "
                "All code must have unit tests with at least 80% coverage. "
                "We use Python 3.11+ with type hints. "
                "Database migrations must be reversible. "
                "API endpoints must include OpenAPI documentation. "
                "Code reviews require at least two approvals. "
                "Performance budgets: API responses under 200ms, "
                "page loads under 3 seconds. "
                "Security reviews are mandatory for all external-facing services."
            ),
            "department": "engineering",
            "doc_type": "policy",
            "source": "internal-wiki",
        }, headers=headers)
        print(f"Status: {r.status_code}")
        print(r.text[:500])

        # 8. Knowledge: Search (only if ingest succeeded)
        if r.status_code == 200:
            print("\n=== 8. Knowledge: Search ===")
            r = await client.post(f"{API}/knowledge/search", json={
                "query": "What are the code review requirements?",
                "department": "engineering",
                "top_k": 3,
            }, headers=headers)
            print(f"Status: {r.status_code}")
            print(r.text[:500])
        else:
            print("\n=== 8. Knowledge: Search (skipped - ingest failed) ===")

        # 9. Knowledge: List Documents
        print("\n=== 9. Knowledge: List Documents ===")
        r = await client.get(f"{API}/knowledge/documents", headers=headers)
        print(f"Status: {r.status_code}")
        print(r.text[:300])

        # 10. Agent Stats
        print("\n=== 10. Agent Stats ===")
        r = await client.get(f"{API}/agents/stats/summary")
        print(f"Status: {r.status_code}")
        print(json.dumps(r.json(), indent=2))

    print("\n==========================================")
    print("  All E2E tests completed!")
    print("==========================================")


if __name__ == "__main__":
    asyncio.run(main())
