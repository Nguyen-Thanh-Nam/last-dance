from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    official_website: str = Field(min_length=4, max_length=500)
    root_domain: str | None = None
    allowed_domains: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    known_social_accounts: list[dict[str, Any]] = Field(default_factory=list)
    authorized_assets: list[str] = Field(default_factory=list)
    mode: Literal["passive", "authorized"] = "passive"
    notes: str = ""


class CollectRequest(BaseModel):
    collectors: list[str] = Field(default_factory=lambda: ["passive_web", "dns", "certificate_transparency", "rdap", "social_osint", "ai"])
    demo: bool = False


class ClaimReview(BaseModel):
    status: Literal["confirmed", "related", "needs_review", "rejected"]
    rationale: str | None = None


class ModelRelationship(BaseModel):
    subject_type: Literal["entity", "asset"]
    subject_ref: str
    predicate: str
    relation_class: Literal["owned", "operated", "used", "partner", "mentioned", "unknown"] = "unknown"
    object_type: Literal["entity", "asset"]
    object_ref: str
    evidence_source_id: str
    evidence_quote: str
    rationale: str = ""
    confidence: float = Field(ge=0, le=1)


class ModelOutput(BaseModel):
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[ModelRelationship] = Field(default_factory=list)
    explanation: str = ""
