from __future__ import annotations

import json
import urllib.request
from typing import Any

from ..schemas import ModelOutput


class OpenAICompatibleAdapter:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def analyze(self, project: dict[str, Any], sources: list[dict[str, Any]], assets: list[dict[str, Any]]) -> ModelOutput:
        if not (self.base_url and self.api_key and self.model):
            raise RuntimeError("AI_PROVIDER=openai-compatible requires AI_BASE_URL, AI_API_KEY, and AI_MODEL")
        evidence_catalog = [{"id": source["id"], "url": source.get("source_url"), "text": source.get("raw_content", "")[:6000]} for source in sources]
        asset_catalog = [{"id": asset["id"], "type": asset["asset_type"], "value": asset["display_value"], "source_id": asset.get("source_id")} for asset in assets]
        prompt = {
            "task": "Extract entities and evidence-backed relationships. Use only source ids and asset ids from the catalogs; never invent URLs or sources.",
            "project": {"organization": project["organization_name"], "root_domain": project["root_domain"]},
            "sources": evidence_catalog,
            "assets": asset_catalog,
            "output_schema": {"entities": [{"entity_type": "organization|product|project|website", "name": "string", "source_id": "source id or null"}], "relationships": [{"subject_type": "entity|asset", "subject_ref": "entity id or candidate:product:name", "predicate": "string", "object_type": "entity|asset", "object_ref": "asset:id or entity id", "evidence_source_id": "source id", "evidence_quote": "verbatim quote", "rationale": "string", "confidence": "0..1"}], "explanation": "string"},
        }
        request_body = json.dumps({"model": self.model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": "Return JSON only."}, {"role": "user", "content": json.dumps(prompt)}]}).encode()
        request = urllib.request.Request(f"{self.base_url}/chat/completions", data=request_body, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return ModelOutput.model_validate(json.loads(content))
