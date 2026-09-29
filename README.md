# Surface Map AI

Evidence-backed external attack surface discovery for an organization. The project is an offline-first MVP for a graduation project: it collects public technical and non-technical signals, normalizes them, links them only when a source-backed claim exists, and produces a browsable report.

## What is included

- Project scope with organization, official website, root domain, allowlist, `passive` and `authorized` modes, notes, run status, and collector logs.
- Independent passive website, DNS, and authorized HTTP/crawl collectors. Authorized requests are bounded by page/depth/delay settings, check every host against the allowlist, block private/loopback hosts, and validate redirects before following them.
- Normalized `Domain`/`Host`, `Website`, `Endpoint`, `Parameter`, and DNS assets, plus `Organization`, `Product`, `Project`, and `Website` entities.
- Sources retain URL/name, collection time, title, raw content, and metadata. Relationships retain predicate, status (`confirmed`, `related`, `needs_review`), confidence, rationale, and an evidence quote.
- `rules-demo` AI adapter is deterministic and clearly labeled. `openai-compatible` can call a configurable `/chat/completions` provider. Model output is schema-validated; source IDs and quotes are checked against collected content, and unsupported claims become `needs_review`.
- Browser UI for project creation, demo loading, collection, asset search/filtering, relationship graph, claim detail, and JSON/HTML report download.
- Deterministic demo fixture and evaluation script with precision/recall/F1, evidence validity rate, and normalization duplicate counts.

The implementation uses FastAPI and SQLite by default so it runs on a new machine without a database service. The database layer is isolated and can be replaced with PostgreSQL for deployment; Docker Compose packages the default local app.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env  # optional; export values in your shell or use a dotenv runner
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Click **Load demo** to create/open the fixed Acme Robotics fixture. The fixture is synthetic and must not be described as an external scan or real AI result.

Without a browser:

```bash
python scripts/load_demo.py
python scripts/evaluate.py
```

Docker:

```bash
docker compose up --build
```

## AI configuration

The default `AI_PROVIDER=rules-demo` needs no key. To run a real model, set:

```bash
export AI_PROVIDER=openai-compatible
export AI_BASE_URL=https://your-provider.example/v1
export AI_API_KEY=redacted
export AI_MODEL=your-model-name
```

The provider must return a JSON object matching the schema in `app/schemas.py`. The adapter sends a catalog of existing source and asset IDs. It never accepts a model-invented URL, source, or confidence as verified fact; unsupported IDs or quotes remain review items. Run `python scripts/evaluate.py` again and compare with a fresh `rules-demo` run for a same-fixture comparison.

## Tests and evaluation

```bash
pytest
python scripts/evaluate.py
```

The fixture ground truth expects `app.acme.example`, `status.acme.example`, and the normalized Fleet Console endpoint. Relationship truth expects a `Fleet Console - PRODUCT_USES_WEBSITE - app.acme.example` claim. The script reports precision, recall, F1, evidence validity rate, and URL duplicates before/after normalization. If a real AI provider is not configured, the AI comparison is explicitly reported as not run.

## API overview

- `POST /api/projects`, `GET /api/projects`, `GET /api/projects/{id}`
- `POST /api/projects/{id}/collect`
- `POST /api/demo/load`
- `GET /api/projects/{id}/assets?q=&asset_type=&status=&source=`
- `GET /api/projects/{id}/relationships`, `/graph`, `/claims/{relationship_id}`
- `GET /api/projects/{id}/report.json`, `/report.html`

## Data and safety boundaries

Passive mode fetches only the official website and performs DNS lookups. It does not port scan or brute force. Authorized mode is opt-in and only crawls HTTP(S) pages on the supplied allowlist with configurable page/depth/delay limits. Redirect targets are revalidated. External links are recorded as candidates but are not treated as owned assets unless the allowlist and source-backed relationship justify that status. Shared IPs, named partners, and model suggestions alone never prove ownership.

## Architecture

`app/collectors` contains collectors and scoped HTTP utilities; `app/normalize.py` and `app/scope.py` contain canonicalization and authorization rules; `app/ai` contains adapters and evidence validation; `app/pipeline.py` runs isolated collectors and logs failures; `app/report.py` exports reports; `app/static` is the lightweight browser UI. `IMPLEMENTATION_PLAN.md` records the implementation plan completed for this repository.

# last-dance
