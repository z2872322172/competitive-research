from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ClaimType = Literal["pricing", "feature", "positioning", "strength", "weakness", "market_update", "general"]
ClaimStatusValue = Literal["verified", "low_confidence", "undisclosed", "needs_evidence"]


class ExtractedClaim(BaseModel):
    evidence_id: str
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
                    "evidence_id": {"type": "string"},
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
