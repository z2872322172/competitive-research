"""阶段 3 Claim 多源交叉验证测试：状态判定 / 置信分公式 / 冲突调和写入 value_json / 事件。"""

import pytest

from app import models
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.services import claim_verification, research_service


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def create_task_and_run(db):
    task = research_service.create_task(
        db,
        research_service.ResearchTaskCreate(
            prompt="Research multi source claim verification",
            competitors=["Cursor"],
            dimensions=["pricing"],
        ),
    )
    run = research_service.create_run(db, task.id)
    return task, run


def add_source(db, task_id, *, source_type="official", url="https://cursor.example/pricing", publisher="Cursor", is_primary=True, index=0):
    source = models.Source(
        task_id=task_id,
        url=url,
        canonical_url=url,
        source_type=source_type,
        title=f"Source {index}",
        publisher=publisher,
        content_hash=f"{task_id}-source-{index}",
        is_primary=is_primary,
    )
    db.add(source)
    db.flush()
    return source


def add_evidence(db, source, *, quality=0.85, index=0, locator=True):
    evidence = models.Evidence(
        source_id=source.id,
        quote=f"Evidence quote {index}",
        locator_json=research_service.encode_json({"kind": "html", "char_start": 0}) if locator else "{}",
        evidence_hash=f"{source.id}-evidence-{index}",
        extraction_method="verification_test",
        quality_score=quality,
    )
    db.add(evidence)
    db.flush()
    return evidence


def add_claim(db, task_id, *, status="verified", confidence_score=0.8, subject="Cursor", predicate="has_pricing_signal"):
    claim = models.Claim(
        task_id=task_id,
        subject=subject,
        predicate=predicate,
        value_json=research_service.encode_json({"summary": "Cursor Pro is 20 dollars per month"}),
        claim_type="pricing",
        dimension="定价策略",
        status=status,
        confidence="medium",
        confidence_score=confidence_score,
        display_text="Cursor Pro 套餐定价为 20 美元/月。",
    )
    db.add(claim)
    db.flush()
    return claim


def link_evidence(db, claim, evidence, *, relation="supports", weight=1.0):
    db.add(models.ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relation=relation, weight=weight))
    db.flush()


def test_compute_confidence_score_follows_formula():
    score = claim_verification.compute_confidence_score(
        max_support_reliability=0.9,
        source_diversity_score=0.7,
        evidence_quality_avg=0.8,
        recency_score=1.0,
        citation_locator_score=1.0,
        conflict_penalty=0.0,
    )
    assert score == round(0.45 * 0.9 + 0.20 * 0.7 + 0.20 * 0.8 + 0.10 * 1.0 + 0.05 * 1.0, 4)

    penalized = claim_verification.compute_confidence_score(
        max_support_reliability=0.9,
        source_diversity_score=0.7,
        evidence_quality_avg=0.8,
        recency_score=1.0,
        citation_locator_score=1.0,
        conflict_penalty=0.15,
    )
    assert score - penalized == pytest.approx(0.15, abs=1e-4)


def test_source_diversity_score_tiers_and_social_cap():
    assert claim_verification.source_diversity_score(0, set()) == 0.0
    assert claim_verification.source_diversity_score(1, {"official"}) == 0.3
    assert claim_verification.source_diversity_score(2, {"official", "docs"}) == 0.7
    assert claim_verification.source_diversity_score(3, {"official", "docs", "news"}) == 1.0
    # 只有社区来源：上限 0.5
    assert claim_verification.source_diversity_score(3, {"social"}) == 0.5
    assert claim_verification.source_diversity_score(2, {"community", "social"}) == 0.5


def test_single_official_support_becomes_verified(db=None):
    db = SessionLocal()
    try:
        task, _run = create_task_and_run(db)
        source = add_source(db, task.id, index=0)
        evidence = add_evidence(db, source, index=0)
        claim = add_claim(db, task.id)
        link_evidence(db, claim, evidence)

        summary = claim_verification.cross_validate_claims(db, task=task)

        assert claim.status == models.ClaimStatus.verified.value
        assert claim.confidence_score > 0.6
        assert summary["verified_claims"] == 1
        assert summary["corroborated_claims"] == 0
        assert summary["claims_created"] == 1
        assert summary["citation_coverage"] == 1.0
    finally:
        db.rollback()
        db.close()


