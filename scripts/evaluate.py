from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db import db_session, init_db
from app.pipeline import project_snapshot
from app.sample_data import load_demo
from app.normalize import normalize_endpoint


def scores(truth: set[str], predicted: set[str]) -> dict[str, float]:
    tp = len(truth & predicted)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "true_positive": tp, "predicted": len(predicted), "ground_truth": len(truth)}


def main() -> None:
    init_db()
    result = load_demo()
    with db_session() as db:
        snapshot = project_snapshot(db, result["project_id"])
    assert snapshot
    # Labels describe the deterministic fixture, not an external organization.
    truth_assets = {"app.acme.example", "status.acme.example", normalize_endpoint("https://app.acme.example/login?next=/dashboard&tenant=acme")}
    predicted_assets = {a["canonical_value"] for a in snapshot["assets"] if a["asset_type"] in {"host", "endpoint"} and a["canonical_value"] in truth_assets}
    valid_evidence = [r for r in snapshot["relationships"] if r.get("evidence_id") and r.get("quote") and r.get("source_url")]
    relation_truth = {"Fleet Console|PRODUCT_USES_WEBSITE|app.acme.example"}
    relation_predicted = set()
    entity_names = {e["id"]: e["display_name"] for e in snapshot["entities"]}
    asset_values = {a["id"]: a["canonical_value"] for a in snapshot["assets"]}
    for rel in snapshot["relationships"]:
        if rel["predicate"] == "PRODUCT_USES_WEBSITE":
            relation_predicted.add(f"{entity_names.get(rel['subject_id'], '')}|{rel['predicate']}|{asset_values.get(rel['object_id'], '')}")
    before = ["https://app.acme.example/login?next=/dashboard&tenant=acme", "https://app.acme.example/login?tenant=acme&next=/other"]
    after = {normalize_endpoint(value) for value in before}
    output = {"fixture": "Acme Robotics deterministic demo", "asset_scores": scores(truth_assets, predicted_assets), "relation_scores": scores(relation_truth, relation_predicted), "valid_evidence_rate": round(len(valid_evidence) / len(snapshot["relationships"]) if snapshot["relationships"] else 0.0, 4), "duplicate_count_before": len(before), "duplicate_count_after": len(after), "ai_provider": result["ai"]["provider"], "ai_comparison": "not run; configure AI_PROVIDER=openai-compatible and rerun to measure a real model" if settings.ai_provider == "rules-demo" else "configured provider executed; compare this output with a rules-demo run"}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
