"""鉴权与用户隔离：JWT 登录态 + 工作区成员校验。

设计说明：
- 令牌为标准 HS256 JWT（header.payload.signature，base64url），用标准库 hmac/hashlib 手写，
  避免引入 pyjwt 依赖；签名密钥来自 Settings.auth_token_secret。
- 密码使用 PBKDF2-SHA256（20 万次迭代 + 16 字节随机盐）哈希存储，格式：
  pbkdf2_sha256$iterations$salt_hex$hash_hex
- auth_mode=strict 时所有业务接口强制 Bearer 令牌，并按 workspace_members 表校验
  工作区归属；auth_mode=disabled 时退回原 X-Workspace-Id / X-User-Id 头部行为（离线/演示）。
- AUTH_MODE_OVERRIDE 环境变量优先于 Settings（get_settings 有 lru_cache，测试需要
  在不重建应用实例的情况下切换模式，因此此处实时读取环境变量）。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import get_db

PBKDF2_ITERATIONS = 200_000
TOKEN_ALGORITHM = "HS256"


class AuthError(HTTPException):
    def __init__(self, code: str, message: str, status_code: int = 401) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


# ---------------------------------------------------------------------------
# 密码哈希
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(hash_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# JWT（HS256，标准格式，零依赖实现）
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(user: models.User, *, secret: str, ttl_seconds: int) -> str:
    issued_at = int(time.time())
    header = _b64url_encode(json.dumps({"alg": TOKEN_ALGORITHM, "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url_encode(
        json.dumps(
            {"sub": str(user.id), "username": user.username, "iat": issued_at, "exp": issued_at + ttl_seconds},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(signature)}"


def decode_access_token(token: str, *, secret: str) -> dict:
    """校验签名与过期时间，返回 payload；失败抛 AuthError。"""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            raise AuthError("invalid_token", "token signature verification failed")
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != TOKEN_ALGORITHM:
            raise AuthError("invalid_token", f"unsupported token algorithm: {header.get('alg')}")
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("malformed_token", "token is malformed") from exc
    if not isinstance(payload, dict) or "sub" not in payload:
        raise AuthError("malformed_token", "token payload is invalid")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthError("token_expired", "token has expired")
    return payload


# ---------------------------------------------------------------------------
# 请求级鉴权上下文
# ---------------------------------------------------------------------------

@dataclass
class AuthContext:
    """一次请求的鉴权上下文：路由统一通过它做工作区隔离判断。"""

    strict: bool
    user: models.User | None = None
    username: str = "anonymous"
    workspace_id: str | None = None
    workspace_ids: list[str] = field(default_factory=list)
    # disabled 模式下保留原有的 X-User-Id 过滤语义；strict 模式下恒为 None（按工作区整体可见）。
    created_by_filter: str | None = None

    def can_access_workspace(self, resource_workspace_id: str | None) -> bool:
        if not self.strict:
            # 与原 task_matches_scope 语义一致：未指定则不过滤。
            return not self.workspace_id or resource_workspace_id == self.workspace_id
        return resource_workspace_id in self.workspace_ids

    def can_access(self, resource_workspace_id: str | None, resource_created_by: str | None = None) -> bool:
        """资源级访问判断：strict 按工作区成员关系，disabled 保留原 header 过滤语义。"""
        if not self.can_access_workspace(resource_workspace_id):
            return False
        if not self.strict and self.created_by_filter and resource_created_by is not None:
            return resource_created_by == self.created_by_filter
        return True

    def resolve_workspace_for_create(self, requested: str | None) -> str:
        """创建资源时的工作区归属：strict 强制归入当前激活工作区。"""
        if not self.strict:
            return requested or "default"
        return self.workspace_id or (self.workspace_ids[0] if self.workspace_ids else "default")


def resolve_auth_mode() -> str:
    override = os.getenv("AUTH_MODE_OVERRIDE")
    if override:
        return override.strip().lower()
    return get_settings().auth_mode.strip().lower()


def load_user_workspaces(db: Session, user_id: int) -> list[models.WorkspaceMember]:
    return list(
        db.execute(
            select(models.WorkspaceMember)
            .where(models.WorkspaceMember.user_id == user_id)
            .order_by(models.WorkspaceMember.id.asc())
        )
        .scalars()
        .all()
    )


def get_auth(
    authorization: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> AuthContext:
    strict = resolve_auth_mode() == "strict"

    if not strict:
        # disabled 模式：完全保留旧行为，离线/演示不需要登录。
        return AuthContext(strict=False, workspace_id=x_workspace_id, created_by_filter=x_user_id)

    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("missing_token", "authentication required: provide 'Authorization: Bearer <token>'")
    payload = decode_access_token(authorization[len("Bearer "):].strip(), secret=settings.auth_token_secret)

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise AuthError("malformed_token", "token subject is invalid") from exc

    user = db.get(models.User, user_id)
    if user is None or not user.is_active:
        raise AuthError("user_inactive", "user does not exist or has been disabled")

    memberships = load_user_workspaces(db, user.id)
    workspace_ids = [membership.workspace_id for membership in memberships]

    if x_workspace_id and x_workspace_id not in workspace_ids:
        raise AuthError(
            "workspace_forbidden",
            f"user '{user.username}' is not a member of workspace '{x_workspace_id}'",
            status_code=403,
        )

    active_workspace = x_workspace_id or (workspace_ids[0] if workspace_ids else None)
    return AuthContext(
        strict=True,
        user=user,
        username=user.username,
        workspace_id=active_workspace,
        workspace_ids=workspace_ids,
        created_by_filter=None,
    )


def require_auth(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    """strict 模式下仅要求已登录（如 metrics/search 等不做工作区过滤的接口）。"""
    return auth
