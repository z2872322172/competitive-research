"""Claim 多源交叉验证（改造方案 5.6 / 5.7）。

对每个 Claim 按证据关系收集支持 / 冲突来源，计算来源多样性、最高支持来源
可靠性和置信分公式，判定 verified / corroborated / low_confidence / conflict
等状态；存在冲突时把调和结论（resolution）合并写回 Claim.value_json，
不做简单删除，保证冲突可追溯。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.services.source_quality import score_source_reliability

# 置信分公式权重（方案 5.6）
WEIGHT_MAX_SOURCE_RELIABILITY = 0.45
WEIGHT_SOURCE_DIVERSITY = 0.20
WEIGHT_EVIDENCE_QUALITY = 0.20
WEIGHT_RECENCY = 0.10
WEIGHT_CITATION_LOCATOR = 0.05
# 冲突扣分：高可靠（或与支持侧同等级）来源反驳扣得多，弱冲突扣得少
CONFLICT_PENALTY_STRONG = 0.15
CONFLICT_PENALTY_WEAK = 0.08
# 冲突判定：反驳来源至少 medium 可靠，且与支持侧最高可靠来源相当（允许 0.1 差距）
CONFLICT_RELIABILITY_THRESHOLD = 0.6
CONFLICT_RELATIVE_TOLERANCE = 0.1
# verified 门槛：单来源支持时需要至少 medium 可靠来源
VERIFIED_RELIABILITY_THRESHOLD = 0.6
CORROBORATED_MIN_SOURCES = 2
# 置信分级
HIGH_CONFIDENCE_THRESHOLD = 0.75
MEDIUM_CONFIDENCE_THRESHOLD = 0.55
# 仅社区来源时的多样性上限（方案 5.6）
SOCIAL_SOURCE_TYPES = {"social", "community"}
# 人工已决策（非 continue_research）的 Claim 不被机器验证覆盖
OPEN_REVIEW_DECISIONS = {"", "continue_research", None}
# recency 分档：90 天内 1.0，180 天内 0.8，365 天内 0.6，更早 0.4，无时间信息 0.5（常青文档中性）
RECENCY_TIERS = ((90, 1.0), (180, 0.8), (365, 0.6))
RECENCY_WITHOUT_DATE = 0.5
RECENCY_STALE = 0.4


@dataclass
class ClaimVerification:
    """单个 Claim 的交叉验证结果（可解释、确定性）。"""

    claim_id: int
    status: str
    confidence_score: float
    confidence_label: str
    support_evidence_ids: list[int] = field(default_factory=list)
    conflict_evidence_ids: list[int] = field(default_factory=list)
    distinct_source_count: int = 0
    distinct_domain_count: int = 0
    source_diversity_score: float = 0.0
    max_supporting_source_reliability: float = 0.0
    evidence_quality_avg: float = 0.0
    recency_score: float = 0.0
    citation_locator_score: float = 0.0
    conflict_penalty: float = 0.0
    conflict: bool = False
    resolution_strategy: str = ""
    resolution: dict[str, Any] | None = None

    def confidence_breakdown(self) -> dict[str, float]:
        return {
            "max_supporting_source_reliability": round(self.max_supporting_source_reliability, 4),
            "source_diversity_score": round(self.source_diversity_score, 4),
            "evidence_quality_avg": round(self.evidence_quality_avg, 4),
            "recency_score": round(self.recency_score, 4),
            "citation_locator_score": round(self.citation_locator_score, 4),
            "conflict_penalty": round(self.conflict_penalty, 4),
        }


def analyze_claim(claim: models.Claim) -> ClaimVerification:
    """对单个 Claim 做多源交叉验证分析（纯计算，不写库）。

    需要 claim.evidence_links 及 evidence.source 关系可用（selectinload 或手工赋值）。
    """
    supports: list[models.ClaimEvidence] = []
    conflicts: list[models.ClaimEvidence] = []
    for link in claim.evidence_links:
        if link.relation == "conflicts":
            conflicts.append(link)
        elif link.relation == "supports":
            supports.append(link)
        # context 等背景关系不参与支持/冲突判定，只作参考

    support_reliabilities = [evidence_reliability(link) for link in supports]
    conflict_reliabilities = [evidence_reliability(link) for link in conflicts]
    max_support_reliability = max(support_reliabilities, default=0.0)
    max_conflict_reliability = max(conflict_reliabilities, default=0.0)

    source_ids = {link.evidence.source_id for link in supports if link.evidence is not None}
    source_types = set()
    domains = set()
    for link in supports:
        source = link.evidence.source if link.evidence is not None else None
        if source is None:
            continue
        source_types.add(str(source.source_type or "").lower())
        host = urlparse(str(source.canonical_url or source.url or "")).netloc.lower()
        if host:
            domains.add(host)

    diversity = source_diversity_score(len(source_ids), source_types)
    quality_avg = (
        sum((link.evidence.quality_score if link.evidence else 0.0) for link in supports) / len(supports)
        if supports
        else 0.0
    )
    recency = max((source_recency_score(link) for link in supports), default=0.0)
    locator = citation_locator_score(supports)

    strong_conflict = bool(conflicts) and (
        max_conflict_reliability >= CONFLICT_RELIABILITY_THRESHOLD
        and max_conflict_reliability >= max_support_reliability - CONFLICT_RELATIVE_TOLERANCE
    )
    conflict_penalty = CONFLICT_PENALTY_STRONG if strong_conflict else (CONFLICT_PENALTY_WEAK if conflicts else 0.0)

    confidence_score = compute_confidence_score(
        max_support_reliability=max_support_reliability,
        source_diversity_score=diversity,
        evidence_quality_avg=quality_avg,
        recency_score=recency,
        citation_locator_score=locator,
        conflict_penalty=conflict_penalty,
    )

    verification = ClaimVerification(
        claim_id=claim.id,
        status="",
        confidence_score=confidence_score,
        confidence_label=confidence_label(confidence_score),
        support_evidence_ids=[link.evidence_id for link in supports],
        conflict_evidence_ids=[link.evidence_id for link in conflicts],
        distinct_source_count=len(source_ids),
        distinct_domain_count=len(domains),
        source_diversity_score=diversity,
        max_supporting_source_reliability=max_support_reliability,
        evidence_quality_avg=quality_avg,
        recency_score=recency,
        citation_locator_score=locator,
        conflict_penalty=conflict_penalty,
        conflict=strong_conflict,
    )

    verification.status = resolve_status(
        claim=claim,
        has_supports=bool(supports),
        has_conflicts=bool(conflicts),
        strong_conflict=strong_conflict,
        distinct_source_count=len(source_ids),
        max_support_reliability=max_support_reliability,
        confidence_score=confidence_score,
    )

    if conflicts:
        verification.resolution = build_conflict_resolution(
            claim,
            supports=supports,
            conflicts=conflicts,
            max_support_reliability=max_support_reliability,
            max_conflict_reliability=max_conflict_reliability,
        )
        verification.resolution_strategy = verification.resolution.get("resolution_strategy", "")

    return verification


def resolve_status(
    *,
    claim: models.Claim,
    has_supports: bool,
    has_conflicts: bool,
    strong_conflict: bool,
    distinct_source_count: int,
    max_support_reliability: float,
    confidence_score: float,
) -> str:
    if not has_supports and not has_conflicts:
        # 无有效证据：undisclosed 有特定语义（搜索后确认未公开披露），保留；其余待补证
        if claim.status == models.ClaimStatus.undisclosed.value:
            return models.ClaimStatus.undisclosed.value
        return models.ClaimStatus.needs_evidence.value
    if not has_supports:
        # 只有冲突证据：明确标记冲突，交由人工审阅
        return models.ClaimStatus.conflict.value
    if strong_conflict:
        return models.ClaimStatus.conflict.value
    if distinct_source_count >= CORROBORATED_MIN_SOURCES:
        status = models.ClaimStatus.corroborated.value
    elif max_support_reliability >= VERIFIED_RELIABILITY_THRESHOLD:
        status = models.ClaimStatus.verified.value
    else:
        status = models.ClaimStatus.low_confidence.value
    if status in {models.ClaimStatus.verified.value, models.ClaimStatus.corroborated.value} and confidence_score < MEDIUM_CONFIDENCE_THRESHOLD:
        # 综合置信分不达 medium 时降级，保持历史行为（score < 0.55 → low_confidence）
        status = models.ClaimStatus.low_confidence.value
    return status


def compute_confidence_score(
    *,
    max_support_reliability: float,
    source_diversity_score: float,
    evidence_quality_avg: float,
    recency_score: float,
    citation_locator_score: float,
    conflict_penalty: float,
) -> float:
    score = (
        WEIGHT_MAX_SOURCE_RELIABILITY * max_support_reliability
        + WEIGHT_SOURCE_DIVERSITY * source_diversity_score
        + WEIGHT_EVIDENCE_QUALITY * evidence_quality_avg
        + WEIGHT_RECENCY * recency_score
        + WEIGHT_CITATION_LOCATOR * citation_locator_score
        - conflict_penalty
    )
    return round(min(max(score, 0.05), 0.98), 4)


def confidence_label(score: float) -> str:
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if score >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def evidence_reliability(link: models.ClaimEvidence) -> float:
    evidence = link.evidence
    if evidence is None or evidence.source is None:
        return 0.0
    return float(score_source_reliability(evidence.source).get("score", 0.5))


def source_diversity_score(distinct_source_count: int, source_types: set[str]) -> float:
    if distinct_source_count <= 0:
        return 0.0
    if distinct_source_count == 1:
        score = 0.3
    elif distinct_source_count == 2:
        score = 0.7
    else:
        score = 1.0
    if source_types and source_types.issubset(SOCIAL_SOURCE_TYPES):
        score = min(score, 0.5)
    return score


def source_recency_score(link: models.ClaimEvidence) -> float:
    evidence = link.evidence
    if evidence is None or evidence.source is None:
        return 0.0
    source = evidence.source
    timestamp = source.published_at or source.retrieved_at
    if timestamp is None:
        return RECENCY_WITHOUT_DATE
    if timestamp.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=None)
    now = models.utc_now()
    if timestamp > now + timedelta(days=1):
        # 未来时间（解析异常）按未知处理
        return RECENCY_WITHOUT_DATE
    age_days = (now - timestamp).days
    for threshold, score in RECENCY_TIERS:
        if age_days <= threshold:
            return score
    return RECENCY_STALE


def citation_locator_score(supports: list[models.ClaimEvidence]) -> float:
    if not supports:
        return 0.0
    located = 0
    for link in supports:
        locator = decode_json_str(link.evidence.locator_json if link.evidence is not None else "")
        if locator:
            located += 1
    return round(located / len(supports), 4)


def build_conflict_resolution(
    claim: models.Claim,
    *,
    supports: list[models.ClaimEvidence],
    conflicts: list[models.ClaimEvidence],
    max_support_reliability: float,
    max_conflict_reliability: float,
) -> dict[str, Any]:
    """构建写回 value_json 的冲突调和结果（方案 5.7）。"""
    support_stronger = bool(supports) and max_support_reliability > max_conflict_reliability + 0.05
    if support_stronger:
        strategy = "prefer_primary_recent_source"
        preferred = preferred_supporting_source(supports)
        reason = (
            "支持证据来自可靠性更高的来源"
            + ("，且为官方/一手来源" if preferred and preferred.get("is_primary") else "")
            + "，优先采用该侧结论，同时保留冲突证据供复核。"
        )
    else:
        strategy = "mark_as_unresolved"
        preferred = preferred_supporting_source(supports) if supports else None
        reason = "支持与冲突证据强度接近（或缺少支持证据），无法自动调和，保留冲突并交由人工审阅。"

    value = decode_json_str(claim.value_json)
    conflict_summary = f"{claim.subject} 相关结论在 {len({link.evidence_id for link in conflicts})} 条证据中与当前结论存在矛盾"

    resolution: dict[str, Any] = {
        "conflict": True,
        "conflict_summary": conflict_summary,
        "preferred_value": str(value.get("summary") or claim.display_text)[:200] if (value or claim.display_text) else None,
        "preferred_source_id": preferred.get("source_id") if preferred else None,
        "resolution_strategy": strategy,
        "conflicting_evidence_ids": sorted({link.evidence_id for link in conflicts}),
        "reason": reason,
    }
    return resolution


def preferred_supporting_source(supports: list[models.ClaimEvidence]) -> dict[str, Any] | None:
    """支持侧最优来源：可靠性优先，其次一手来源，再次最新发布/抓取时间。"""
    best: dict[str, Any] | None = None
    for link in supports:
        evidence = link.evidence
        source = evidence.source if evidence is not None else None
        if source is None:
            continue
        reliability = evidence_reliability(link)
        timestamp = source.published_at or source.retrieved_at or datetime.min
        candidate = {
            "source_id": source.id,
            "is_primary": bool(source.is_primary),
            "reliability": reliability,
            "timestamp": timestamp,
        }
        if best is None or (
            candidate["reliability"],
            candidate["is_primary"],
            candidate["timestamp"],
        ) > (best["reliability"], best["is_primary"], best["timestamp"]):
            best = candidate
    return best


def apply_verification(claim: models.Claim, verification: ClaimVerification) -> None:
    """把验证结果写回 Claim（状态、置信、覆盖率、冲突调和 value_json）。"""
    claim.status = verification.status
    if verification.status == models.ClaimStatus.undisclosed.value:
        # 未披露 ≠ 低置信（搜索后确认无公开信息），保留原置信字段
        pass
    else:
        claim.confidence = verification.confidence_label
        claim.confidence_score = verification.confidence_score
        if verification.status == models.ClaimStatus.needs_evidence.value:
            # 缺证据：置信上限 0.4，与历史行为保持一致
            claim.confidence_score = min(claim.confidence_score, 0.4)
            claim.confidence = "low"
    if claim.evidence_links:
        claim.evidence_coverage = max(claim.evidence_coverage, 1.0)
    else:
        claim.evidence_coverage = 0.0
    if verification.resolution is not None:
        value = decode_json_str(claim.value_json)
        value.update(verification.resolution)
        claim.value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def cross_validate_claims(db: Session, *, task: models.ResearchTask) -> dict[str, Any]:
    """任务级多源交叉验证入口：逐 Claim 分析并落库。

    已有人工审阅决策（accept/exclude/mark_uncertain）的 Claim 不被覆盖。
    返回汇总统计和逐 Claim 结果（claim_results 供事件层使用后剔除）。
    """
    claims = (
        db.execute(
            select(models.Claim)
            .where(models.Claim.task_id == task.id)
            .options(
                selectinload(models.Claim.evidence_links)
                .selectinload(models.ClaimEvidence.evidence)
                .selectinload(models.Evidence.source),
                selectinload(models.Claim.review_decisions),
            )
            .order_by(models.Claim.created_at.asc())
        )
        .scalars()
        .all()
    )

    claim_results: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    cited_claims = 0
    confidence_total = 0.0

    for claim in claims:
        latest_review = max(claim.review_decisions, key=lambda item: item.created_at, default=None)
        human_reviewed = latest_review is not None and latest_review.decision not in OPEN_REVIEW_DECISIONS
        verification = analyze_claim(claim)
        changed = False
        if not human_reviewed:
            previous = (claim.status, claim.confidence_score)
            apply_verification(claim, verification)
            changed = (claim.status, claim.confidence_score) != previous
        if claim.evidence_links:
            cited_claims += 1
        status_counts[claim.status] = status_counts.get(claim.status, 0) + 1
        confidence_total += claim.confidence_score

        result: dict[str, Any] = {
            "claim_id": claim.id,
            "subject": claim.subject,
            "status": claim.status,
            "confidence_score": claim.confidence_score,
            "support_evidence_ids": verification.support_evidence_ids,
            "conflict_evidence_ids": verification.conflict_evidence_ids,
            "support_source_count": verification.distinct_source_count,
            "source_diversity_score": verification.source_diversity_score,
            "max_supporting_source_reliability": verification.max_supporting_source_reliability,
            "changed": changed,
            "confidence_breakdown": verification.confidence_breakdown(),
        }
        if verification.resolution is not None:
            result["conflict_summary"] = verification.resolution.get("conflict_summary")
            result["resolution_strategy"] = verification.resolution.get("resolution_strategy")
            result["conflicting_evidence_ids"] = verification.resolution.get("conflicting_evidence_ids")
        claim_results.append(result)

    db.commit()

    total = len(claims)
    return {
        "claims_created": total,
        "cited_claims": cited_claims,
        "claims_without_evidence": status_counts.get(models.ClaimStatus.needs_evidence.value, 0),
        "verified_claims": status_counts.get(models.ClaimStatus.verified.value, 0),
        "corroborated_claims": status_counts.get(models.ClaimStatus.corroborated.value, 0),
        "low_confidence_claims": status_counts.get(models.ClaimStatus.low_confidence.value, 0),
        "conflict_claims": status_counts.get(models.ClaimStatus.conflict.value, 0),
        "undisclosed_claims": status_counts.get(models.ClaimStatus.undisclosed.value, 0),
        "citation_coverage": round(cited_claims / total, 4) if total else 0.0,
        "avg_confidence_score": round(confidence_total / total, 4) if total else 0.0,
        "claim_results": claim_results,
    }


def decode_json_str(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}
