from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings
from ..db import insert_evidence, insert_relationship, upsert_entity, rows
from ..normalize import normalize_name
from ..schemas import ModelOutput
from .openai_compatible import OpenAICompatibleAdapter
from .rules import RuleBasedAdapter


def _adapter():
    if settings.ai_provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleAdapter(settings.ai_base_url, settings.ai_api_key, settings.ai_model)
    return RuleBasedAdapter()


def run_ai_enrichment(db, project: dict[str, Any]) -> dict[str, Any]:
    sources = rows(db.execute("SELECT * FROM sources WHERE project_id=? ORDER BY collected_at", (project["id"],)))
    assets = rows(db.execute("SELECT * FROM assets WHERE project_id=? ORDER BY asset_type, canonical_value", (project["id"],)))
    adapter = _adapter()
    output: ModelOutput = adapter.analyze(project, sources, assets)
    entity_refs: dict[str, str] = {}
    source_ids = {source["id"] for source in sources}
    source_text = {source["id"]: source.get("raw_content", "") for source in sources}
    for entity in output.entities:
        name = str(entity.get("name", "")).strip()
        entity_type = str(entity.get("entity_type", "")).strip().lower()
        if not name or entity_type not in {"organization", "product", "project", "website"}:
            continue
        source_id = entity.get("source_id") if entity.get("source_id") in source_ids else None
        entity_id = upsert_entity(db, project["id"], entity_type, normalize_name(name), name, "discovered", source_id)
        entity_refs[f"candidate:{entity_type}:{normalize_name(name)}"] = entity_id
    accepted = 0
    needs_review = 0
    for candidate in output.relationships:
        source_id = candidate.evidence_source_id
        quote = candidate.evidence_quote.strip()
        valid_source = source_id in source_ids
        normalized_quote = re.sub(r"\s+", " ", quote).strip().casefold()
        normalized_source = re.sub(r"\s+", " ", source_text.get(source_id, "")).strip().casefold()
        valid_quote = valid_source and bool(normalized_quote) and normalized_quote in normalized_source
        subject_id = _resolve_ref(candidate.subject_type, candidate.subject_ref, entity_refs, assets)
        object_id = _resolve_ref(candidate.object_type, candidate.object_ref, entity_refs, assets)
        if not subject_id or not object_id:
            needs_review += 1
            continue
        status = "confirmed" if valid_quote and candidate.confidence >= 0.8 else "needs_review"
        evidence_id = insert_evidence(db, project["id"], source_id, quote, "model-validated" if valid_quote else "model-evidence-failed", candidate.confidence, "valid" if valid_quote else "invalid") if valid_source else None
        insert_relationship(db, project["id"], candidate.subject_type, subject_id, candidate.predicate, candidate.object_type, object_id, status, candidate.confidence if valid_quote else min(candidate.confidence, 0.25), candidate.rationale, evidence_id)
        if status == "confirmed":
            accepted += 1
        else:
            needs_review += 1
    return {"provider": adapter.name, "explanation": output.explanation, "relationships_accepted": accepted, "relationships_needs_review": needs_review}


def _resolve_ref(ref_type: str, ref: str, entity_refs: dict[str, str], assets: list[dict[str, Any]]) -> str | None:
    if ref_type == "entity":
        return entity_refs.get(ref) or (ref.split(":", 1)[1] if ref.startswith("entity:") else None)
    if ref_type == "asset" and ref.startswith("asset:"):
        asset_id = ref.split(":", 1)[1]
        return asset_id if any(asset["id"] == asset_id for asset in assets) else None
    return None
