import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import Settings
from app.services.analysis.llm import LLMUnavailable, build_llm_extractor
from app.services.analysis.schemas import ClaimExtractionResult, ExtractedClaim


PRICING_TERMS = {"price", "pricing", "plan", "subscription", "seat", "billing", "定价", "价格", "套餐", "订阅"}
FEATURE_TERMS = {"feature", "control", "admin", "privacy", "integration", "workflow", "功能", "控制", "管理", "集成", "隐私"}
POSITIONING_TERMS = {"position", "market", "enterprise", "team", "developer", "定位", "市场", "企业", "团队", "开发者"}


def extract_and_store_claims(db: Session, *, task: models.ResearchTask, settings: Settings) -> ClaimExtractionResult:
    evidence_items = load_task_evidence(db, task.id, limit=settings.llm_max_evidence_items)
    if not evidence_items:
        return ClaimExtractionResult()

    evidence_payload = [serialize_evidence_for_extraction(item) for item in evidence_items]
    llm_extractor = build_llm_extractor(settings)
    if llm_extractor:
        try:
            result = llm_extractor.extract_claims(prompt=task.prompt, evidence_payload=evidence_payload)
        except ValueError as exc:
            raise ValueError(f"schema_validation_failed:{exc}") from exc
        except (LLMUnavailable, KeyError, IndexError, RuntimeError):
            result = rule_based_extract_claims(task=task, evidence_items=evidence_items)
    else:
        result = rule_based_extract_claims(task=task, evidence_items=evidence_items)

    valid_evidence_ids = {item.id for item in evidence_items}
    normalized_claims = dedupe_claims([claim for claim in result.claims if claim.evidence_id in valid_evidence_ids and claim.display_text.strip()])
    stored_claims: list[ExtractedClaim] = []
    for claim in normalized_claims:
        if store_claim(db, task_id=task.id, claim=claim):
            stored_claims.append(claim)
    db.commit()
    return ClaimExtractionResult(claims=stored_claims)


def load_task_evidence(db: Session, task_id: int, *, limit: int) -> list[models.Evidence]:
    return (
        db.execute(
            select(models.Evidence)
            .join(models.Source)
            .where(models.Source.task_id == task_id)
            .options(selectinload(models.Evidence.source))
            .order_by(models.Evidence.quality_score.desc(), models.Evidence.created_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def serialize_evidence_for_extraction(evidence: models.Evidence) -> dict[str, Any]:
    source = evidence.source
    return {
        "evidence_id": evidence.id,
        "quote": evidence.quote,
        "source_title": source.title if source else "",
        "source_url": source.canonical_url if source else "",
        "source_type": source.source_type if source else "",
        "quality_score": evidence.quality_score,
    }


def rule_based_extract_claims(*, task: models.ResearchTask, evidence_items: list[models.Evidence]) -> ClaimExtractionResult:
    claims: list[ExtractedClaim] = []
    competitors = extract_competitors(task)
    for evidence in evidence_items:
        quote = " ".join(evidence.quote.split())
        subject = choose_subject(quote, competitors) or infer_subject_from_source(evidence) or task.title
        claim_type, dimension, predicate = classify_quote(quote)
        display_text = build_display_text(subject, quote)
        claims.append(
            ExtractedClaim(
                evidence_id=evidence.id,
                subject=subject[:160],
                predicate=predicate,
                value={"summary": display_text, "source_quote": quote[:500]},
                claim_type=claim_type,
                dimension=dimension,
                status="verified" if evidence.quality_score >= 0.55 else "low_confidence",
                confidence="high" if evidence.quality_score >= 0.8 else "medium",
                confidence_score=min(max(evidence.quality_score, 0.35), 0.9),
                display_text=display_text,
                relation="supports",
            )
        )
    return ClaimExtractionResult(claims=claims)


def store_claim(db: Session, *, task_id: int, claim: ExtractedClaim) -> bool:
    existing = db.execute(
        select(models.Claim.id).where(
            models.Claim.task_id == task_id,
            models.Claim.subject == claim.subject,
            models.Claim.predicate == claim.predicate,
            models.Claim.claim_type == claim.claim_type,
        )
    ).first()
    if existing:
        return False

    model_claim = models.Claim(
        task_id=task_id,
        subject=claim.subject,
        predicate=claim.predicate,
        value_json=json_dumps(claim.value),
        claim_type=claim.claim_type,
        dimension=claim.dimension,
        status=claim.status,
        confidence=claim.confidence,
        confidence_score=claim.confidence_score,
        display_text=claim.display_text,
        include_in_report=True,
        evidence_coverage=1.0,
    )
    db.add(model_claim)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    db.add(models.ClaimEvidence(claim_id=model_claim.id, evidence_id=claim.evidence_id, relation=claim.relation, weight=1.0))
    return True


def extract_competitors(task: models.ResearchTask) -> list[str]:
    try:
        scope = json_loads(task.scope_json)
    except ValueError:
        return []
    return [str(item) for item in scope.get("competitors", []) if item]


def dedupe_claims(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    seen: set[tuple[str, str, str]] = set()
    result: list[ExtractedClaim] = []
    for claim in claims:
        key = (claim.subject.lower(), claim.predicate.lower(), claim.claim_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(claim)
    return result


def choose_subject(text: str, competitors: list[str]) -> str | None:
    lowered = text.lower()
    for competitor in competitors:
        if competitor.lower() in lowered:
            return competitor
    return None


def infer_subject_from_source(evidence: models.Evidence) -> str | None:
    if not evidence.source:
        return None
    title = evidence.source.title.strip()
    if title:
        return title.split("|")[0].split("-")[0].strip()[:160]
    return None


def classify_quote(text: str) -> tuple[str, str, str]:
    lowered = text.lower()
    if contains_any(lowered, PRICING_TERMS):
        return "pricing", "定价策略", "has_pricing_signal"
    if contains_any(lowered, FEATURE_TERMS):
        return "feature", "核心功能", "supports_feature"
    if contains_any(lowered, POSITIONING_TERMS):
        return "positioning", "市场定位", "has_positioning_signal"
    return "general", "general", "states_fact"


def contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def build_display_text(subject: str, quote: str) -> str:
    sentence = split_sentence(quote)
    return f"{subject}: {sentence}"[:700]


def split_sentence(text: str) -> str:
    parts = re.split(r"(?<=[。！？.!?])\s+", text)
    return (parts[0] if parts else text).strip()[:500]


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str) -> dict[str, Any]:
    import json

    return json.loads(value)
