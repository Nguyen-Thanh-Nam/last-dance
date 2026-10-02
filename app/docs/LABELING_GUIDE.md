# Hướng dẫn gán nhãn và khóa bộ đánh giá

Fixture `data/fixtures/acme/manifest.json` dùng để kiểm thử chức năng. Nhãn fixture được duy trì cùng code, không có hai người gán nhãn độc lập và không được dùng để chứng minh chất lượng AI trên tổ chức thật.

## Thu thập bộ dữ liệu nghiên cứu

Mỗi tài liệu cần có: document_id, organization, source_url/source_type, snapshot_path, collected_at, sha256, language, split, điều kiện sử dụng, ngày khóa dữ liệu và phạm vi được phép. Ghi tài liệu không truy cập được thành missing_data; không thay bằng dữ liệu giả rồi tính như dữ liệu thật. Snapshot công khai có thể dùng cho trích xuất offline; quyền kiểm tra HTTP/TLS là cấu hình riêng.

Chia tập theo tổ chức/tài liệu và nhóm nguồn có cùng SHA-256. Một nguồn sao chép không được xuất hiện ở cả development và evaluation. Tập Acme hiện được đánh dấu development; cần ít nhất lab có danh mục chuẩn và hai hồ sơ tổ chức như mục 9 của plan.md. Không tự nhận đã có bộ này.

## Quy tắc nhãn

- Entity: loại, tên chuẩn hóa, tên gọi khác và source/document ID. Trùng tên không tự là cùng thực thể.
- Asset: loại + giá trị chuẩn hóa, trạng thái controlled/third_party/candidate/insufficient_evidence/rejected. IP dùng chung và DNS/CT/TLS không đủ xác nhận quyền quản lý.
- Relation: subject, predicate, object, label=true/false/unknown, nguồn và đoạn trích, vai trò supports/refutes, lý do. Khóa URL giữ phân biệt hoa thường ở path/query.
- Evidence: có đoạn trích và hash chỉ xác nhận truy xuất; người gán nhãn phải đánh giá đoạn đó có hỗ trợ nhận định hay không.
- Nhãn unknown được báo cáo riêng, không tính tùy tiện thành true hoặc false. Danh sách positive chưa đầy đủ không phải closed-world ground truth.

Hai thành viên gán nhãn riêng trước khi xem dự đoán; lưu hai phiếu cùng thời gian và lý do. Lưu bất đồng và nhãn adjudicated sau thảo luận. Không điền tên/ngày/chữ ký giả. Chỉ chỉnh luật/prompt/ngưỡng trên development; khóa evaluation, model, prompt/schema version, SHA-256 và requirements-lock.txt trước khi đo.

## Chạy đánh giá

`python scripts/evaluate.py --output docs/verification/evaluation.json` chỉ chạy fixture B0 trong DB tạm.

Với report thực:

```powershell
python scripts/evaluate.py --snapshot data/B0-report.json --comparison-snapshot data/B1-report.json --ground-truth data/real-ground-truth.json --output docs/verification/real-evaluation.json
```

Hai report phải dùng cùng seed và tập hash snapshot. Không chạy thêm nguồn trực tiếp riêng cho B1. Ground truth dùng schema trong data/evaluation_ground_truth.json; ghi excluded_seed_hosts rõ ràng. Mọi dự đoán có kết luận nằm trong phạm vi nhiệm vụ phải được tính, bao gồm false positive. Zero denominator hiện trả 0; các bucket không có dự đoán cần ghi rõ không có mẫu thay vì suy ra độ chính xác bằng 0.

Script đã đo thực thể theo các loại khai báo trong ground truth; cần bổ sung bộ nhãn thật theo từng loại và chất lượng hỗ trợ ngữ nghĩa của chứng cứ bằng người gán nhãn, độ mới/độc lập, mức ổn định qua lần lặp và thời gian duyệt. Script hiện tự động hóa Precision/Recall/F1 thực thể, tài sản và quan hệ; chưa tự đánh giá được các tiêu chí thủ công này.
