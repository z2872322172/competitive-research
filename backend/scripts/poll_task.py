import time

import httpx

base = "http://127.0.0.1:8000"
r = httpx.post(f"{base}/v1/auth/login", json={"username": "langfuse_probe", "password": "probe123456"}, timeout=15)
token = r.json()["token"]
h = {"Authorization": f"Bearer {token}"}

r = httpx.get(f"{base}/v1/research-tasks", headers=h, timeout=15)
tasks = r.json()
latest = max(tasks, key=lambda t: t["id"])
task_id = latest["id"]
print("task:", task_id, latest["status"])

status = latest["status"]
for i in range(60):
    time.sleep(6)
    r = httpx.get(f"{base}/v1/research-tasks/{task_id}", headers=h, timeout=15)
    body = r.json()
    status = body.get("task", {}).get("status") or body.get("status")
    print(f"poll {i}: {status}")
    if status in ("completed", "failed", "waiting_review"):
        break
print("FINAL:", status)
