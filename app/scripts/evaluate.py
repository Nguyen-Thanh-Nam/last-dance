from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'BE'))

from app.config import settings
from app.db import db_session, init_db
from app.normalize import normalize_name
from app.pipeline import project_snapshot
from app.sample_data import load_demo
from app.ai.service import run_ai_enrichment


def scores(truth: set[str], predicted: set[str]) -> dict:
    tp, fp, fn = len(truth & predicted), len(predicted - truth), len(truth - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'precision': round(precision, 4), 'recall': round(recall, 4), 'f1': round(f1, 4),
            'true_positive': tp, 'false_positive': fp, 'false_negative': fn,
            'predicted': len(predicted), 'ground_truth': len(truth)}


def relation_key(subject: str, predicate: str, object_value: str) -> str:
    # URLs are case sensitive in path/query; only names are case folded.
    return f'{normalize_name(subject) if "://" not in subject else subject}|{predicate}|{object_value}'


def evaluate_snapshot(snapshot, ground_truth):
    truth_assets = {f"{a['asset_type']}|{a['canonical_value']}" for a in ground_truth['assets'] if a.get('label') == 'true'}
    seeds = set(ground_truth.get('excluded_seed_hosts', [snapshot['project']['root_domain']]))
    predicted_assets = {f"{a['asset_type']}|{a['canonical_value']}" for a in snapshot['assets']
                        if a['asset_type'] in {'host', 'endpoint'} and a['canonical_value'] not in seeds
                        and a['status'] in {'confirmed', 'related'}}
    truth_relations = {relation_key(r['subject_name'], r['predicate'], r['object_value'])
                       for r in ground_truth['relationships'] if r.get('label') == 'true'}
    labels = {e['id']: e['display_name'] for e in snapshot['entities']}
    labels.update({a['id']: a['canonical_value'] for a in snapshot['assets']})
    labels.update({a['id']: a['profile_url'] for a in snapshot.get('social_accounts', [])})
    labels.update({p['id']: p['permalink'] for p in snapshot.get('social_posts', [])})
    records = [(r, relation_key(labels.get(r['subject_id'], r['subject_id']), r['predicate'],
                               labels.get(r['object_id'], r['object_id']))) for r in snapshot['relationships']]
    concluded = {key for rel, key in records if rel['status'] in {'confirmed', 'related'}}
    valid = [r for r in snapshot['relationships'] if r.get('evidence_id') and r.get('quote')
             and r.get('source_url') and r.get('source_collected_at') and r.get('content_hash') and r.get('validity') == 'valid']
    buckets = {name: scores(truth_relations, {key for rel, key in records if low <= rel['confidence'] < high and rel['status'] in {'confirmed','related'}})
               for name, low, high in [('high', .8, 1.01), ('medium', .5, .8), ('low', 0, .5)]}
    entity_types = set(ground_truth.get('evaluated_entity_types', ['product', 'project']))
    truth_entities = {f"{e['entity_type']}|{normalize_name(e['name'])}" for e in ground_truth.get('entities', []) if e.get('label') == 'true'}
    predicted_entities = {f"{e['entity_type']}|{normalize_name(e['display_name'])}" for e in snapshot['entities'] if e['entity_type'] in entity_types}
    predicates = {r['predicate'] for r in ground_truth['relationships']} | {r['predicate'] for r in snapshot['relationships']}
    predicate_metrics = {predicate: scores({k for k in truth_relations if k.split('|')[1] == predicate},
                                          {key for rel, key in records if rel['predicate'] == predicate and rel['status'] in {'confirmed','related'}}) for predicate in sorted(predicates)}
    return {'asset_scores': scores(truth_assets, predicted_assets), 'relation_scores': scores(truth_relations, concluded),
            'entity_scores': scores(truth_entities, predicted_entities) if ground_truth.get('entities') else {'status': 'not_labeled'},
            'relation_scores_by_predicate': predicate_metrics,
            'confidence_bucket_metrics': buckets,
            'traceability_rate': round(len(valid)/len(records),4) if records else 0.0,
            'coverage': round(len(concluded)/len(records),4) if records else 0.0,
            'needs_review_count': sum(r['status']=='needs_review' for r, _ in records),
            'false_positive_assets': sorted(predicted_assets-truth_assets), 'false_negative_assets': sorted(truth_assets-predicted_assets),
            'false_positive_relations': sorted(concluded-truth_relations), 'false_negative_relations': sorted(truth_relations-concluded),
            'collector_duration_ms': sum(log.get('duration_ms',0) for log in snapshot['collector_logs'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--with-ai', action='store_true', help='Run configured real provider after the same B0 snapshots')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--snapshot', type=Path, help='Evaluate an exported report.json instead of the synthetic fixture')
    parser.add_argument('--comparison-snapshot', type=Path, help='B1 report.json with the same source hashes as --snapshot')
    parser.add_argument('--ground-truth', type=Path, default=ROOT/'data/evaluation_ground_truth.json')
    args = parser.parse_args()
    truth = json.loads(args.ground_truth.read_text(encoding='utf-8'))
    if args.snapshot:
        baseline = json.loads(args.snapshot.read_text(encoding='utf-8'))
        output = {'fixture': truth['fixture'], 'B0': evaluate_snapshot(baseline, truth), 'B1': {'status': 'not_run'}}
        if args.comparison_snapshot:
            comparison = json.loads(args.comparison_snapshot.read_text(encoding='utf-8'))
            baseline_hashes = {s['content_hash'] for s in baseline['sources']}
            comparison_hashes = {s['content_hash'] for s in comparison['sources']}
            if baseline_hashes != comparison_hashes or baseline['project']['root_domain'] != comparison['project']['root_domain']:
                parser.error('B0/B1 require the same root-domain seed and snapshot content hashes')
            output['B1'] = {'status': 'completed', **evaluate_snapshot(comparison, truth)}
        rendered = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered+'\n', encoding='utf-8')
        print(rendered)
        return
    if args.comparison_snapshot:
        parser.error('--comparison-snapshot requires --snapshot')
    original_db = settings.database_path
    with tempfile.TemporaryDirectory(prefix='surface-evaluation-') as temporary:
        try:
            object.__setattr__(settings, 'database_path', str(Path(temporary)/'evaluation.db'))
            init_db()
            result = load_demo()
            with db_session() as db:
                baseline = project_snapshot(db, result['project_id'])
            output = {'fixture': truth['fixture'], 'B0': evaluate_snapshot(baseline, truth),
                      'B1': {'status': 'not_run', 'reason': 'Use --with-ai and configure a real provider.'},
                      'limitations': ['Synthetic fixture only; this is functional verification, not research validation.',
                                      'No independent human labeling, held-out organizations or Internet reachability measurement is claimed.',
                                      'Known root-domain seeds are excluded; every concluded in-scope host/endpoint prediction is scored, including false positives.']}
            if args.with_ai:
                if settings.ai_provider not in {'openai', 'openai-compatible'} or not all((settings.ai_base_url, settings.ai_api_key, settings.ai_model)):
                    output['B1'] = {'status': 'not_run', 'reason': 'Real provider configuration is incomplete.'}
                else:
                    try:
                        with db_session() as db:
                            ai = run_ai_enrichment(db, baseline['project'])
                            enhanced = project_snapshot(db, result['project_id'])
                        output['B1'] = {'status': 'completed', 'provider': ai['provider'], 'model': settings.ai_model,
                                        **evaluate_snapshot(enhanced, truth)}
                    except Exception as exc:
                        output['B1'] = {'status': 'failed', 'reason': str(exc)}
            rendered = json.dumps(output, ensure_ascii=False, indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered+'\n', encoding='utf-8')
            print(rendered)
        finally:
            object.__setattr__(settings, 'database_path', original_db)


if __name__ == '__main__':
    main()
