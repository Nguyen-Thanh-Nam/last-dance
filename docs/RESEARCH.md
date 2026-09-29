# Cơ sở phương pháp

## 1. Nhóm nguồn OSINT

| Nhóm nguồn | Dữ liệu kỹ thuật | Dữ liệu tổ chức | Ưu điểm | False positive thường gặp |
| --- | --- | --- | --- | --- |
| Website và sitemap chính thức | URL, host, endpoint, tên tham số, liên kết | thương hiệu, sản phẩm, dự án, kênh chính thức | nguồn trực tiếp, dễ truy nguyên | trang cũ, liên kết nhà cung cấp hoặc đối tác |
| DNS và Certificate Transparency | domain, subdomain, A/AAAA, thời hạn chứng thư | không trực tiếp | thụ động, có lịch sử | domain cũ, môi trường thử nghiệm, tên thuê chung |
| Kho mã nguồn/tài liệu công khai | URL API, hostname, cấu hình công khai | tên sản phẩm/dự án và maintainer | giàu chi tiết kỹ thuật | fork, ví dụ mẫu, secret đã hết hạn |
| Mạng xã hội và bài đăng công khai | URL ứng dụng, campaign domain, link tracking | brand, sản phẩm, dự án, thông báo | liên kết hoạt động kinh doanh với URL | tài khoản giả, đại lý, bài đăng cũ, link rút gọn |
| Nguồn đăng ký/IP/ASN/CDN | registrar, IP, ASN, nhà cung cấp | pháp nhân nếu dữ liệu công khai | bổ trợ cho đối chiếu | privacy proxy, CDN/shared hosting, công ty cùng tên |
| Nguồn bên thứ ba | bài báo, tuyển dụng, cộng đồng | đối tác, sản phẩm, hoạt động | mở rộng ngữ cảnh | sao chép, trích dẫn thiếu nguồn, suy diễn sở hữu |

RDAP/đăng ký IP-domain là nguồn bổ trợ cho registrar, ASN và hosting; chỉ chạy khi bật rõ ràng vì cần request ra Internet.

Collector phải lưu dữ liệu gốc, URL hoặc định danh nguồn, thời điểm thu thập, phương pháp và lỗi. Độ mới được biểu diễn bằng `collected_at`, `published_at` (nếu có) và trường thời hạn chứng thư/DNS khi nguồn cung cấp. Một lần chạy mới không xóa bằng chứng cũ.

## 2. Thụ động và chủ động

`passive` chỉ đọc nguồn công khai: website chính thức, DNS resolver, CT log và bản ghi social đã cung cấp hoặc trang công khai. Không port scan, brute force, đăng nhập, tham gia nhóm kín hay lập hồ sơ cá nhân.

`authorized` cho phép HTTP GET/crawl giới hạn trên allowlist. Mỗi request kiểm tra scheme, host, allowlist, địa chỉ private/loopback và redirect mới. Giới hạn page/depth/delay được cấu hình qua biến môi trường. Collector lỗi được ghi trong `collector_logs` và không hủy các collector khác.

## 3. Chuẩn hóa và loại trùng

- Domain: lowercase, bỏ dấu chấm cuối, bỏ `www.` ở biểu diễn gốc, tách hostname khỏi URL.
- URL: lowercase scheme/hostname, bỏ fragment, bỏ port mặc định, giữ path.
- Endpoint: giữ tên tham số theo thứ tự alphabet nhưng thay giá trị bằng rỗng; vì vậy hai URL khác giá trị query vẫn hợp nhất.
- Tên tổ chức/brand/product: trim, gộp whitespace, `casefold`; tên hiển thị gốc vẫn giữ để đối chiếu.
- Social URL: platform + profile URL là khóa hợp nhất; post permalink là khóa hợp nhất.

Việc hợp nhất chỉ làm giảm bản ghi trùng, không tự nâng mức xác minh. Tài sản từ CT hoặc bài đăng vẫn là `discovered/related/needs_review` cho đến khi có chứng cứ trực tiếp.

## 4. Phân loại quan hệ

| Lớp | Tiêu chí tối thiểu | Ví dụ | Không đủ để kết luận |
| --- | --- | --- | --- |
| `owned` | nguồn chính thức nói hoặc liên kết trực tiếp quyền sở hữu/đăng ký | website chính thức liên kết tài khoản Facebook chính thức | cùng IP, cùng CDN, tên giống |
| `operated` | nguồn chính thức cho thấy tổ chức vận hành dịch vụ | trang trạng thái thuộc domain chính thức | nhà cung cấp hosting |
| `used` | sản phẩm/tài liệu chính thức dùng hoặc liên kết tới tài sản | bài sản phẩm dẫn tới `app.example.org` | host chỉ xuất hiện trong DNS |
| `partner` | nguồn chỉ rõ đối tác hoặc quan hệ cung ứng | trang đối tác của tổ chức | coi domain đối tác là tài sản tổ chức |
| `mentioned` | chỉ được nhắc tới trong bài viết/post | bài đăng nhắc sản phẩm của bên khác | suy diễn sở hữu |
| `unknown` | chưa đủ căn cứ để chọn lớp | CT candidate chưa có backlink | mô hình tự tạo URL hoặc nguồn |

Shared IP/CDN, công ty trùng tên, domain đại lý và bài đăng cũ luôn giữ trạng thái review cho đến khi có nguồn độc lập phù hợp. `confidence` không phải sự thật do mô hình tự quyết định; hệ thống kết hợp chất lượng loại nguồn, độ trực tiếp của quote và điểm mô hình sau kiểm tra schema.

## 5. AI có kiểm soát

Đầu vào adapter gồm project scope, catalog `Source` và catalog tài sản đã tồn tại. Schema đầu ra chỉ cho phép entity và relationship tham chiếu `source_id`/`asset_id` trong catalog. Service kiểm tra:

1. source ID phải tồn tại trong project;
2. quote phải là đoạn văn bản xuất hiện trong raw content sau khi chuẩn hóa whitespace;
3. subject/object phải resolve về entity hoặc asset đã lưu;
4. quan hệ thiếu chứng cứ chuyển `needs_review`, confidence tối đa 0.25;
5. URL, nguồn và dữ liệu kỹ thuật không có trong catalog không được tạo mới.

`rules-demo` là adapter deterministic cho demo offline, không được gọi là AI thật. `openai-compatible` chỉ chạy khi có endpoint/key/model và kết quả phải qua cùng validation.

## 6. Đánh giá

Với tập ground truth có nhãn thủ công, tài sản và quan hệ được tính precision, recall và F1 theo giá trị chuẩn hóa. Tách kết quả theo `confirmed`, `related/probable` và `needs_review` để không che giấu false positive. `traceability_rate` là tỷ lệ claim có evidence hợp lệ, source URL/định danh, thời gian thu thập và quote; `source_reachable_rate` chỉ được tính khi chạy kiểm tra URL thực tế, không bịa khi offline.

Các trường hợp cần ghi lại gồm: đúng (post chính thức dẫn tới app), sai dương tính (host CT cũ hoặc CDN), sai âm tính (social page bị chặn fetch), và nguyên nhân (thiếu backlink, nguồn hết hạn, collector lỗi).
