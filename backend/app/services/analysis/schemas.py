from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ClaimType = Literal["pricing", "feature", "positioning", "strength", "weakness", "market_update", "general"]
ClaimStatusValue = Literal["verified", "low_confidence", "undisclosed", "needs_evidence"]


class ExtractedClaim(BaseModel):
    # 证据 ID 为数据库自增整型；LLM 可能把整型回显为字符串，统一在校验前转回 int。
    # 无法解析的值（如幻觉出的旧格式 ID）映射为 -1，不会命中任何真实证据，后续按"不存在的 evidence_id"过滤。
    evidence_id: int
    subject: str = Field(min_length=1, max_length=160)
    predicate: str = Field(min_length=1, max_length=120)
    value: dict[str, Any] = Field(default_factory=dict)
    claim_type: ClaimType = "general"
    dimension: str = Field(default="general", min_length=1, max_length=120)
    status: ClaimStatusValue = "verified"
    confidence: Literal["high", "medium", "low"] = "medium"
    confidence_score: float = Field(default=0.6, ge=0, le=1)
    display_text: str = Field(min_length=8)
    relation: Literal["supports", "context"] = "supports"

    @field_validator("evidence_id", mode="before")
    @classmethod
    def coerce_evidence_id(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return -1

    @field_validator("predicate")
    @classmethod
    def normalize_predicate(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")[:120]


class ClaimExtractionResult(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


CLAIM_EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "evidence_id": {"type": "integer"},
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "value": {"type": "object", "additionalProperties": True},
                    "claim_type": {
                        "type": "string",
                        "enum": ["pricing", "feature", "positioning", "strength", "weakness", "market_update", "general"],
                    },
                    "dimension": {"type": "string"},
                    "status": {"type": "string", "enum": ["verified", "low_confidence", "undisclosed", "needs_evidence"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                    "display_text": {"type": "string"},
                    "relation": {"type": "string", "enum": ["supports", "context"]},
                },
                "required": [
                    "evidence_id",
                    "subject",
                    "predicate",
                    "value",
                    "claim_type",
                    "dimension",
                    "status",
                    "confidence",
                    "confidence_score",
                    "display_text",
                    "relation",
                ],
            },
        }
    },
    "required": ["claims"],
}
