# Cấu trúc và dọn thư mục — 02/10/2026

Theo yêu cầu, mã nguồn nằm trong `app/BE/` và `app/FE/`. Backend giữ Python package `app/BE/app/` để duy trì import `app.main`. Không còn BE/FE riêng ở thư mục gốc.

Yêu cầu tiếp theo đã được áp dụng: ngoài cùng chỉ có `app/` và `plan.md`, cùng thư mục Git ẩn `.git/`. Tất cả dữ liệu, tài liệu, script, bộ test, môi trường Python, `.env`, file cài đặt và Docker đều được chuyển nguyên trạng vào `app/`. Không xóa dữ liệu dự án. Chạy các lệnh từ `app/`; README, pyproject, scripts, Docker và venv activation/editable install đã cập nhật theo vị trí này. Python package và frontend vẫn nằm ở `app/BE/app/` và `app/FE/` xét từ thư mục ngoài cùng.

Đã cập nhật setuptools/pytest trong pyproject.toml, Docker COPY/PYTHONPATH, các script evaluate/load_demo/export_fixture/smoke_api và các hướng dẫn chạy. Đường dẫn frontend vẫn được backend tính từ vị trí package và trỏ đúng `app/FE/`.

Đã dọn khỏi dự án: `.pytest_cache`, các `__pycache__` trong backend/scripts/tests, metadata `surface_map_ai.egg-info` cũ và metadata mới sinh khi cập nhật editable install, `runtime/browser-check.db` và `runtime/served-app.js` do lượt kiểm thử trước tạo ra. Không xóa database `data/surface_map.db`, `.env`, `.venv`, code, bộ test, fixture hay tài liệu.

Công cụ thực thi chặn lệnh xóa trực tiếp, kể cả khi đã giới hạn từng file/thư mục. Các mục sinh tự động được chuyển ra bản sao dự phòng tại `C:\Users\NTN\AppData\Local\Temp\surface-map-cleanup-65691cbcc7e24b2fa39164934373f672`. Đây là chuyển khỏi dự án, chưa phải xóa vật lý. Không có mục không rõ nguồn gốc nào bị chuyển vào bản sao này.

Chạy lại pytest/curl/JavaScript và Docker sau khi chuyển code; bằng chứng cuối tại [SUMMARY.md](SUMMARY.md). Pytest dùng thư mục temp mới riêng vì thư mục `pytest-of-NTN` cũ bị Windows từ chối truy cập; không sửa quyền thư mục đó.
