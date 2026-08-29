"""竞品画像库端点。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import AuthContext, get_auth
from app.db import get_db
from app.schemas import CompetitorProfileCreate, CompetitorProfileOut
from app.services import research_service

router = APIRouter()


@router.post("/competitors", response_model=CompetitorProfileOut, status_code=201)
def create_competitor_profile(
    payload: CompetitorProfileCreate,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> CompetitorProfileOut:
    # strict 模式下竞品归属强制绑定到当前激活工作区，客户端传入值仅作请求意向不作信任。
    payload.workspace_id = auth.resolve_workspace_for_create(payload.workspace_id)
    try:
        return research_service.create_competitor_profile(db, payload)
    except ValueError as exc:
        if str(exc) == "competitor_profile_exists":
            raise HTTPException(status_code=409, detail={"code": "competitor_profile_exists", "message": "competitor profile already exists"}) from exc
        raise


@router.get("/competitors", response_model=list[CompetitorProfileOut])
def list_competitor_profiles(
    workspace_id: str | None = None,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> list[CompetitorProfileOut]:
    if auth.strict:
        visible = [workspace_id] if workspace_id in auth.workspace_ids else auth.workspace_ids
        rows: list[CompetitorProfileOut] = []
        for ws in visible:
            rows.extend(research_service.list_competitor_profiles(db, workspace_id=ws))
        return rows
    return research_service.list_competitor_profiles(db, workspace_id=workspace_id or "default")
