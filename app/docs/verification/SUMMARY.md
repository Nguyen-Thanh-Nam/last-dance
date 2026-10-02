# Kết quả kiểm tra cuối — 02/10/2026

Code MVP đã được tách vào `app/BE/app` và `app/FE`. Bảng đối chiếu yêu cầu, thay đổi và phần chưa đạt nằm trong [PLAN_AUDIT.md](../PLAN_AUDIT.md) và mục 15 của [plan.md](../../../plan.md).

Sau khi bổ sung Google Dork, đã chạy 103 test, 63 curl checks cho API, 18 curl requests cho setup thành công trên fixture server, 55 curl checks cho FE/CORS/schema, kiểm tra logic Dork trên FE và build Docker BE. Không gọi Google CSE API thật; xem [GOOGLE_DORK.md](GOOGLE_DORK.md) để biết yêu cầu quyền API và fallback. Chi tiết luồng setup tại [DOMAIN_SETUP.md](DOMAIN_SETUP.md); giao diện và phần chưa kiểm tra trực quan tại [FIGMA.md](FIGMA.md). Lượt trước sửa giao diện có 71 curl checks trên Windows/Docker. Chi tiết cấu trúc tại [STRUCTURE.md](STRUCTURE.md).

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Unit/integration/regression | 103 passed, 1 deprecation warning của Starlette/httpx | [pytest.txt](pytest.txt), [JUnit](pytest.xml) |
| Curl API bản setup một domain, DB tạm | 63 kiểm tra đạt; bao phủ 24 method-route API | [curl-results.json](curl-results.json), [curl.txt](curl.txt) |
| Curl setup thành công, fixture server | 18 kiểm tra đạt; tự tạo/thu thập/Google Dork fallback/social/AI fixture/báo cáo, reuse và input lỗi | [domain-setup-curl.json](domain-setup-curl.json), [domain-setup-curl.txt](domain-setup-curl.txt) |
| Curl FE/CORS/schema bản setup một domain | 55 kiểm tra đạt, toàn bộ assets khớp file trên đĩa; không thay đổi project | [figma-frontend-curl.json](figma-frontend-curl.json), [figma-frontend-curl.txt](figma-frontend-curl.txt) |
| Docker FE BankDash | Build image frontend thành công | [figma-docker-build.txt](figma-docker-build.txt) |
| Docker BE setup một domain | Build thành công; 63 curl checks đạt, bao phủ 24 API; DB tmpfs, non-root, read-only, cap-drop và no-new-privileges | [domain-docker-build.txt](domain-docker-build.txt), [domain-docker-api.json](domain-docker-api.json), [domain-docker-api.txt](domain-docker-api.txt) |
| Docker Linux trước sửa giao diện | Build thành công; healthy; user `app`; read-only root; runtime tmpfs; capabilities dropped; no-new-privileges | [docker-build.txt](docker-build.txt) |
| Curl trên Docker trước sửa giao diện, DB tạm | 71 kiểm tra đạt; bao phủ 23 method-route API | [docker-curl-results.json](docker-curl-results.json), [docker-curl.txt](docker-curl.txt) |
| JavaScript | `node --check FE/app.js` đạt | Chạy lại sau sửa cuối |
| Dependency/config/diff | `pip check`, `docker compose config --quiet`, `git diff --check` đạt | Không có lỗi dependency/config/whitespace |
| Logic FE, Node DOM stub | Cards/charts, search, claims/sources, setup một domain, auto polling, reload resume, lỗi inline và API/report port đạt | [frontend-logic.txt](frontend-logic.txt); không kiểm tra layout |
| Giao diện trình duyệt | Bản BankDash vẫn bị chặn bởi saved Browser permission; chưa nghiệm thu desktop/mobile | [FIGMA.md](FIGMA.md), [UI.md](UI.md); ảnh cũ thuộc giao diện trước |
| Evaluation B0 | Fixture tổng hợp: assets 3/3, entities 2/2, relationships 5/5; Precision/Recall/F1 đều 1.0 | [evaluation.json](evaluation.json) |
| Evaluation B1 / nguồn thật | Chưa chạy model thật hoặc corpus tổ chức thật | Không có key/corpus/nhãn độc lập cho thực nghiệm |

Curl dùng `curl.exe` thật, kiểm tra phản hồi thành công và lỗi 400/404/409/422, tác vụ nền, cách ly project, review, evidence, observations, report và chặn private target. Bản setup một domain có tổng 135 request assertions từ ba runner (63 API + 17 setup + 55 FE/CORS/schema). Runner API không đếm polling bổ sung; runner setup ghi cả request polling đã thực hiện. Số 71 của lượt trước gồm 61 kiểm tra BE và 10 kiểm tra FE/CORS/phân tách server. Runner API đối chiếu OpenAPI để xác nhận không bỏ sót API đã khai báo, dùng DB/server tạm và dừng sau kiểm tra. Runner FE không tạo/xóa project; chỉ thêm POST setup input sai để xác nhận server thật đã nạp route mới.

DNS/CT/RDAP/TLS và AI được kiểm thử bằng fixture/mock. Các kết quả này xác nhận hành vi phần mềm trong tình huống đã kiểm tra; không chứng minh mọi dịch vụ Internet thật đang khả dụng hoặc độ chính xác nghiên cứu trên tổ chức thật. Fixture và ground truth được duy trì cùng code, chưa phải dữ liệu held-out hay gán nhãn độc lập. Vì vậy chưa tuyên bố đạt mục tiêu Precision 90% của đồ án.

Để nghiệm thu nghiên cứu vẫn cần lab/phạm vi được phép, hai hồ sơ tổ chức thật, corpus snapshot, hai người gán nhãn độc lập, so sánh B0/B1 cùng dữ liệu, đo chi phí/độ ổn định/thời gian duyệt và báo cáo/slide thực nghiệm. Backlog tùy chọn như PostgreSQL, React/Cytoscape, Subfinder, PDF, semantic search và diff được giữ rõ là chưa triển khai.

Sau khi gom toàn bộ dự án vào `app/`, chạy các lệnh kiểm tra từ thư mục này; `plan.md` là file duy nhất còn nằm ngoài (ngoài metadata Git ẩn). Venv activation và editable install đã được cập nhật theo vị trí mới.
