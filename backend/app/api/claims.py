"""论断端点：论断详情与人工复核决策。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.auth import AuthContext, get_auth
from app.db import get_db
from app.schemas import ClaimOut, ReviewDecisionCreate, ReviewDecisionOut
from app.services import research_service

router = APIRouter()


@router.get("/claims/{claim_id}", response_model=ClaimOut)
def get_claim(
    claim_id: int,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ClaimOut:
    claim = (
        db.execute(
            select(models.Claim)
            .where(models.Claim.id == claim_id)
            .options(
                selectinload(models.Claim.task),
                selectinload(models.Claim.evidence_links),
                selectinload(models.Claim.evidence_links)
                .selectinload(models.ClaimEvidence.evidence)
                .selectinload(models.Evidence.source),
                selectinload(models.Claim.review_decisions),
            )
        )
        .scalars()
        .first()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    if not auth.can_access(claim.task.workspace_id, claim.task.created_by):
        raise HTTPException(status_code=404, detail="claim not found")
    return research_service.serialize_claim(claim)


@router.post("/claims/{claim_id}/review", response_model=ReviewDecisionOut, status_code=201)
def review_claim(
    claim_id: int,
    payload: ReviewDecisionCreate,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ReviewDecisionOut:
    claim = (
        db.execute(
            select(models.Claim)
            .where(models.Claim.id == claim_id)
            .options(selectinload(models.Claim.task))
        )
        .scalars()
        .first()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    if not auth.can_access(claim.task.workspace_id, claim.task.created_by):
        raise HTTPException(status_code=404, detail="claim not found")

    previous_status = claim.status
    resulting_status = previous_status
    if payload.decision == "accept":
        claim.status = models.ClaimStatus.verified.value
        claim.include_in_report = True
        resulting_status = claim.status
    if payload.decision == "exclude":
        claim.include_in_report = False
        resulting_status = claim.status
    if payload.decision == "mark_uncertain":
        claim.status = models.ClaimStatus.low_confidence.value
        claim.confidence = "low"
        resulting_status = claim.status
    decision = models.ReviewDecision(
        claim_id=claim_id,
        decision=payload.decision,
        reason=payload.reason,
        previous_status=previous_status,
        resulting_status=resulting_status,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    research_service.record_review_decision_event(db, claim, decision)
    research_service.sync_task_review_status(db, claim.task_id)
    return decision
