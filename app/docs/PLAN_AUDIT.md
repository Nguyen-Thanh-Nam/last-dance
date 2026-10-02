# Đối chiếu plan.md với triển khai

Ngày kiểm tra: 02/10/2026 (Asia/Saigon).

Kết luận: phần mềm đã có luồng MVP chạy được và kiểm thử tái hiện. Chưa đủ tiêu chuẩn nghiệm thu nghiên cứu theo mục 9 và 13 vì chưa có bộ nhãn độc lập, hồ sơ tổ chức thật, kết quả model thật B0/B1 và báo cáo/slide thực nghiệm. Fixture Acme dùng cho kiểm thử chức năng; không thay thế những đầu ra này.

## Đối chiếu chức năng

| Yêu cầu | Trước kiểm tra | Hiện tại / chứng cứ | Giới hạn còn lại |
|---|---|---|---|
| Tách backend/frontend | FE nằm trong app/static | app/BE/app và app/FE, Docker/import/script cập nhật | FE JavaScript/SVG; chưa dùng React |
| Tác vụ nền, tiến độ, log | Collect chạy trong request, demo flag không được sử dụng | SQLite queued jobs, worker, 202/run polling, collector savepoint, log; offline mode chặn network | Một process; interrupted cần người dùng tạo run mới |
| Organization/aliases/seeds/scope | Có input nhưng kiểm tra chưa chặt | Pydantic input, HTTP(S), IDNA, public suffix, nested social schema | PUT/UI edit tổ chức-scope; audit previous/updated config |
| Scope độc lập | Empty authorized_assets cho kiểm tra mọi host allowlist; redirect không xét exact asset | Hostname/domain/IP/CIDR, test HTTP/TLS, expiry; kiểm tra mỗi redirect; global + per-scope opt-in lab | Các quyền lab/real organization phải do nhóm cung cấp |
| DNS và chuẩn hóa | Xóa www, làm hỏng IPv6, AAAA bị khóa như A | Giữ www/wildcard, IDNA, IPv6, URL path/query; A/AAAA/CNAME/MX/NS, wildcard marker, quan hệ kỹ thuật | HTTP DNS resolution phụ thuộc OS timeout |
| CT/RDAP | CT bỏ wildcard; RDAP name bị gán nhầm registrar | Giữ chứng chỉ lịch sử/SAN, wildcard và certificate_contains; RDAP role registrar chính xác hơn | Nguồn thật phụ thuộc availability; RDAP redirect ngoài trust list bị chặn |
| HTTP/HTTPS/TLS | Crawl nuốt lỗi và không có TLS collector riêng | IP pinned + Host/SNI, TLS verify, status/header/redirect, TLS SAN; probe_error giữ chặn/lỗi | Kiểm tra service 403 không suy ra ownership; không scan ports |
| Snapshot/provenance | Raw và source đơn; upsert thay source mất liên kết lịch sử | SHA-256, run ID, chunks/offsets, observations, claim_evidence supports/refutes, source API | Không tự chứng minh tính đúng ngữ nghĩa của chứng cứ |
| Review và classification | Chỉ trạng thái cuối; AI có thể ghi đè quyết định duyệt | Review append-only, giữ human review, classification riêng, counter-evidence chuyển needs_review | Cần người có chuyên môn xử lý mâu thuẫn và sở hữu |
| AI | Reference entity giả có thể tạo cạnh treo; prompt/schema quá lỏng | ID đúng project, schema type/predicate, quote check, bounded source/asset catalog, untrusted-source prompt, model_runs/usage | Model thật chưa được kiểm chứng bằng dữ liệu nghiên cứu; heuristic chưa hiệu chỉnh |
| Luật liên kết sản phẩm | Gán mọi host cùng trang cho sản phẩm | Yêu cầu link có ngữ cảnh sản phẩm; negative regression cho root/status | Baseline vẫn là bộ luật giới hạn, cần phân tích lỗi trên corpus thật |
| Social official channel | Manual text có chữ official tự confirmed | Cần backlink trong official snapshot; manual assertion needs_review | Không crawling private/profile cá nhân; giới hạn platform ghi riêng |
| Giao diện | Graph bị cắt node và không mở evidence; cancel có thể tạo project | Lọc depth/status, cạnh mở claim; source filter/asset observations, review/history/classification; sửa cancel và stale click handlers | Chưa có Cytoscape layout nâng cao và tài khoản nhiều người dùng |
| Báo cáo | JSON/HTML | JSON gồm provenance/review/model data, HTML escape và tên thực thể, CSV chống formula injection | Chưa có PDF; report nghiên cứu cuối kỳ phải dùng dữ liệu thực |
| Đánh giá | Asset Precision lọc trước bằng truth; B0/B1 bị lẫn provider | DB tạm, không lọc bỏ FP; typed assets, entity/relationship metrics, buckets, coverage, traceability; B0 độc lập; B1 opt-in; so sánh hash snapshot | Bộ chuẩn fixture nhỏ; chưa có held-out set và 2 reviewer độc lập |
| Đóng gói và API | Cấu trúc cũ và dependency khoảng phiên bản | requirements-lock, Docker/Compose, OpenAPI/Swagger/API.md và curl smoke runner | SQLite/JS là lựa chọn MVP; PostgreSQL/React chưa triển khai |

