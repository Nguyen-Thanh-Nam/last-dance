# Surface Map AI

Evidence-backed external attack surface discovery for an organization. The project is an offline-first MVP for a graduation project: it collects public technical and non-technical signals, normalizes them, links them only when a source-backed claim exists, and produces a browsable report.

## What is included

- Project scope with organization, aliases, brands, official website, root domain, allowlist, known social URLs, authorized assets, `passive` and `authorized` modes, notes, run status, and collector logs.
- Independent passive website, DNS, Certificate Transparency, RDAP (IP/registrar/ASN/hosting enrichment when the public endpoint responds), Social OSINT, and authorized HTTP/crawl collectors. Authorized requests are bounded by page/depth/delay settings, check every host against the allowlist, block private/loopback hosts, and validate redirects before following them.
- Normalized `Domain`/`Host`, `Website`, `Endpoint`, `Parameter`, and DNS/IP assets, plus `Organization`, `Brand`, `Product`, `Project`, `SocialAccount`, and `SocialPost` entities.
- Sources retain URL/name, collection time, title, raw content, and metadata. Relationships retain predicate, status (`confirmed`, `related`, `needs_review`), confidence, rationale, and an evidence quote.
- `rules-demo` AI adapter is deterministic and clearly labeled. `openai-compatible` can call a configurable `/chat/completions` provider. Model output is schema-validated; source IDs and quotes are checked against collected content, and unsupported claims become `needs_review`.
- Browser UI for project creation, demo loading, collection, asset/social search views, relationship graph, claim detail, confirm/reject review actions, and JSON/HTML report download.
- Deterministic demo fixture and labeled ground truth with precision/recall/F1, confidence/evidence traceability, collector duration, and normalization duplicate counts.

The implementation uses FastAPI and SQLite by default so it runs on a new machine without a database service. The database layer is isolated and can be replaced with PostgreSQL for deployment; Docker Compose packages the default local app.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env  # optional; export values in your shell or use a dotenv runner
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Click **Load demo** to create/open the fixed Acme Robotics fixture. The fixture is synthetic and must not be described as an external scan or real AI result. The project page has **Run collection** and **Full collection**; full mode enables every collector allowed by the project mode and still enforces the same allowlist. **Delete project** removes only the selected project and its related evidence/runs.

Without a browser:

```bash
python scripts/load_demo.py
python scripts/evaluate.py
```

To run selected collectors for a project, for example:

```bash
curl -X POST http://127.0.0.1:8000/api/projects/PROJECT_ID/collect \
  -H 'Content-Type: application/json' \
  -d '{"collectors":["passive_web","dns","certificate_transparency","social_osint","ai"]}'
```

Known social records are supplied when creating a project. Facebook/LinkedIn records normally use manual public evidence; YouTube/GitHub URLs may be fetched publicly:

```json
{"platform":"facebook","url":"https://facebook.com/example","handle":"example","verification_evidence":"The official website example.org links to this page.","posts":[{"permalink":"https://facebook.com/example/posts/1","published_at":"2025-01-01T00:00:00Z","content":"Product: Example App is available at https://app.example.org/"}]}
```

Docker:

```bash
docker compose up --build
```

Compose reads the root `.env` automatically for `AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL`; the database is always stored in the named container volume at `/app/runtime`. To avoid using host port 8000, set `SURFACE_MAP_PORT=8010` in `.env` or run `SURFACE_MAP_PORT=8010 docker compose up --build`. The image runs as a non-root user, drops Linux capabilities, uses a read-only filesystem except for the database volume, and exposes a healthcheck at `/api/health`. Before starting anything, validate the generated configuration with `docker compose config`.

RDAP enrichment is opt-in because it makes public network requests. Set `ENABLE_RDAP=true` when you want IP/domain RDAP, ASN, registrar, and hosting enrichment; the collector records failures and never treats the result as ownership proof.

## AI configuration

The default `AI_PROVIDER=rules-demo` needs no key. To run a real model, set:

```bash
export AI_PROVIDER=openai-compatible
export AI_BASE_URL=https://your-provider.example/v1
export AI_API_KEY=redacted
export AI_MODEL=your-model-name
```

The provider must return a JSON object matching the schema in `app/schemas.py`. The adapter sends a catalog of existing source and asset IDs. It never accepts a model-invented URL, source, or confidence as verified fact; unsupported IDs or quotes remain review items. The final confidence combines source type, quote directness, and the model suggestion after validation. Run `python scripts/evaluate.py` again and compare with a fresh `rules-demo` run for a same-fixture comparison. The script explicitly reports `not_run` when no real model is configured.

## Tests and evaluation

```bash
pytest
python scripts/evaluate.py
```

The fixture ground truth is in `data/evaluation_ground_truth.json`. It expects `app.acme.example`, `status.acme.example`, the normalized Fleet Console endpoint, an official Facebook account, and a product-to-app relation. The script reports precision, recall, F1, evidence traceability, confidence buckets, collector time, and URL duplicates before/after normalization. If a real AI provider is not configured, the AI comparison is explicitly reported as not run.

## API overview

- `POST /api/projects`, `GET /api/projects`, `GET /api/projects/{id}`
- `POST /api/projects/{id}/collect` with `{"profile":"standard"}` or `{"profile":"full"}`. Full adds authorized HTTP only when the project is `authorized`.
- `DELETE /api/projects/{id}`
- `POST /api/demo/load`
- `GET /api/projects/{id}/social`
- `GET /api/projects/{id}/assets?q=&asset_type=&status=&source=`
- `GET /api/projects/{id}/relationships`, `/graph`, `/claims/{relationship_id}`
- `PATCH /api/projects/{id}/claims/{relationship_id}` with `confirmed`, `related`, `needs_review`, or `rejected`
- `GET /api/projects/{id}/report.json`, `/report.html`

## Data and safety boundaries

Passive mode reads the official website, DNS, Certificate Transparency, RDAP when enabled by the collector list, and configured public social records. It does not port scan or brute force. Authorized mode is opt-in and only crawls HTTP(S) pages on the supplied allowlist with configurable page/depth/delay limits. Redirect targets are revalidated. External links are recorded as candidates but are not treated as owned assets unless the allowlist and source-backed relationship justify that status. Shared IPs, named partners, and model suggestions alone never prove ownership.

Social support is deliberately explicit. Facebook and LinkedIn use URL/manual JSON import because automated collection is commonly restricted; YouTube and GitHub public pages can be fetched when a URL is supplied. Instagram, TikTok, X, Threads, Reddit, Telegram, Discord, Zalo, and Medium are supported as URL/manual records with reviewer verification. The system never enters private groups, bypasses login, or profiles private individuals. See `docs/SOCIAL_OSINT.md` for the exact input and status model.

## Architecture

`app/collectors` contains collectors and scoped HTTP utilities; `app/normalize.py` and `app/scope.py` contain canonicalization and authorization rules; `app/ai` contains adapters and evidence validation; `app/pipeline.py` runs isolated collectors and logs failures; `app/report.py` exports reports; `app/static` is the lightweight browser UI. Methodology, data model, experiments, and social-source limitations are documented in `docs/RESEARCH.md`, `docs/DATA_MODEL.md`, `docs/EXPERIMENTS.md`, and `docs/SOCIAL_OSINT.md`. `IMPLEMENTATION_PLAN.md` records the implementation plan completed for this repository.

# last-dance
