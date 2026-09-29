from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db import db_session, init_db
from app.normalize import normalize_endpoint, normalize_name
from app.pipeline import project_snapshot
from app.sample_data import load_demo


def scores(truth: set[str], predicted: set[str]) -> dict[str, float | int]:
    tp = len(truth & predicted)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "true_positive": tp, "predicted": len(predicted), "ground_truth": len(truth)}


def relation_key(subject: str, predicate: str, object_value: str) -> str:
    return f"{normalize_name(subject)}|{predicate}|{object_value.casefold()}"


def main() -> None:
    init_db()
    ground_truth = json.loads((ROOT / "data/evaluation_ground_truth.json").read_text(encoding="utf-8"))
    result = load_demo()
    with db_session() as db:
        snapshot = project_snapshot(db, result["project_id"])
    assert snapshot

    truth_assets = {item["canonical_value"] for item in ground_truth["assets"]}
    predicted_assets = {a["canonical_value"] for a in snapshot["assets"] if a["asset_type"] in {"host", "endpoint"} and a["canonical_value"] in truth_assets}

    truth_relations = {relation_key(item["subject_name"], item["predicate"], item["object_value"]) for item in ground_truth["relationships"]}
    entity_names = {e["id"]: e["display_name"] for e in snapshot["entities"]}
    asset_values = {a["id"]: a["canonical_value"] for a in snapshot["assets"]}
    social_values = {a["id"]: a["profile_url"] for a in snapshot.get("social_accounts", [])}
    post_values = {p["id"]: p["permalink"] for p in snapshot.get("social_posts", [])}
    predicted_relations: set[str] = set()
    relation_records = []
    for rel in snapshot["relationships"]:
        subject = entity_names.get(rel["subject_id"], post_values.get(rel["subject_id"], social_values.get(rel["subject_id"], rel["subject_id"])))
        object_value = asset_values.get(rel["object_id"], social_values.get(rel["object_id"], entity_names.get(rel["object_id"], rel["object_id"])))
        key = relation_key(subject, rel["predicate"], object_value)
        predicted_relations.add(key)
        relation_records.append((rel, key))

    valid_evidence = [r for r in snapshot["relationships"] if r.get("evidence_id") and r.get("quote") and r.get("source_url") and r.get("validity", "valid") != "invalid"]
    bucket_metrics = {}
    for bucket, predicate in (("confirmed", lambda r: r["status"] == "confirmed"), ("related_probable", lambda r: r["status"] in {"related", "confirmed"}), ("needs_review", lambda r: r["status"] == "needs_review")):
        bucket_keys = {key for rel, key in relation_records if predicate(rel)}
        bucket_metrics[bucket] = scores(truth_relations, bucket_keys)

    before = ["https://app.acme.example/login?next=/dashboard&tenant=acme", "https://app.acme.example/login?tenant=acme&next=/other"]
    after = {normalize_endpoint(value) for value in before}
    total_duration = sum(int(log.get("duration_ms", 0)) for log in snapshot.get("collector_logs", []))
    false_positive_relations = sorted(predicted_relations - truth_relations)
    false_negative_relations = sorted(truth_relations - predicted_relations)
    output = {
        "fixture": ground_truth["fixture"],
        "asset_scores": scores(truth_assets, predicted_assets),
        "relation_scores": scores(truth_relations, predicted_relations),
        "confidence_bucket_metrics": bucket_metrics,
        "traceability_rate": round(len(valid_evidence) / len(snapshot["relationships"]) if snapshot["relationships"] else 0.0, 4),
        "source_reachable_rate": "not_run_offline_fixture",
        "collector_duration_ms": total_duration,
        "duplicate_count_before": len(before),
        "duplicate_count_after": len(after),
        "ai_provider": result["ai"]["provider"],
        "ai_comparison": "not_run; configure AI_PROVIDER=openai-compatible and rerun to measure a real model" if settings.ai_provider == "rules-demo" else "configured provider executed; compare this output with a rules-demo run",
        "false_positive_relations": false_positive_relations,
        "false_negative_relations": false_negative_relations,
        "notes": ["Fixture is synthetic and manually labeled.", "No external source reachability score is claimed in offline mode.", "Review false positives and false negatives in docs/EXPERIMENTS.md."],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
