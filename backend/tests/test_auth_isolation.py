"""P7-42 鉴权与用户隔离验收测试（AUTH_MODE_OVERRIDE=strict）。

覆盖：
- 注册 / 登录 / 令牌校验（401/403/409 语义）
- strict 模式下无令牌访问被拒
- 工作区成员关系隔离：A 的任务对 B（不同工作区）完全不可见（404，不泄露存在性）
- 同工作区成员可见
- 任务归属由登录态决定（created_by 强制为 username，不可伪造）
"""

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture(autouse=True)
def strict_auth(monkeypatch):
    monkeypatch.setenv("AUTH_MODE_OVERRIDE", "strict")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    init_db()
    yield
    monkeypatch.delenv("AUTH_MODE_OVERRIDE", raising=False)


def register(client: TestClient, username: str, password: str = "secret-pass-123", workspace_id: str | None = None):
    payload = {"username": username, "password": password}
    if workspace_id:
        payload["workspace_id"] = workspace_id
    return client.post("/v1/auth/register", json=payload)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_task(client: TestClient, token: str, title: str = "隔离验证任务") -> dict:
    response = client.post(
        "/v1/research-tasks",
        json={"prompt": f"调研 {title} 的定价与功能差异", "title": title},
        headers=bearer(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_issues_token_and_default_workspace():
    with TestClient(app) as client:
        response = register(client, "alice")
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["token"]
        assert body["token_type"] == "bearer"
        assert body["user"]["username"] == "alice"
        assert body["user"]["workspaces"] == [{"workspace_id": "alice-default", "role": "owner"}]


def test_register_duplicate_username_rejected():
    with TestClient(app) as client:
        assert register(client, "bob").status_code == 201
        response = register(client, "bob")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "username_taken"


def test_login_validates_credentials():
    with TestClient(app) as client:
        register(client, "carol")
        ok = client.post("/v1/auth/login", json={"username": "carol", "password": "secret-pass-123"})
        assert ok.status_code == 200
        assert ok.json()["token"]
        bad = client.post("/v1/auth/login", json={"username": "carol", "password": "wrong-pass-xxx"})
        assert bad.status_code == 401
        assert bad.json()["error"]["code"] == "invalid_credentials"


def test_strict_mode_requires_token():
    with TestClient(app) as client:
        for path in ["/v1/research-tasks", "/v1/metrics", "/v1/search?q=pricing"]:
            response = client.get(path)
            assert response.status_code == 401, (path, response.text)
            assert response.json()["error"]["code"] == "missing_token"


def test_tampered_token_rejected():
    with TestClient(app) as client:
        token = register(client, "dave").json()["token"]
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        response = client.get("/v1/research-tasks", headers=bearer(tampered))
        assert response.status_code == 401


def test_whoami_returns_login_user():
    with TestClient(app) as client:
        token = register(client, "erin").json()["token"]
        response = client.get("/v1/auth/me", headers=bearer(token))
        assert response.status_code == 200
        assert response.json()["username"] == "erin"


def test_workspace_isolation_between_users():
    """A 的任务对其他工作区的 B 不可见：列表不含、详情 404、执行 404、事件为空。"""
    with TestClient(app) as client:
        alice_token = register(client, "alice_ws").json()["token"]
        task = create_task(client, alice_token, title="Alice 私有任务")
        task_id = task["id"]

        bob_token = register(client, "bob_ws").json()["token"]

        bob_list = client.get("/v1/research-tasks", headers=bearer(bob_token))
        assert bob_list.status_code == 200
        assert all(item["id"] != task_id for item in bob_list.json())

        assert client.get(f"/v1/research-tasks/{task_id}", headers=bearer(bob_token)).status_code == 404
        assert client.post(f"/v1/research-tasks/{task_id}/confirm", headers=bearer(bob_token)).status_code == 404
        assert client.get(f"/v1/research-tasks/{task_id}/events", headers=bearer(bob_token)).json() == []

        # Alice 自己可见。
        assert client.get(f"/v1/research-tasks/{task_id}", headers=bearer(alice_token)).status_code == 200


def test_task_attribution_forced_by_login_identity():
    """strict 模式下 created_by 由登录态决定，客户端伪造无效。"""
    with TestClient(app) as client:
        token = register(client, "frank").json()["token"]
        response = client.post(
            "/v1/research-tasks",
            json={"prompt": "调研 Notion 与飞书的协作能力差异", "created_by": "someone-else", "workspace_id": "default"},
            headers=bearer(token),
        )
        assert response.status_code == 201
        task = response.json()
        assert task["created_by"] == "frank"
        # 伪造的 default 工作区不生效：强制归入登录用户激活工作区。
        assert task["workspace_id"] == "frank-default"


def test_shared_workspace_membership_grants_visibility():
    """B 注册到 A 的工作区后可见 A 的任务。"""
    with TestClient(app) as client:
        alice_token = register(client, "gina").json()["token"]
        task = create_task(client, alice_token, title="团队共享任务")
        task_id = task["id"]

        bob_token = register(client, "hank", workspace_id="gina-default").json()["token"]
        shared_list = client.get("/v1/research-tasks", headers=bearer(bob_token))
        assert any(item["id"] == task_id for item in shared_list.json())
        assert client.get(f"/v1/research-tasks/{task_id}", headers=bearer(bob_token)).status_code == 200


def test_workspace_header_for_non_member_rejected():
    with TestClient(app) as client:
        token = register(client, "ivy").json()["token"]
        response = client.get("/v1/research-tasks", headers={**bearer(token), "X-Workspace-Id": "not-my-workspace"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "workspace_forbidden"


def test_competitors_scoped_to_membership():
    with TestClient(app) as client:
        alice_token = register(client, "jack").json()["token"]
        created = client.post(
            "/v1/competitors",
            json={"name": "Cursor", "category": "ai-coding", "workspace_id": "default"},
            headers=bearer(alice_token),
        )
        assert created.status_code == 201, created.text
        # 伪造的 workspace_id=default 被强制改写为登录用户的激活工作区。
        assert created.json()["workspace_id"] == "jack-default"

        bob_token = register(client, "kate").json()["token"]
        bob_list = client.get("/v1/competitors", headers=bearer(bob_token))
        assert all(row["workspace_id"] != "jack-default" for row in bob_list.json())
