# Mô hình dữ liệu và luồng xử lý

## Thực thể chính

- `Organization`: entity type `organization`, tên tổ chức và aliases trong project.
- `Brand`: bảng brands, tên thương hiệu và nguồn.
- `Product`, `Project`, `Website`: entity types trong bảng entities.
- `Domain`, `Host`, `IP`, `Service`, `Endpoint`: asset types trong bảng assets; DNS record giữ IP và domain trong attributes.
- `SocialAccount`: platform, profile URL, verification status/reason và source.
- `SocialPost`: permalink, published_at, content, source.
- `Source`: URL hoặc tên nguồn, raw content, metadata và collected_at.
- `Evidence`: quote, locator, validity, confidence và source.
- `Relationship`: subject/object refs, predicate, relation_class, status, confidence, rationale, evidence và review metadata.
- `CollectionRun`: giới hạn chạy, trạng thái và collector logs.

## Quan hệ cốt lõi

```text
Organization -[OFFICIAL_SOCIAL_ACCOUNT / owned]-> SocialAccount
SocialPost  -[POST_MENTIONS_PRODUCT / mentioned]-> Product or Host
Product     -[PRODUCT_USES_WEBSITE / used]-> Website, Host or Endpoint
Organization-[OWNS_DOMAIN / owned]-> Domain
```

Không gắn một IP dùng chung vào Organization nếu không có chứng cứ khác. Mỗi cạnh của đồ thị phải truy ngược tới `Evidence -> Source`; cạnh không resolve hoặc không có quote không được đánh dấu confirmed.

## Luồng xử lý

```text
Project + allowlist
  -> CollectionRun
  -> independent collectors (passive/DNS/CT/social/authorized HTTP)
  -> normalize + upsert + source/evidence
  -> rules-demo or OpenAI-compatible extraction
  -> schema/evidence validation
  -> relationship review and graph
  -> JSON/HTML report + evaluation metrics
```

SQLite là mặc định để demo tái lập trên máy mới; các bảng và khóa đã tách khỏi collector để có thể thay bằng PostgreSQL. Migration tự thêm các cột mở rộng cho database MVP cũ.
