# Giao diện BankDash — 02/10/2026

Đã đọc thiết kế bằng Figma connector, gồm context và ảnh của desktop `78:351` (1440×1175) và mobile `169:3352` (375×1778) trong [file BankDash](https://www.figma.com/design/RwJ5LozBocVhfqsLTZIc8M/BankDash---Dashboard-UI-Kit---Admin-Template-Dashboard---Admin-Dashboard--Community-?node-id=78-351). Code được chuyển sang HTML/CSS/JavaScript đang dùng của Surface Map AI.

## Phần đã triển khai

- Header trắng, sidebar desktop, nền sáng, font Inter/Lato, màu xanh/tím/teal, thẻ bo góc và bố cục ba hàng theo BankDash. Mobile có menu thu gọn, thẻ cuộn ngang và nội dung một cột.
- Hai thẻ inventory, recent observations, discovery activity, asset statistics và observation history lấy dữ liệu project thật qua API. Biểu đồ dùng bảy ngày UTC; project rỗng hiển thị giá trị 0/trạng thái trống.
- Thay nội dung ngân hàng bằng assets, sources, relationships và collection của đồ án. Quick actions giữ Run collection/Full collection/Load demo; không triển khai chức năng giao dịch tài chính trong mẫu.
- Giữ tạo/sửa/xóa project, scope, lọc assets, graph, classification, review/evidence history, social, collection logs và JSON/CSV/HTML export. Bổ sung danh sách saved sources và mở snapshot/hash, tìm kiếm trên header, nút xem claims cần duyệt.
- 31 tài nguyên từ context Figma được lưu trong `FE/assets/`, gồm biến thể dấu thẻ desktop/mobile. SVG giữ nguyên root width/height/viewBox; icon ghép giữ offset theo lớp Figma. Font lưu cục bộ, kèm hai giấy phép OFL. FE không phụ thuộc URL tài nguyên Figma có hạn sử dụng.
- Manifest nguồn tại `docs/figma-assets-download.json` ghi file/node, tên file, SHA-256 và kích thước SVG. Cấu trúc vẫn chỉ có `app/` và `plan.md` ngoài cùng; FE :2222, BE :3333.

## Bằng chứng kiểm tra bản mới

Giao diện đã được bổ sung form setup một domain theo yêu cầu tiếp theo; chi tiết và bằng chứng tại [DOMAIN_SETUP.md](DOMAIN_SETUP.md).

| Kiểm tra | Kết quả | File |
|---|---|---|
| BE regression | 103 passed; một warning dependency hiện có | `pytest.txt`, `pytest.xml` |
| API bằng curl trên DB tạm | 63 request assertions đạt, bao phủ đủ 24 API method-route | `curl-results.json`, `curl.txt` |
| FE và CORS/schema bằng curl, hai server đang chạy | 55 kiểm tra không thay đổi project đạt; nội dung HTTP của CSS/JS/icon/font khớp file trên đĩa | `figma-frontend-curl.json`, `figma-frontend-curl.txt` |
| Logic FE trong Node với DOM stub và snapshot demo riêng | Khởi tạo, dữ liệu charts/cards, project rỗng, tìm kiếm, lọc claim, escape source, ID và assets đạt | `frontend-logic.txt` |
| JavaScript syntax | `node --check FE/app.js` và `FE/config.js` đạt | Lệnh chạy trực tiếp |
| Docker FE | Build image frontend thành công | `figma-docker-build.txt` |
| Dependency/config | `pip check`, `docker compose config --quiet` đạt | Lệnh chạy trực tiếp |

Curl FE kiểm tra tài nguyên/health/CORS/schema và gửi input setup sai bị từ chối; không thay đổi project. Curl API/setup và logic FE dùng database tạm; không sửa database của người dùng. Node DOM stub không xác nhận layout, font thực tế hay hành vi trình duyệt. Lệnh dọn cache Python/pytest sinh ra ở lượt trước bị kiểm duyệt tự động từ chối với lý do “blocked by policy”; cache được giữ trong `app/`.

## Phần chưa xác minh

Browser đã từ chối mở `http://127.0.0.1:2222` vì saved user permission setting, kể cả sau khi người dùng xác nhận đã bật quyền. Không dùng browser khác, CDP hay cách vòng để vượt chặn. Chưa có ảnh của giao diện BankDash chạy thực tế, chưa đo rendered geometry/overflow hoặc xác nhận thao tác desktop/mobile trong trình duyệt. Các ảnh `ui-desktop.png`/`ui-mobile.png` là giao diện cũ, không chứng minh bản BankDash. Vì vậy chưa tuyên bố giao diện giống Figma 100% hoặc đã nghiệm thu trực quan.

## Chạy lại

Từ `app/`, chạy `.\.venv\Scripts\python.exe scripts/run_tests.py`, `scripts/smoke_api.py` và `scripts/check_frontend.py` bằng cùng Python. Khi FE :2222 và BE :3333 đang chạy, gọi `.\.venv\Scripts\python.exe scripts/smoke_frontend.py`. `run_tests.py` dùng thư mục tạm mới vì thư mục pytest-of-NTN cũ trên Windows bị lỗi quyền truy cập; không đổi ACL hay xóa cache của phiên trước.
