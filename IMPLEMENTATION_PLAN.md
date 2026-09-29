# Implementation plan

1. Build a FastAPI service with a SQLite default database, explicit project scope, collection runs, normalized assets, entities, sources, evidence, relationships, and collector logs.
2. Add passive and authorized collectors with host allowlist checks, bounded crawling, URL/parameter normalization, DNS lookup, and per-collector error isolation.
3. Add a rules-based demo AI adapter plus an OpenAI-compatible adapter. Validate model output against schemas and require source-backed evidence before accepting a relationship.
4. Add a browser UI served by FastAPI for project creation, demo loading, collection, asset/relationship views, evidence details, graph rendering, and JSON/HTML reports.
5. Add deterministic demo data, meaningful tests, an evaluation script with labeled ground truth, Docker/local setup, and documentation.

The default demo is offline and deterministic. Network collection is bounded and opt-in; the authorized collector never follows a redirect to a host outside the project allowlist.
