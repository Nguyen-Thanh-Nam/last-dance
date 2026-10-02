# Surface Map AI

Ứng dụng nghiên cứu nhận diện bề mặt tấn công từ nguồn công khai, có snapshot/chứng cứ để kiểm tra nhận định. Bản hiện tại chạy với FastAPI + SQLite và frontend JavaScript/SVG. Kết quả kiểm thử và phần còn thiếu so với kế hoạch nằm trong [docs/PLAN_AUDIT.md](docs/PLAN_AUDIT.md).

## Cấu trúc

```text
../plan.md             kế hoạch nằm ngoài app/
BE/app/                Python backend
FE/                    frontend
scripts/               demo, đánh giá, kiểm tra curl
tests/                 bộ test
data/                 database, fixture và ground truth
docs/                  tài liệu và bằng chứng kiểm tra
.venv/                 môi trường Python cục bộ
.env                   cấu hình cục bộ
pyproject.toml         package/dependency và pytest
requirements-lock.txt  phiên bản dependency
Dockerfile             đóng gói Docker
docker-compose.yml     chạy Docker Compose
```

`BE/` và `FE/` là hai thư mục mã nguồn riêng. FE có server riêng tại `http://127.0.0.1:2222`; BE chỉ phục vụ API tại `http://127.0.0.1:3333`. FE gọi BE qua CORS; không cần Node build. PostgreSQL và React/Cytoscape trong kế hoạch ban đầu là lựa chọn kiến trúc đề xuất; bản MVP hiện dùng SQLite và JavaScript/SVG. Chưa có PostgreSQL adapter, React frontend hay triển khai nhiều worker.

FE dùng bố cục BankDash từ Figma, với thống kê/biểu đồ lấy dữ liệu OSINT của project. Icon, ảnh và font nằm trong `FE/assets/`; giao diện không tải tài nguyên từ URL Figma tạm thời. Chi tiết triển khai và giới hạn kiểm tra trực quan tại [docs/verification/FIGMA.md](docs/verification/FIGMA.md).

`BE/app/` là Python package dùng cho import `app.main`. Mọi code, dữ liệu, cấu hình, tài liệu và bộ test đều nằm trong thư mục `app/` ngoài cùng; kế hoạch giữ ở `../plan.md`. `.venv`, `.env` và database sử dụng được giữ lại. Cache Python/pytest đã sinh lại sau lượt kiểm tra mới và còn trong `app/` vì lệnh dọn bị kiểm duyệt tự động chặn. Chi tiết lượt gom thư mục trước tại [docs/verification/STRUCTURE.md](docs/verification/STRUCTURE.md).

## Chạy trên Windows

Dùng Python 3.11 trở lên. Từ thư mục chứa `app/` và `plan.md`, vào `app/` trước:

```powershell
Set-Location .\app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe scripts/start_dev.py
```

Mở http://127.0.0.1:2222, chọn **Thêm domain**, nhập một domain và bấm **Bắt đầu**. Hệ thống tự tạo project/website/phạm vi thu thập, xếp hàng website → DNS → CT → RDAP nếu bật → Google Dork → social → AI, hiển thị tiến độ và cập nhật danh mục/báo cáo. Không cần điền tên tổ chức, JSON, scope hoặc bấm Run collection lần nữa. Tải lại trang sẽ mở project đã chọn và tiếp tục theo dõi job. Gửi lại cùng domain dùng lại project tự tạo, tránh job trùng. Tên project ban đầu là domain, không phải xác nhận danh tính pháp lý của tổ chức.

Google Dork tạo các truy vấn giới hạn `site:<domain>` cho tài liệu và trang công khai. Muốn lấy kết quả tự động, cần quyền truy cập Google Custom Search JSON API hiện có và khai báo `GOOGLE_CSE_API_KEY`/`GOOGLE_CSE_ID`; nếu chưa cấu hình, log có các liên kết truy vấn Google để mở thủ công. Social URLs được tìm từ website snapshot trong scope. Chế độ tự động dùng passive và HTTPS; kiểm tra HTTP/TLS chủ động vẫn là tính năng có scope riêng trong cấu hình project. AI dùng provider/model/key đã khai báo trong `.env`; lỗi nguồn/provider được ghi trong Collection logs, dữ liệu các bước khác vẫn được giữ.

**Load demo** dùng rules-demo và dữ liệu giả lập cố định; không gọi Internet hoặc nhà cung cấp AI, kể cả khi đã cấu hình model thật. Không sử dụng demo làm kết quả thực nghiệm nghiên cứu.

Script khởi động cả hai server và Ctrl+C dừng cả hai. Nếu muốn chạy riêng, mở hai terminal trong `app/`:

