# Tách FE/BE — 02/10/2026

- FE: http://127.0.0.1:2222, server Python riêng trong `FE/serve.py`.
- BE: http://127.0.0.1:3333; Swagger http://127.0.0.1:3333/docs.
- Backend không phục vụ frontend hoặc `/static`; `/` trả thông tin API.
- FE/config.js lấy cùng hostname và port 3333. Fetch và các link CSV/JSON/HTML report đều trỏ BE.
- CORS mặc định chỉ cho `http://127.0.0.1:2222` và `http://localhost:2222`; origin khác bị từ chối preflight.
- Native: chạy `.\.venv\Scripts\python.exe scripts/start_dev.py` từ `app/`, hoặc chạy hai terminal như README. Script đọc app/.env cho BE, kiểm tra hai port trước khởi động và dừng cả hai child server khi Ctrl+C.
- Docker Compose: hai target/service riêng, localhost mappings 2222/3333, non-root, read-only và healthcheck. BE giữ volume database.

Kết quả sau sửa: **80 test passed**; **71 curl checks passed** trên Windows và Docker. Trong đó 61 checks backend bao phủ 23 API, 10 checks bổ sung kiểm tra FE files, phân tách server và CORS. Xem [split-curl-results.json](split-curl-results.json), [split-curl.txt](split-curl.txt), [docker-curl-results.json](docker-curl-results.json), [pytest.txt](pytest.txt).

JavaScript syntax và Compose config đạt. Hai Docker test container healthy, user `app`, read-only; đã dừng sau kiểm tra. Database kiểm thử biệt lập, không dùng database dự án. Browser tool từ chối quyền mở FE port 2222; chưa kiểm tra lại luồng giao diện trong browser, không thử truy cập qua cách khác.
