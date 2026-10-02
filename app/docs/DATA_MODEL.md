# Bổ sung mô hình dữ liệu v0.2

app/BE/app/db.py có migration tương thích SQLite hiện có; không xóa database người dùng.

- projects: organization, aliases, brands, root-domain/website seeds, collection allowlist, legacy exact authorized_assets và authorized_scopes JSON (kind, value, tests, expiry, allow_private).
- collection_runs: queue/progress/status/config/error_count; một run queued/running mỗi project.
- sources: raw snapshot, URL/type/name/title, collected_at, SHA-256 và run_id. source_chunks giữ ID/offset/text có thể ghép lại raw snapshot.
- assets/entities: định danh chuẩn hóa và dữ liệu hiện tại. assets.classification độc lập với assets.status và claim review. Không xóa www hay lower-case URL path/query.
- observations: mỗi quan sát asset-source-run-time-attributes, để upsert không làm mất nguồn cũ.
- evidence: source ID, quote, locator/offset, validity và rank.
- relationships: bộ ba, predicate, class, confidence, rationale và current review; claim_evidence giữ nhiều evidence với roles supports/refutes.
- reviews: lịch sử quyết định claim, người/lý do/time và trạng thái trước/sau.
- asset_reviews: lịch sử classification; không đổi scope theo classification.
- model_runs: provider/model/prompt/schema, hash input, output, thời gian, usage/temperature metadata; chi phí tiền tệ chưa biết được lưu null.
- collector_logs: run/collector/status/message/count/duration.
- brands/social_accounts/social_posts: records công khai/manual; official backlink từ snapshot và manual assertion được phân biệt.

API chặn ID source/claim/asset/run thuộc project khác. Graph chỉ dùng ID entity/asset thực sự có trong project. Các FK cascade giúp xóa project cùng dữ liệu phụ thuộc khi project không có run đang chạy. Công cụ kiểm tra dùng DB tạm riêng.

Bảng claim_evidence giữ cả chứng cứ trái chiều; thêm refutes chuyển claim về needs_review và tạo audit. Chưa có bộ giải quyết mâu thuẫn tự động theo ngữ nghĩa/độ mới; human review cần quyết định. Snapshot hash không chứng minh nguồn nói đúng.

project_history lưu thời gian và previous/updated JSON khi PUT tổ chức/scope. Không được đổi scope trong lúc job queued/running.