```powershell
# Terminal BE
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir BE --host 127.0.0.1 --port 3333 --env-file .env --reload
# Terminal FE
.\.venv\Scripts\python.exe FE/serve.py --port 2222
```

Swagger: http://127.0.0.1:3333/docs. Linux/macOS dùng `.venv/bin/python` cho các lệnh tương ứng. FE/config.js mặc định gọi BE cùng hostname ở port 3333; khi dùng hostname khác, sửa URL trong file này và CORS_ORIGINS của BE.

Biến môi trường mặc định: ALLOW_PRIVATE_LAB=false, DATABASE_PATH=./data/surface_map.db, AI_PROVIDER=rules-demo, MAX_CRAWL_PAGES=12, MAX_CRAWL_DEPTH=2, REQUEST_DELAY_SECONDS=0.25, ENABLE_RDAP=false. Không tự đọc `.env` trong script. Để Uvicorn đọc `.env`, thêm `--env-file .env`; giữ credential ngoài Git.

## Thu thập và phạm vi

- `allowed_domains`: phạm vi lấy nội dung; kiểm tra ranh giới nhãn DNS và URL HTTP(S), không chứa credential.
- `authorized_assets`: hostname/URL chính xác được phép HTTP/TLS; hoặc dùng `authorized_scopes` với kind=hostname/domain/ip/cidr, value, allowed_tests và expires_at có timezone. Scope domain cho phép subdomain; scope hostname chỉ một host. IP/CIDR áp dụng khi URL dùng IP literal và IP đó cũng nằm trong allowlist.
- mode=authorized cùng phạm vi chủ động rõ ràng mới cho chạy probe. Để trống phạm vi chủ động sẽ chặn; tài sản AI/DNS/CT phát hiện không mở rộng quyền kiểm tra.
- Lab riêng chỉ cho phép địa chỉ private/loopback khi đồng thời đặt ALLOW_PRIVATE_LAB=true và allow_private=true trên scope chủ động phù hợp. Link-local, reserved, multicast và unspecified vẫn bị chặn. Giữ mặc định false khi dùng nguồn bên ngoài.
- Kiểm tra từng redirect; chặn private, loopback, reserved, mixed DNS/IPv6 và đích không phân giải được. Kết nối dùng IP đã kiểm tra, giữ Host/SNI và xác thực chứng chỉ TLS.
- Collector DNS lưu A/AAAA/CNAME/MX/NS và dấu hiệu wildcard; CT giữ cả mẫu wildcard và thời hạn lịch sử; RDAP opt-in với danh sách endpoint/redirect tin cậy đã khai báo trong collector. Registry ngoài danh sách có thể bị chặn và ghi lỗi.
- `passive_web` lấy nội dung website và DNS thực hiện tương tác mạng; tên preset passive không có nghĩa hoàn toàn không tương tác. Các nguồn bên thứ ba và việc lấy nội dung được phân biệt trong metadata.
- Crawl mặc định tối đa 12 trang, depth 2, delay 0.25s, tối đa 3 redirect/request, 500 KB/page, socket timeout 8s. Concurrency=1 và automatic retry=0; gửi lại job để retry có kiểm soát. CT/RDAP timeout 12s. Phân giải DNS hệ thống cho HTTP/TLS còn phụ thuộc timeout của OS.

Thu thập mặc định trả HTTP 202 và run_id; UI theo dõi `/runs/{id}`. SQLite lưu hàng đợi; worker chạy trong cùng process, từng collector có log và transaction. Job đang running khi process bị dừng được đánh dấu interrupted ở lần khởi động sau; queued vẫn được xử lý. Chạy một process Uvicorn worker; không dùng `--workers` nhiều process với cơ chế phục hồi hiện tại. Để gọi đồng bộ phục vụ kiểm thử, gửi background=false.

```json
{
  "organization_name": "Example Organization",
  "official_website": "https://example.org/",
  "allowed_domains": ["example.org"],
  "mode": "authorized",
  "authorized_scopes": [
    {"kind": "hostname", "value": "example.org", "allowed_tests": ["http", "tls"], "expires_at": "2026-12-31T23:59:59+07:00"}
  ]
}
```

## Chứng cứ và duyệt

Source lưu nội dung, URL, thời gian, SHA-256, run ID và chunk với offset. Asset giữ các observation qua lần thu thập. Claim giữ mọi evidence supports/refutes; thêm counter-evidence chuyển claim về needs_review. Review lưu người duyệt, lý do, thời gian, trạng thái trước/sau. Thu thập tiếp không ghi đè quyết định duyệt cũ.

