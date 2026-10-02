# Implementation plan

1. Build a FastAPI service with a SQLite default database, explicit project scope, collection runs, normalized assets, entities, sources, evidence, relationships, and collector logs.
2. Add passive and authorized collectors with host allowlist checks, bounded crawling, URL/parameter normalization, DNS lookup, Certificate Transparency lookup, public social URL/manual import, and per-collector error isolation.
3. Add a rules-based demo AI adapter plus an OpenAI-compatible adapter. Validate model output against schemas and require source-backed evidence before accepting a relationship.
4. Add explicit Brand, SocialAccount, SocialPost, relationship classes, confidence/traceability fields, and review actions for confirming or rejecting claims.
5. Add a browser UI served by FastAPI for project creation, demo loading, collection, asset/social views, evidence details, graph rendering, review actions, and JSON/HTML reports.
6. Add deterministic demo data, labeled ground truth, research and data-model documents, meaningful tests, an evaluation script, Docker/local setup, and documentation of exact platform support and limitations.

The default demo is offline and deterministic. Network collection is bounded and opt-in; the authorized collector never follows a redirect to a host outside the project allowlist.

## Audit v0.2 (02/10/2026)

Mã đã tách app/BE/app và app/FE. Đối chiếu chi tiết, kết quả pytest/curl/Docker và các yêu cầu nghiên cứu chưa hoàn thành nằm trong plan.md mục 15, docs/PLAN_AUDIT.md và docs/verification/. Đã thêm worker/queue, scope độc lập/expiry/lab opt-in, TLS, snapshot/hash/chunks/observations, review/classification/counter-evidence, project edit audit, CSV và sửa evaluation không bỏ false positives. Chưa tuyên bố model thật, corpus thật hoặc nhãn độc lập đã được kiểm chứng.
