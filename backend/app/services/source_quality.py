"""Explainable source reliability scoring.

This is a lightweight, deterministic layer used by API serializers. It does not
replace claim verification; it gives the UI and later ranking logic a transparent
source-level prior before multi-source cross-validation is fully persisted.
"""

from typing import Any
from urllib.parse import urlparse

SOURCE_TYPE_BASE_SCORE = {
    "official": 0.82,
    "docs": 0.78,
    "news": 0.7,
    "pdf": 0.68,
    "upload": 0.64,
    "web": 0.58,
    "manual": 0.56,
    "social": 0.48,
    "community": 0.48,
}


def score_source_reliability(source: Any) -> dict[str, Any]:
    source_type = str(getattr(source, "source_type", "") or "web").strip().lower()
    url = str(getattr(source, "canonical_url", "") or getattr(source, "url", "") or "")
    publisher = str(getattr(source, "publisher", "") or "").strip()
    content_hash = str(getattr(source, "content_hash", "") or "").strip()
    index_status = str(getattr(source, "index_status", "") or "").strip().lower()
    parsed = urlparse(url)

    score = SOURCE_TYPE_BASE_SCORE.get(source_type, 0.55)
    reasons = [f"来源类型基准：{source_type or 'unknown'}"]
    warnings: list[str] = []

    if getattr(source, "is_primary", False):
        score += 0.08
        reasons.append("标记为一手来源")
    if parsed.scheme == "https":
        score += 0.03
        reasons.append("使用 HTTPS 链接")
    else:
        score -= 0.05
        warnings.append("来源不是 HTTPS，后续应优先寻找更稳定出处")
    if content_hash:
        score += 0.04
        reasons.append("已保存内容哈希，可追溯快照")
    else:
        score -= 0.08
        warnings.append("缺少内容哈希，引用链完整性不足")
    if publisher:
        score += 0.03
        reasons.append(f"发布方：{publisher}")
    else:
        warnings.append("发布方未知，需要交叉验证")
    if getattr(source, "published_at", None):
        score += 0.02
        reasons.append("包含发布时间")
    if getattr(source, "retrieved_at", None):
        score += 0.02
        reasons.append("包含抓取时间")
    if index_status in {"indexed", "completed"}:
        score += 0.02
        reasons.append("已进入检索索引")

    host = parsed.netloc.lower()
    if host.endswith(".gov") or ".gov." in host:
        score += 0.08
        reasons.append("政府/监管域名")
    if host.endswith(".edu") or ".edu." in host:
        score += 0.06
        reasons.append("教育/研究机构域名")
    if source_type in {"social", "community"}:
        warnings.append("社区/社交来源适合发现观点和争议，不能单独作为关键事实依据")
        heat_score = getattr(source, "heat_score", None)
        if isinstance(heat_score, (int, float)) and heat_score >= 0.7:
            score += 0.04
            reasons.append("社交热度较高，可作为舆情信号")

    score = min(max(score, 0.0), 1.0)
    return {
        "score": round(score, 2),
        "label": reliability_label(score),
        "reasons": reasons[:5],
        "warnings": warnings[:4],
    }


def reliability_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"