Asset classification là controlled/third_party/candidate/insufficient_evidence/rejected, độc lập với trạng thái claim confirmed/related/needs_review/rejected và độc lập với scope. Giao diện cho phép duyệt cả claim và classification. DNS/CT/TLS hoặc IP dùng chung không tự xác nhận sở hữu. Điểm confidence được hiển thị là heuristic rank, không phải xác suất đã hiệu chỉnh.

Manual social assertion cần duyệt; chỉ backlink tồn tại trong snapshot website chính thức mới tự xác nhận liên kết kênh. Xem docs/SOCIAL_OSINT.md. Giao diện lọc tài sản theo type/status/source/search, mở lịch sử tài sản, lọc đồ thị theo status/depth và mở evidence bằng cạnh đồ thị.

## AI và thực nghiệm

Model thật dùng AI_PROVIDER=openai-compatible, AI_BASE_URL, AI_API_KEY và AI_MODEL. Adapter gọi `/chat/completions`, giới hạn 20 nguồn khác hash, 30.000 ký tự tổng, 6.000 ký tự/nguồn, 500 asset và temperature=0. Schema kiểm tra loại thực thể/quan hệ, ID phải tồn tại đúng project, quote phải có trong source. Nội dung nguồn là dữ liệu không đáng tin cậy và không điều khiển lệnh/phạm vi. Output, input hash, model, prompt/schema version, duration và usage được lưu. Chi phí tiền tệ để null nếu chưa cấu hình bảng giá.

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py --output docs/verification/evaluation.json
.\.venv\Scripts\python.exe scripts/evaluate.py --with-ai --output docs/verification/ai-evaluation.json
```

Script dùng DB tạm, không thay đổi DB người dùng. B0 luôn là rules-demo; B1 chỉ chạy khi yêu cầu --with-ai và có cấu hình model thật. Hướng dẫn gán nhãn độc lập, chia tập, khóa cấu hình và đánh giá report thực nằm trong docs/LABELING_GUIDE.md. Các số trên fixture nhỏ kiểm tra chức năng; không chứng minh Precision 90% trên tổ chức thật.

## Kiểm thử

Chạy các lệnh sau trong thư mục `app/`.

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py
.\.venv\Scripts\python.exe scripts/smoke_api.py
.\.venv\Scripts\python.exe scripts/smoke_split_ports.py
.\.venv\Scripts\python.exe scripts/check_frontend.py
.\.venv\Scripts\python.exe scripts/smoke_setup.py
node --check FE/app.js
```

`smoke_api.py` tự khởi động server ở port trống với DB tạm, gọi curl.exe/curl thật, kiểm tra các API theo OpenAPI và dừng server khi xong. Không quét tổ chức bên ngoài. DNS/CT/RDAP/TLS và nhà cung cấp AI được kiểm tra bằng fixture/mocks; kiểm tra từ chối đích nội bộ chạy qua server thật. Kết quả nằm trong docs/verification/. Chạy script chỉ tạo dữ liệu tạm của test, không xóa project người dùng.

`run_tests.py` chạy pytest trong thư mục tạm mới, tránh lỗi quyền của cache temp Windows cũ. `check_frontend.py` cần Node và kiểm tra logic với DOM stub, không thay thế E2E trình duyệt. Khi server thật đang chạy, dùng `scripts/smoke_frontend.py` bằng Python để curl chỉ đọc FE/CORS. `smoke_split_ports.py` cần hai port đang trống; không dùng `--external` với database project thật vì runner đó tạo/xóa dữ liệu kiểm thử.

## API

OpenAPI tại `/openapi.json`, Swagger tại `/docs`, ReDoc tại `/redoc`. Tài liệu tĩnh trong docs/API.md.

- Projects: create/list/detail/delete, demo/load.
- Collect: enqueue/sync; list runs/detail/progress/logs.
- Assets: list/filter/detail/observations; PATCH classification.
- Social, relationships, graph, claim detail/review/history.
- POST claim evidence với supports/refutes; GET saved source/chunks.
- Export JSON/HTML báo cáo và CSV danh mục.

## Docker

Chạy Compose trong thư mục `app/` để dùng đúng Dockerfile, .env và build context.

```powershell
docker compose config --quiet
docker compose up --build
```

Compose dùng `.env`, named volume riêng cho DB, user non-root, filesystem read-only ngoài volume, drop capabilities và healthcheck. Ghi dependency trong requirements-lock.txt; Docker cài đúng các phiên bản này. Compose có hai service độc lập: backend ở port 3333 và frontend ở port 2222, bind localhost. CORS_ORIGINS mặc định chỉ cho http://127.0.0.1:2222 và http://localhost:2222. Không dùng SURFACE_MAP_PORT cũ. Đây là ứng dụng nghiên cứu một người dùng trên máy/lab; chưa có authentication, tenant isolation hay triển khai công khai nhiều người dùng.