def test_two_distinct_sources_become_corroborated():
    db = SessionLocal()
    try:
        task, _run = create_task_and_run(db)
        official = add_source(db, task.id, index=0)
        docs = add_source(db, task.id, source_type="docs", url="https://docs.example/pricing", publisher="Docs", index=1)
        evidence_a = add_evidence(db, official, index=0)
        evidence_b = add_evidence(db, docs, index=1)
        claim = add_claim(db, task.id)
        link_evidence(db, claim, evidence_a)
        link_evidence(db, claim, evidence_b)

        summary = claim_verification.cross_validate_claims(db, task=task)

        assert claim.status == models.ClaimStatus.corroborated.value
        assert summary["corroborated_claims"] == 1
        analysis = claim_verification.analyze_claim(claim)
        assert analysis.source_diversity_score == 0.7
        assert analysis.distinct_source_count == 2
        assert analysis.distinct_domain_count == 2
    finally:
        db.rollback()
        db.close()


def test_strong_conflict_marks_conflict_and_writes_resolution_into_value_json():
    db = SessionLocal()
    try:
        task, _run = create_task_and_run(db)
        # 支持侧是 news（可靠但低于官方），冲突侧是 official → 强冲突
        news = add_source(db, task.id, source_type="news", url="https://news.example/pricing", publisher="News", is_primary=False, index=0)
        official = add_source(db, task.id, index=1)
        support = add_evidence(db, news, index=0)
        conflict = add_evidence(db, official, index=1)
        claim = add_claim(db, task.id)
        link_evidence(db, claim, support, relation="supports")
        link_evidence(db, claim, conflict, relation="conflicts")

        summary = claim_verification.cross_validate_claims(db, task=task)

        assert claim.status == models.ClaimStatus.conflict.value
        assert summary["conflict_claims"] == 1
        value = research_service.decode_json(claim.value_json)
        assert value["conflict"] is True
        assert value["resolution_strategy"] == "mark_as_unresolved"
        assert value["conflicting_evidence_ids"] == [conflict.id]
        assert "人工审阅" in value["reason"]
        # 冲突被扣分
        analysis = claim_verification.analyze_claim(claim)
        assert analysis.conflict_penalty == pytest.approx(claim_verification.CONFLICT_PENALTY_STRONG)
    finally:
        db.rollback()
        db.close()


def test_weak_conflict_stays_verified_but_records_resolution():
    db = SessionLocal()
    try:
        task, _run = create_task_and_run(db)
        official = add_source(db, task.id, index=0)
        social = add_source(
            db,
            task.id,
            source_type="social",
            url="http://forum.example/thread",
            publisher="",
            is_primary=False,
            index=1,
        )
        support = add_evidence(db, official, index=0)
        conflict = add_evidence(db, social, index=1, quality=0.4)
        claim = add_claim(db, task.id)
        link_evidence(db, claim, support, relation="supports")
        link_evidence(db, claim, conflict, relation="conflicts")

        claim_verification.cross_validate_claims(db, task=task)

        # 低可靠来源的反驳不足以推翻结论，但冲突被披露并弱扣分
        assert claim.status == models.ClaimStatus.verified.value
        analysis = claim_verification.analyze_claim(claim)
        assert analysis.conflict_penalty == pytest.approx(claim_verification.CONFLICT_PENALTY_WEAK)
        value = research_service.decode_json(claim.value_json)
        assert value["conflict"] is True
        assert value["resolution_strategy"] == "prefer_primary_recent_source"
        assert value["preferred_source_id"] == official.id
        assert value["conflicting_evidence_ids"] == [conflict.id]
    finally:
        db.rollback()
        db.close()


def test_social_only_support_stays_low_confidence():
    db = SessionLocal()
    try:
        task, _run = create_task_and_run(db)
        social = add_source(
            db,
            task.id,
            source_type="social",
            url="http://forum.example/thread",
            publisher="",
            is_primary=False,
            index=0,
        )
        evidence = add_evidence(db, social, quality=0.5, index=0)
        claim = add_claim(db, task.id)
        link_evidence(db, claim, evidence)

        summary = claim_verification.cross_validate_claims(db, task=task)

        assert claim.status == models.ClaimStatus.low_confidence.value
        assert summary["low_confidence_claims"] == 1
    finally:
        db.rollback()
        db.close()


