"""Claim-level evidence conflict analysis.

The result is intentionally deterministic and explainable. It gives reviewers a
transparent first-pass judgement while the deeper LLM verifier is still evolving.
"""

from typing import Any

from app import models
from app.services import claim_verification
from app.services.source_quality import score_source_reliability


def analyze_claim_conflict(claim: models.Claim) -> dict[str, Any]:
    grouped = {"supports": [], "conflicts": [], "context": []}
    for link in claim.evidence_links:
        relation = link.relation if link.relation in grouped else "supports"
        grouped[relation].append(link)

    support_score = relation_score(grouped["supports"])
    conflict_score = relation_score(grouped["conflicts"])
    context_count = len(grouped["context"])
    support_count = len(grouped["supports"])
    conflict_count = len(grouped["conflicts"])
    needs_more_research = claim.status in {
        models.ClaimStatus.needs_evidence.value,
        models.ClaimStatus.undisclosed.value,
    }

    if conflict_count:
        needs_more_research = True
        if conflict_score > support_score + 0.05:
            recommendation = "冲突证据来源质量更高，建议下调或改写该 Claim，并继续查找一手来源。"
            preferred_relation = "conflicts"
        elif support_score > conflict_score + 0.05:
            recommendation = "支持证据来源质量更高，可保留 Claim，但报告中应披露冲突来源。"
            preferred_relation = "supports"
        else:
            recommendation = "支持与冲突证据强度接近，建议继续查证或在报告中标注不确定边界。"
            preferred_relation = "mixed"
    elif support_count:
        recommendation = "当前未发现冲突证据，可基于已有来源保留 Claim。"
        preferred_relation = "supports"
    else:
        recommendation = "Claim 缺少可追溯证据，建议继续搜索或排除出报告。"
        preferred_relation = "none"
        needs_more_research = True

    rationale = [
        f"支持证据 {support_count} 条，平均强度 {support_score:.0%}",
        f"冲突证据 {conflict_count} 条，平均强度 {conflict_score:.0%}",
    ]
    if context_count:
        rationale.append(f"背景证据 {context_count} 条")

    verification = claim_verification.analyze_claim(claim)
    if verification.distinct_source_count >= 2:
        rationale.append(f"支持来源覆盖 {verification.distinct_source_count} 个独立来源（{verification.distinct_domain_count} 个域名）")
    if verification.resolution is not None:
        rationale.append(f"冲突调和策略：{verification.resolution.get('resolution_strategy', '')}")

    return {
        "support_count": support_count,
        "conflict_count": conflict_count,
        "context_count": context_count,
        "support_score": round(support_score, 2),
        "conflict_score": round(conflict_score, 2),
        "preferred_relation": preferred_relation,
        "needs_more_research": needs_more_research,
        "recommendation": recommendation,
        "rationale": rationale,
        "distinct_source_count": verification.distinct_source_count,
        "source_diversity_score": round(verification.source_diversity_score, 2),
        "max_supporting_source_reliability": round(verification.max_supporting_source_reliability, 2),
        "confidence_breakdown": verification.confidence_breakdown(),
    }


def relation_score(links: list[models.ClaimEvidence]) -> float:
    if not links:
        return 0.0
    scores = []
    for link in links:
        evidence = link.evidence
        if evidence is None:
            scores.append(0.0)
            continue
        source_score = score_source_reliability(evidence.source).get("score", 0.5) if evidence.source else 0.5
        scores.append(((evidence.quality_score * 0.55) + (source_score * 0.45)) * max(link.weight, 0.1))
    return sum(scores) / len(scores)
