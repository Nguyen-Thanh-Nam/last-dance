# Hợp đồng API (v0.2.0)

BE: http://127.0.0.1:3333. FE: http://127.0.0.1:2222. Chạy Swagger tại `http://127.0.0.1:3333/docs`, ReDoc tại `/redoc`; schema tĩnh: `docs/openapi.json`. API dùng JSON, ngoại trừ HTML/CSV exports.

| Method | Route | Chức năng |
|---|---|---|
| GET | `/api/health` | Health |
| GET | `/api/projects` | Projects |
| POST | `/api/projects` | Create Project |
| POST | `/api/projects/setup` | Nhập domain, tự tạo project và khởi chạy collection |
| PUT | `/api/projects/{project_id}` | Update Project |
| GET | `/api/projects/{project_id}` | Project Detail |
| DELETE | `/api/projects/{project_id}` | Delete Project |
| POST | `/api/projects/{project_id}/collect` | Collect |
| POST | `/api/demo/load` | Demo Load |
| GET | `/api/projects/{project_id}/social` | Social |
| GET | `/api/projects/{project_id}/assets` | Assets |
| GET | `/api/projects/{project_id}/relationships` | Relationships |
| GET | `/api/projects/{project_id}/graph` | Graph |
| GET | `/api/projects/{project_id}/claims/{relationship_id}` | Claim |
| PATCH | `/api/projects/{project_id}/claims/{relationship_id}` | Review Claim |
| GET | `/api/projects/{project_id}/report.json` | Json Report |
| POST | `/api/projects/{project_id}/claims/{relationship_id}/evidence` | Attach Evidence |
| GET | `/api/projects/{project_id}/report.html` | Html Report |
| GET | `/api/projects/{project_id}/report.csv` | Csv Report |
| GET | `/api/projects/{project_id}/runs` | Runs |
| GET | `/api/projects/{project_id}/runs/{run_id}` | Run Detail |
| GET | `/api/projects/{project_id}/sources/{source_id}` | Source Detail |
| GET | `/api/projects/{project_id}/assets/{asset_id}` | Asset Detail |
| PATCH | `/api/projects/{project_id}/assets/{asset_id}` | Review Asset |

## Trạng thái và lỗi

- Setup: `POST /api/projects/setup` chỉ cần `{"domain":"example.org"}`; trả 202 với `project`, `collection` (run_id/status) và `created`. Tự tạo website HTTPS, tên project theo domain, root domain và allowlist; mode passive. Tạo project và queue cùng transaction. Gửi lại cùng domain dùng lại project tự tạo và job đang chạy; sau khi job kết thúc thì tạo lần thu thập mới. Không tự ghi đè project cấu hình thủ công.

- Collect: mặc định `202 {run_id,status:queued}`; GET run để theo dõi queued/running/completed/completed_with_errors/failed/interrupted. `background=false` trả 200 sau khi xong.
- Job trùng hoặc xóa project có job đang hoạt động: 409. Project/claim/asset/source/run không tồn tại hoặc ID thuộc project khác: 404. Input/schema sai: 422. Website ngoài allowlist hoặc evidence quote không có trong snapshot: 400.
- Claim review: confirmed/related/needs_review/rejected, reviewer và rationale. Review history giữ trạng thái trước/sau; thu thập tiếp giữ quyết định human_review.
- Asset classification: controlled/third_party/candidate/insufficient_evidence/rejected; rationale bắt buộc. Thay classification không thay scope hoặc claim status.
- Evidence attachment: source_id, quote, role=supports/refutes, reviewer. Chỉ dùng source cùng project; chấp nhận khác biệt khoảng trắng nhưng lưu lại đoạn trích đúng từ snapshot. Refutes chuyển claim về needs_review và ghi review audit.
- Asset filters: q, asset_type, status, source (mọi observation), classification, min_confidence (0..1), observed_after (ISO timestamp có timezone).
- Source detail trả raw_content, SHA-256, collection/run metadata và chunks (ID, offsets, text).
- JSON report chứa snapshot, observations, reviews, sources, model_runs và limitations. CSV có BOM UTF-8, classification, nguồn, first/last seen và tránh formula injection. HTML escape dữ liệu nguồn.

## Ví dụ collect

```json
{"collectors":["passive_web","dns","certificate_transparency","social_osint","ai"],"profile":"standard","background":true,"demo":false}
```

Profile full thêm authorized_http và tls chỉ khi mode=authorized. Mỗi kiểm tra chủ động vẫn cần scope riêng. `demo=true` trong collect bỏ qua collector mạng; `/api/demo/load` nạp fixture đầy đủ offline, luôn dùng rules-demo.

Social collector tự phát hiện tối đa 20 profile URL từ website snapshot trong scope và kết hợp với các record đã khai báo. Bỏ qua link chia sẻ, đăng nhập và các đường dẫn bài viết phổ biến. Các nền tảng manual-only giữ chứng cứ backlink; không tự vượt đăng nhập hoặc lấy bài viết cần export thủ công.

PUT project dùng schema đầy đủ như create; chặn thay scope khi có active run và lưu previous/updated project trong project_history. Lab private cần global ALLOW_PRIVATE_LAB cùng scope allow_private=true; default false.