def test_no_evidence_becomes_needs_evidence_and_undisclosed_is_preserved():
    db = SessionLocal()
    try:
        task, _run = create_task_and_run(db)
        orphan = add_claim(db, task.id, subject="Cursor", predicate="no_evidence")
        undisclosed_source = add_source(db, task.id, source_type="news", url="https://news.example/update", publisher="News", is_primary=False, index=1)
        context_evidence = add_evidence(db, undisclosed_source, index=1)
        undisclosed = add_claim(
            db,
            task.id,
            status=models.ClaimStatus.undisclosed.value,
            confidence_score=0.64,
            subject="Cursor",
            predicate="enterprise_price_undisclosed",
        )
        db.add(models.ClaimEvidence(claim_id=undisclosed.id, evidence_id=context_evidence.id, relation="context", weight=0.5))
        db.flush()

        summary = claim_verification.cross_validate_claims(db, task=task)

        assert orphan.status == models.ClaimStatus.needs_evidence.value
        assert orphan.confidence_score <= 0.4
        assert orphan.evidence_coverage == 0.0
        assert undisclosed.status == models.ClaimStatus.undisclosed.value
        assert undisclosed.confidence_score == 0.64
        assert summary["claims_without_evidence"] >= 1
        assert summary["undisclosed_claims"] == 1
    finally:
        db.rollback()
        db.close()


def test_human_reviewed_claim_is_not_overridden():
    db = SessionLocal()
    try:
        task, _run = create_task_and_run(db)
        social = add_source(
            db,
            task.id,
            source_type="social",
            url="http://forum.example/thread",
            publisher="",
            is_primary=False,
            index=0,
        )
        evidence = add_evidence(db, social, quality=0.5, index=0)
        claim = add_claim(db, task.id, status=models.ClaimStatus.verified.value, confidence_score=0.9)
        link_evidence(db, claim, evidence)
        db.add(models.ReviewDecision(claim_id=claim.id, decision="accept", reason="人工确认", previous_status="verified", resulting_status="verified"))
        db.flush()

        claim_verification.cross_validate_claims(db, task=task)

        # 人工 accept 后机器验证不回写
        assert claim.status == models.ClaimStatus.verified.value
        assert claim.confidence_score == 0.9
    finally:
        db.rollback()
        db.close()


def test_verify_claims_emits_cross_validation_events():
    db = SessionLocal()
    try:
        task, run = create_task_and_run(db)
        official = add_source(db, task.id, index=0)
        social = add_source(
            db,
            task.id,
            source_type="social",
            url="http://forum.example/thread",
            publisher="",
            is_primary=False,
            index=1,
        )
        support = add_evidence(db, official, index=0)
        conflict = add_evidence(db, social, index=1, quality=0.4)
        verified_claim = add_claim(db, task.id)
        link_evidence(db, verified_claim, support, relation="supports")
        link_evidence(db, verified_claim, conflict, relation="conflicts")
        add_claim(db, task.id, subject="Cursor", predicate="no_evidence")

        summary = research_service.verify_claims(db, task=task)

        assert summary["claims_created"] == 2
        assert summary["conflict_claims"] == 0

        events = (
            db.query(models.ResearchEvent)
            .filter(models.ResearchEvent.run_id == run.id)
            .order_by(models.ResearchEvent.sequence_no)
            .all()
        )
        event_types = [event.type for event in events]
        assert "claim.conflict_detected" in event_types

        conflict_event = next(event for event in events if event.type == "claim.conflict_detected")
        payload = research_service.decode_json(conflict_event.payload_json)
        assert payload["claim_id"] == verified_claim.id
        assert payload["resolution_strategy"] == "prefer_primary_recent_source"
        assert payload["confidence_breakdown"]["conflict_penalty"] > 0

        # 有冲突披露的 claim 不再发 claim.verified；纯验证通过的 claim 才发
        verified_payloads = [research_service.decode_json(e.payload_json) for e in events if e.type == "claim.verified"]
        assert all(item["claim_id"] != verified_claim.id for item in verified_payloads)
    finally:
        db.rollback()
        db.close()
