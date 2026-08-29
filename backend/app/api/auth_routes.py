"""鉴权接口：注册 / 登录 / 当前用户信息。

注册即分配工作区：默认给每个用户一个 "{username}-default" 个人工作区（角色 owner）；
若指定 workspace_id 则加入该工作区（已是首个成员则同样是 owner，否则 member）。
工作区本身无需显式创建，由 membership 记录隐式构成。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.auth import AuthContext, create_access_token, get_auth, hash_password, load_user_workspaces, verify_password
from app.config import get_settings
from app.db import get_db
from app.schemas import AuthLoginIn, AuthRegisterIn, AuthTokenOut, AuthUserOut, WorkspaceMembershipOut

router = APIRouter(prefix="/auth", tags=["auth"])


def build_user_out(db: Session, user: models.User) -> AuthUserOut:
    memberships = load_user_workspaces(db, user.id)
    return AuthUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_active=user.is_active,
        workspaces=[WorkspaceMembershipOut(workspace_id=m.workspace_id, role=m.role) for m in memberships],
    )


def workspace_member_count(db: Session, workspace_id: str) -> int:
    return db.execute(
        select(func.count(models.WorkspaceMember.id)).where(models.WorkspaceMember.workspace_id == workspace_id)
    ).scalar_one()


def issue_token(db: Session, user: models.User) -> AuthTokenOut:
    settings = get_settings()
    token = create_access_token(user, secret=settings.auth_token_secret, ttl_seconds=settings.auth_token_ttl_seconds)
    return AuthTokenOut(token=token, expires_in=settings.auth_token_ttl_seconds, user=build_user_out(db, user))


@router.post("/register", response_model=AuthTokenOut, status_code=201)
def register(payload: AuthRegisterIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    existing = db.execute(select(models.User).where(models.User.username == payload.username)).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=409, detail={"code": "username_taken", "message": "username already exists"})

    user = models.User(username=payload.username, password_hash=hash_password(payload.password), display_name=payload.display_name)
    db.add(user)
    db.flush()

    workspace_id = payload.workspace_id or f"{payload.username}-default"
    role = "owner" if workspace_member_count(db, workspace_id) == 0 else "member"
    db.add(models.WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=role))
    db.commit()
    db.refresh(user)
    return issue_token(db, user)


@router.post("/login", response_model=AuthTokenOut)
def login(payload: AuthLoginIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    user = db.execute(select(models.User).where(models.User.username == payload.username)).scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials", "message": "invalid username or password"})
    if not user.is_active:
        raise HTTPException(status_code=403, detail={"code": "user_inactive", "message": "user has been disabled"})
    return issue_token(db, user)


@router.get("/me", response_model=AuthUserOut)
def whoami(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> AuthUserOut:
    if auth.user is None:
        raise HTTPException(status_code=401, detail={"code": "not_authenticated", "message": "login required in strict auth mode"})
    return build_user_out(db, auth.user)
