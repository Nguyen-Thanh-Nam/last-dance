from __future__ import annotations

from typing import Any, Literal
from datetime import datetime
import ipaddress
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ConfigDict, field_validator

from .normalize import normalize_domain, normalize_url


class AuthorizedScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["hostname", "domain", "ip", "cidr"]
    value: str
    allowed_tests: list[Literal["http", "tls"]] = Field(default_factory=lambda: ["http", "tls"], min_length=1)
    expires_at: datetime | None = None
    allow_private: bool = False

    @field_validator("expires_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at requires a timezone")
        return value

    @field_validator("value")
    @classmethod
    def scope_value(cls, value, info):
        kind = info.data.get("kind")
        if kind == "cidr":
            return str(ipaddress.ip_network(value, strict=False))
        if kind == "ip":
            return str(ipaddress.ip_address(value))
        value = normalize_domain(value)
        if value.startswith("*."):
            raise ValueError("use domain scope for subdomains")
        return value


class SocialPostInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permalink: str
    content: str = ""
    published_at: datetime | None = None

    @field_validator("permalink")
    @classmethod
    def url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("social URL must be HTTP(S) without credentials")
        return normalize_url(value)


class SocialAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    platform: str | None = None
    handle: str = ""
    verification_evidence: str = ""
    content: str = ""
    posts: list[SocialPostInput] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def url_validator(cls, value):
        return SocialPostInput.url(value)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    organization_name: str = Field(min_length=2, max_length=200)
    official_website: str = Field(min_length=4, max_length=500)
    root_domain: str | None = None
    allowed_domains: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    known_social_accounts: list[SocialAccountInput] = Field(default_factory=list)
    authorized_assets: list[str] = Field(default_factory=list)
    authorized_scopes: list[AuthorizedScope] = Field(default_factory=list)
    mode: Literal["passive", "authorized"] = "passive"
    notes: str = ""

    @field_validator("official_website")
    @classmethod
    def website_url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("official website requires an HTTP(S) URL without credentials")
        return normalize_url(value)

    @field_validator("allowed_domains")
    @classmethod
    def domains(cls, values):
        result = [normalize_domain(v) for v in values]
        if any(v.startswith("*.") for v in result):
            raise ValueError("allowed_domains uses concrete domain names")
        return result

    @field_validator("root_domain")
    @classmethod
    def root(cls, value):
        return normalize_domain(value) if value else None

    @field_validator("authorized_assets")
    @classmethod
    def authorized(cls, values):
        for value in values:
            if "://" in value:
                cls.website_url(value)
            else:
                normalize_domain(value)
        return values


class DomainSetup(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    domain: str = Field(min_length=3, max_length=320)

    @field_validator("domain")
    @classmethod
    def domain_name(cls, value):
        if "://" in value:
            parts = urlsplit(value)
            if (parts.scheme not in {"http", "https"} or parts.username or parts.password
                    or parts.port is not None or parts.path not in {"", "/"}
                    or parts.query or parts.fragment):
                raise ValueError("Chỉ nhập domain, ví dụ example.org")
            value = parts.hostname or ""
        host = normalize_domain(value)
        if host.startswith("*.") or "." not in host:
            raise ValueError("Nhập domain đầy đủ, ví dụ example.org")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return host
        raise ValueError("Nhập domain, không nhập địa chỉ IP")


class CollectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collectors: list[str] = Field(default_factory=list)
    profile: Literal["standard", "full"] = "standard"
    demo: bool = False
    background: bool = True


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["confirmed", "related", "needs_review", "rejected"]
    rationale: str | None = None
    reviewer: str = Field(default="local-user", min_length=1, max_length=200)


class ModelRelationship(BaseModel):
    subject_type: Literal["entity", "asset"]
    subject_ref: str
    predicate: Literal["develops", "official_website_of", "uses_domain", "subdomain_of", "resolves_to", "aliases_to", "certificate_contains", "official_channel_of", "depends_on", "controlled_by", "PRODUCT_USES_WEBSITE", "OFFICIAL_SOCIAL_ACCOUNT", "POST_MENTIONS_PRODUCT", "POST_LINKS_TO_ENDPOINT"]
    relation_class: Literal["owned", "operated", "used", "partner", "mentioned", "unknown"] = "unknown"
    object_type: Literal["entity", "asset"]
    object_ref: str
    evidence_source_id: str
    evidence_quote: str
    rationale: str = ""
    confidence: float = Field(ge=0, le=1)


class AssetReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    classification: Literal["controlled", "third_party", "candidate", "insufficient_evidence", "rejected"]
    reviewer: str = Field(default="local-user", min_length=1, max_length=200)
    rationale: str = Field(min_length=2, max_length=2000)


class EvidenceAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_id: str
    quote: str = Field(min_length=2, max_length=2000)
    role: Literal["supports", "refutes"] = "supports"
    reviewer: str = Field(default="local-user", min_length=1, max_length=200)


class ModelEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    entity_type: Literal["organization", "product", "project", "website"]
    name: str = Field(min_length=2, max_length=200)
    source_id: str | None = None


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[ModelEntity] = Field(default_factory=list)
    relationships: list[ModelRelationship] = Field(default_factory=list)
    explanation: str = ""