## Kết quả xác minh

Lượt cuối sau khi bổ sung setup một domain: **101 test tự động đạt; 63 curl checks API, 17 curl checks setup và 55 curl checks FE/CORS/schema đạt, bao phủ 24 API**. Lượt trước có 71 curl checks trên Windows/Docker. Xem [tổng hợp bằng chứng](verification/SUMMARY.md) và [luồng setup một domain](verification/DOMAIN_SETUP.md).

Số lượng và trạng thái chạy cuối cùng nằm trong `docs/verification/pytest.txt`, `pytest.xml`, `curl-results.json` và `evaluation.json`. Curl runner đối chiếu danh sách route OpenAPI để tránh bỏ sót endpoint. Có kiểm tra 200/202/400/404/409/422, project isolation, queue, export, review, source/observation hashes và chặn private target. Unit/integration tests dùng fixture cho DNS/CT/RDAP/TLS/AI; chưa gọi mọi nguồn OSINT ngoài Internet hoặc trả phí cho model thật.

Giao diện trước khi tách cổng được kiểm tra trong trình duyệt: Load demo, search/type filter, mở observation sau lọc, mở claim từ graph, review/history, form cancel và edit project/scope. Bản BankDash/setup một domain mới chỉ có Node syntax/DOM stub và curl, chưa kiểm tra browser vì quyền đã lưu chặn localhost:2222. Docker được build/run bằng user non-root với DB tạm ở lượt trước; bằng chứng trong thư mục verification. Các test dùng DB tạm, không xóa project người dùng.

Fixture nhãn v2 bổ sung quan hệ product -> endpoint mà snapshot thật sự có liên kết, thêm negative labels cho root/status và loại entity product/project. Nhãn được duy trì cùng code; thay đổi này không phải gán nhãn độc lập. Kết quả tốt trên fixture sau chỉnh luật không được báo cáo như kết quả held-out hoặc chứng minh mục tiêu Precision 90%.

## Công việc nghiên cứu cần dữ liệu/phân công thực tế

1. Xác nhận một lab và hai hồ sơ tổ chức, nguồn công khai/điều kiện sử dụng, scope HTTP/TLS và thời hạn. Có thể bật lab private bằng cấu hình riêng; hiện không tự bật.
2. Thu thập corpus thật, giữ snapshot/hash và missing-data log; chia development/evaluation theo tổ chức và nguồn trùng. Theo docs/LABELING_GUIDE.md.
3. Hai người gán nhãn độc lập, lưu bất đồng/adjudication, khóa ground truth và cấu hình trước khi đo.
4. Cấu hình provider/model/key và chạy B0/B1 trên cùng snapshot, kể cả khi AI không cải thiện; đo chất lượng evidence bằng người, coverage, độ mới, ổn định, chi phí và thời gian duyệt. Dữ liệu JSON/API key không được ghi vào Git.
5. Viết phân tích lỗi, báo cáo cuối kỳ, slide và kịch bản demo bằng kết quả thực. Chưa tuyên bố hoàn thành các mục này.

Các tính năng tùy chọn (diff hai lần thu thập, semantic search, PDF, thêm Subfinder, PostgreSQL, React) nằm ở backlog riêng. Không thay thế các yêu cầu đánh giá nghiên cứu bằng việc thêm tính năng giao diện.
