import json
import re
from typing import Any
from typing import Protocol

import httpx

from app.config import Settings
from app.services.analysis.schemas import CLAIM_EXTRACTION_JSON_SCHEMA, ClaimExtractionResult


class ClaimExtractionLLM(Protocol):
    def extract_claims(self, *, prompt: str, evidence_payload: list[dict]) -> ClaimExtractionResult:
        """Extract structured claims from evidence payload."""


class LLMUnavailable(RuntimeError):
    pass


class OpenAICompatibleClaimExtractor:
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout_seconds: float) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def extract_claims(self, *, prompt: str, evidence_payload: list[dict]) -> ClaimExtractionResult:
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract concise, verifiable competitive-research claims from evidence. "
                    "Every claim must cite exactly one supplied evidence_id. "
                    "Do not invent facts that are not present in the evidence."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"research_prompt": prompt, "evidence": evidence_payload}, ensure_ascii=False),
            },
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "claim_extraction_result",
                    "schema": CLAIM_EXTRACTION_JSON_SCHEMA,
                    "strict": True,
                },
            },
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"]
        return parse_claim_extraction_content(content)


def parse_claim_extraction_content(content: str) -> ClaimExtractionResult:
    """Parse and repair common non-strict JSON responses from LLM providers."""
    raw = extract_json_text(content)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_claim_json:{exc.msg}") from exc
    repaired = repair_claim_payload(payload)
    return ClaimExtractionResult.model_validate(repaired)


def extract_json_text(content: str) -> str:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    object_start = text.find("{")
    array_start = text.find("[")
    starts = [index for index in [object_start, array_start] if index >= 0]
    if not starts:
        raise ValueError("claim_json_not_found")
    start = min(starts)
    end_char = "}" if text[start] == "{" else "]"
    end = text.rfind(end_char)
    if end < start:
        raise ValueError("claim_json_not_closed")
    return text[start : end + 1]


def repair_claim_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = {"claims": payload}
    if not isinstance(payload, dict):
        raise ValueError("claim_payload_must_be_object")

    claims = payload.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError("claim_payload_claims_must_be_array")
    return {"claims": [repair_claim(item) for item in claims if isinstance(item, dict)]}


def repair_claim(item: dict[str, Any]) -> dict[str, Any]:
    confidence_score = coerce_float(item.get("confidence_score"), default=0.6)
    claim_type = normalize_choice(
        item.get("claim_type"),
        {
            "pricing_signal": "pricing",
            "price": "pricing",
            "features": "feature",
            "market": "market_update",
            "position": "positioning",
        },
        default="general",
        allowed={"pricing", "feature", "positioning", "strength", "weakness", "market_update", "general"},
    )
    status = normalize_choice(
        item.get("status"),
        {"certain": "verified", "supported": "verified", "unknown": "undisclosed", "unsupported": "needs_evidence"},
        default="verified",
        allowed={"verified", "low_confidence", "undisclosed", "needs_evidence"},
    )
    confidence = normalize_choice(
        item.get("confidence"),
        {"very_high": "high", "medium_high": "high", "uncertain": "low"},
        default=confidence_from_score(confidence_score),
        allowed={"high", "medium", "low"},
    )
    relation = normalize_choice(
        item.get("relation"),
        {"supporting": "supports", "supported_by": "supports", "background": "context"},
        default="supports",
        allowed={"supports", "context"},
    )

    return {
        "evidence_id": str(item.get("evidence_id", "")).strip(),
        "subject": str(item.get("subject", "")).strip(),
        "predicate": str(item.get("predicate", "states_fact")).strip() or "states_fact",
        "value": item.get("value") if isinstance(item.get("value"), dict) else {},
        "claim_type": claim_type,
        "dimension": str(item.get("dimension", claim_type)).strip() or claim_type,
        "status": status,
        "confidence": confidence,
        "confidence_score": min(max(confidence_score, 0.0), 1.0),
        "display_text": str(item.get("display_text", "")).strip(),
        "relation": relation,
    }


def normalize_choice(value: Any, aliases: dict[str, str], *, default: str, allowed: set[str]) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in allowed else default


def coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def confidence_from_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score < 0.45:
        return "low"
    return "medium"


def build_llm_extractor(settings: Settings) -> ClaimExtractionLLM | None:
    api_key = settings.llm_api_key or settings.openai_api_key
    if not api_key:
        return None
    if settings.llm_provider not in {"openai", "openai_compatible"}:
        raise LLMUnavailable(f"unsupported_llm_provider:{settings.llm_provider}")
    return OpenAICompatibleClaimExtractor(
        api_key=api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
