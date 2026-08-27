import httpx

from app.config import get_settings

s = get_settings()
auth = (s.langfuse_public_key, s.langfuse_secret_key)
base = s.langfuse_host

r = httpx.get(f"{base}/api/public/traces", params={"page": 1, "limit": 10}, auth=auth, timeout=10)
print("traces:", r.status_code, "count:", len(r.json().get("data", [])))
for t in r.json().get("data", []):
    print(" -", t.get("id"), "|", t.get("name"), "| latency:", t.get("latency"))

run_traces = [t for t in r.json()["data"] if t.get("name") == "research_run" and t.get("id") != "run-9999"]
if run_traces:
    tid = run_traces[0]["id"]
    r2 = httpx.get(f"{base}/api/public/traces/{tid}", auth=auth, timeout=10)
    detail = r2.json()
    print()
    print("=== trace", tid, "===")
    print("input.task_id:", (detail.get("input") or {}).get("task_id"))
    print("output:", detail.get("output"))
    obs = detail.get("observations", [])
    print("observations:", len(obs))
    for o in obs:
        usage = o.get("usage") or {}
        print(
            f"  - [{o.get('type')}] {o.get('name')}"
            f" | {o.get('latency')} ms"
            f" | level={o.get('level')}"
            f" | model={o.get('model') or '-'}"
            f" | tokens={usage.get('totalTokens', '-')}"
        )
