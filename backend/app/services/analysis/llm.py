import json
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.services import observability
from app.services.analysis.schemas import CLAIM_EXTRACTION_JSON_SCHEMA, ClaimExtractionResult


class ClaimExtractionLLM(Protocol):
    def extract_claims(self, *, prompt: str, evidence_payload: list[dict]) -> ClaimExtractionResult:
        """Extract structured claims from evidence payload."""


class LLMUnavailable(RuntimeError):
    pass


RESPONSE_FORMAT_ERROR_MARKERS = (
    "response_format",
    "unavailable now",
)

JSON_OBJECT_OUTPUT_CONTRACT = (
    "Respond with a single json object: "
    '{"claims": [{"evidence_id": int, "subject": str, "predicate": str, "value": {}, '
    '"claim_type": "pricing|feature|positioning|strength|weakness|market_update|general", '
    '"dimension": str, "status": "verified|low_confidence|undisclosed|needs_evidence", '
    '"confidence": "high|medium|low", "confidence_score": 0.0-1.0, '
    '"display_text": str, "relation": "supports|context"}]}'
)


class OpenAICompatibleClaimExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        disable_thinking: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.disable_thinking = disable_thinking
        # 部分兼容服务（如 DeepSeek）不支持 json_schema strict 模式，首次 400 后降级为 json_object。
        self._use_json_object = False

    def extract_claims(self, *, prompt: str, evidence_payload: list[dict]) -> ClaimExtractionResult:
        messages = self._build_messages(prompt=prompt, evidence_payload=evidence_payload)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        started_wall = datetime.now(timezone.utc)
        started_at = perf_counter()
        try:
            body = self._request_with_fallback(messages, headers)
        except Exception as exc:
            observability.record_generation(
                name="claim_extraction",
                model=self.model,
                input_messages=messages,
                started_at=started_wall,
                duration_ms=int((perf_counter() - started_at) * 1000),
                error=str(exc),
            )
            raise
        duration_ms = int((perf_counter() - started_at) * 1000)
        content = body["choices"][0]["message"]["content"]
        observability.record_generation(
            name="claim_extraction",
            model=self.model,
            input_messages=messages,
            output_content=content,
            usage=body.get("usage"),
            started_at=started_wall,
            duration_ms=duration_ms,
            metadata_extra={
                "evidence_count": len(evidence_payload),
                "response_format": "json_object" if self._use_json_object else "json_schema",
            },
        )
        return parse_claim_extraction_content(content)

    def _request_with_fallback(self, messages: list[dict], headers: dict) -> dict:
        try:
            return self._request(messages, headers)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and not self._use_json_object:
                detail = exc.response.text or ""
                if any(marker in detail for marker in RESPONSE_FORMAT_ERROR_MARKERS):
                    self._use_json_object = True
                    # json_object 要求提示词中包含 "json"，降级后重建消息。
                    return self._request(self._json_object_messages(messages), headers)
            raise

    def _request(self, messages: list[dict], headers: dict) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if self._use_json_object:
            payload["response_format"] = {"type": "json_object"}
        else:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "claim_extraction_result",
                    "schema": CLAIM_EXTRACTION_JSON_SCHEMA,
                    "strict": True,
                },
            }
        if self.disable_thinking:
            # DashScope 兼容模式的 extra_body 参数：关闭思考模式，省 token 提速。
            payload["enable_thinking"] = False
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    def _build_messages(self, *, prompt: str, evidence_payload: list[dict]) -> list[dict]:
        system_content = (
            "You extract concise, verifiable competitive-research claims from evidence. "
            "Every claim must cite exactly one supplied evidence_id. "
            "Do not invent facts that are not present in the evidence."
        )
        return [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": json.dumps(
                    {"research_prompt": prompt, "evidence": evidence_payload}, ensure_ascii=False
                ),
            },
        ]

    def _json_object_messages(self, messages: list[dict]) -> list[dict]:
        updated = list(messages)
        updated[0] = {
            "role": "system",
            "content": f"{updated[0]['content']} {JSON_OBJECT_OUTPUT_CONTRACT}",
        }
        return updated


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
        # 证据 ID 为自增整型：直接透传（int 或可转 int 的字符串都交给 schema 校验器统一处理）
        "evidence_id": item.get("evidence_id"),
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
        disable_thinking=settings.llm_disable_thinking,
    )
