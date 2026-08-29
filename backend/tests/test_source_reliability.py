"""来源可靠性确定性评分测试（方案 9.1.3）：类型排序 / 加分项 / 扣分与警告 / 标签边界。"""

from types import SimpleNamespace

from app.services.source_quality import reliability_label, score_source_reliability


def make_source(**overrides) -> SimpleNamespace:
    """构造最小化来源对象：HTTP、无哈希、无发布方，仅保留类型字段。"""
    base = dict(
        source_type="web",
        canonical_url="http://example.com/page",
        url=None,
        publisher="",
        content_hash="",
        index_status="",
        is_primary=False,
        published_at=None,
        retrieved_at=None,
        heat_score=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def full_bonus_source(**overrides) -> SimpleNamespace:
    """构造满加分来源：HTTPS + 哈希 + 发布方 + 时间戳 + 索引 + 一手。"""
    return make_source(
        source_type="official",
        canonical_url="https://example.com/page",
        content_hash="abc123",
        publisher="Example",
        published_at="2026-08-01T00:00:00",
        retrieved_at="2026-08-02T00:00:00",
        index_status="indexed",
        is_primary=True,
        **overrides,
    )


def test_source_type_base_scores_are_ordered():
    scores = {
        source_type: score_source_reliability(make_source(source_type=source_type))["score"]
        for source_type in ["official", "docs", "news", "web", "social"]
    }
    assert scores["official"] > scores["docs"] > scores["news"] > scores["web"] > scores["social"]
    # 未识别类型回退到 0.55 基准：HTTP(-0.05) + 缺哈希(-0.08) → 0.42
    assert score_source_reliability(make_source(source_type="unknown_type"))["score"] == 0.42


def test_positive_factors_increase_score():
    minimal = score_source_reliability(make_source())["score"]
    with_hash = score_source_reliability(make_source(canonical_url="https://example.com", content_hash="h1"))["score"]
    full = score_source_reliability(full_bonus_source())["score"]

    assert with_hash > minimal  # HTTPS + 内容哈希
    assert full > with_hash  # 一手来源 / 发布方 / 时间戳 / 索引
    assert full == 1.0  # official 满加分超上限后被 clamp 到 1.0


def test_missing_content_hash_and_http_trigger_warnings_and_deduction():
    result = score_source_reliability(make_source())
    assert result["warnings"]
    assert any("哈希" in warning for warning in result["warnings"])
    assert any("HTTPS" in warning for warning in result["warnings"])

    https_hash = score_source_reliability(make_source(canonical_url="https://example.com", content_hash="h1"))
    assert https_hash["score"] > result["score"]
    assert not any("哈希" in warning for warning in https_hash["warnings"])


def test_gov_and_edu_domains_get_bonus():
    gov = score_source_reliability(make_source(canonical_url="https://www.example.gov/report", content_hash="h1"))
    edu = score_source_reliability(make_source(canonical_url="https://www.example.edu/paper", content_hash="h1"))
    plain = score_source_reliability(make_source(canonical_url="https://www.example.com/report", content_hash="h1"))

    assert gov["score"] > plain["score"]
    assert edu["score"] > plain["score"]
    assert gov["score"] > edu["score"]


def test_social_sources_carry_warning_and_heat_bonus():
    social = score_source_reliability(make_source(source_type="social"))
    assert any("社区" in warning or "社交" in warning for warning in social["warnings"])

    hot = score_source_reliability(make_source(source_type="social", heat_score=0.85))
    cold = score_source_reliability(make_source(source_type="social", heat_score=0.2))
    assert hot["score"] > cold["score"]
    assert any("热度" in reason for reason in hot["reasons"])


def test_reliability_label_boundaries():
    assert reliability_label(0.8) == "high"
    assert reliability_label(0.79) == "medium"
    assert reliability_label(0.6) == "medium"
    assert reliability_label(0.59) == "low"

    result = score_source_reliability(make_source())
    assert result["label"] == reliability_label(result["score"])
