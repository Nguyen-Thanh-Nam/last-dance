# Thiết lập bằng một domain — 02/10/2026

Người dùng chọn **Thêm domain**, nhập một domain và bấm **Bắt đầu**. Form mới có đúng một input, không yêu cầu tên tổ chức/website/allowlist/social JSON hoặc scope. Backend tạo project theo domain, dùng HTTPS và tự xếp hàng standard collection. FE theo dõi tiến độ và cập nhật danh mục/chứng cứ/báo cáo sau khi hoàn tất.

## Hành vi

- `POST /api/projects/setup` nhận `{"domain":"example.org"}`; trả HTTP 202 với project và collection run_id. Tên project ban đầu là domain; AI có thể phát hiện thêm thực thể từ nguồn, không tự xác nhận danh tính tổ chức.
- Chuẩn hóa chữ hoa, dấu chấm cuối và IDNA; có thể dán URL HTTP(S) gốc. Từ chối IP, wildcard, hostname thiếu dấu chấm, credentials, port, path/query và field ngoài schema.
- `www.example.org` cho thu thập website trong `example.org`; nhập `app.example.org` giữ allowlist ở nhánh đó. Mode passive; không tự mở scope kiểm tra HTTP/TLS chủ động.
- Tạo project và job trong cùng transaction. Retry cùng domain dùng lại project tự tạo và active run; sau khi job kết thúc thì tạo run mới, giữ dữ liệu/review cũ. Project cấu hình thủ công được giữ nguyên.
- Website → DNS → Certificate Transparency → RDAP nếu bật → Social → AI. Social tự tìm tối đa 20 profile URLs từ snapshot website trong scope, loại link chia sẻ/đăng nhập/post phổ biến và kết hợp record đã khai báo. Nền tảng manual-only giữ chứng cứ backlink; không tự có bài viết cần đăng nhập/export.
- Tiến độ tiếp tục sau reload; FE nhớ project đã chọn. Mỗi run chỉ có một vòng polling trong trang, không enqueue lại khi reload. Lỗi schema nằm ngay trong form; lỗi collector/provider hiện trong trạng thái run và Collection logs.
- Tính năng sửa project/scope và Load demo cũ vẫn có. API AI dùng cấu hình BE hiện tại; key không đưa xuống FE. Không thay đổi `.env` hoặc database người dùng để kiểm thử.

## Kiểm tra bản này

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Pytest toàn bộ | 101 passed, một warning dependency hiện có | `pytest.txt`, `pytest.xml` |
| Curl API, DB tạm | 63 assertions, bao phủ đủ 24 API method-route | `curl-results.json`, `curl.txt` |
| Curl setup thành công, fixture server | 17 assertions: domain → automatic job → assets/social/AI fixture → reports; reuse và input lỗi | `domain-setup-curl.json`, `domain-setup-curl.txt` |
| Curl FE và BE đang chạy | 55 kiểm tra assets/schema/CORS và input setup bị từ chối, không tạo project | `figma-frontend-curl.json`, `figma-frontend-curl.txt` |
| Logic FE trong Node DOM stub | Đúng một input; submit chỉ domain; tự polling; reload tiếp tục run; không enqueue hai lần; lỗi inline; các chức năng cũ đạt | `frontend-logic.txt` |
| Docker BE bản mới | Build thành công; 63 curl checks đạt, bao phủ đủ 24 API; DB tmpfs, non-root, read-only, cap-drop và no-new-privileges | `domain-docker-build.txt`, `domain-docker-api.json`, `domain-docker-api.txt` |
| Docker FE bản mới | Build thành công | `figma-docker-build.txt` |

Test backend mới kiểm tra normalization, default scope, transaction rollback khi queue lỗi, reuse project/job và chạy pipeline thực qua worker với fixture nguồn. Test social xác nhận backlink và bỏ qua snapshot ngoài scope. Curl thành công dùng rules-demo và bộ thu thập fixture, không gọi Internet hoặc API AI trả phí. Không dùng kết quả này để tuyên bố model/provider thực đã gọi thành công.

BE :3333 và FE :2222 đã được khởi động lại với code mới. Kiểm tra lại bằng curl xác nhận schema có `/api/projects/setup` và FE phục vụ form một domain. Kiểm tra trực quan trong trình duyệt vẫn chưa thực hiện do saved Browser permission block từ lượt trước; DOM stub không thay thế browser E2E.

## Chạy lại

Từ `app/`:

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py
.\.venv\Scripts\python.exe scripts/smoke_api.py
.\.venv\Scripts\python.exe scripts/smoke_setup.py
.\.venv\Scripts\python.exe scripts/check_frontend.py
```

Khi hai server thật đang chạy, dùng `scripts/smoke_frontend.py` bằng cùng Python để kiểm tra tài nguyên/schema/CORS và input lỗi, không thay đổi project. Không chạy `smoke_split_ports.py --external` vào database người dùng.
