# Thiết kế và kết quả thực nghiệm

Xem docs/LABELING_GUIDE.md cho quy tắc nhãn, chia tập, adjudication và khóa cấu hình.

## Đã chạy

B0 trên Acme giả lập, gồm 3 asset cần phát hiện, 2 entity (product/project), 5 quan hệ có nhãn true và negative labels cho root/status. Known root-domain seed không được tính như asset mới phát hiện. Snapshot vật lý và manifest nằm trong data/fixtures/acme/. Nhãn v2 được duy trì cùng code, không phải held-out data hoặc nhãn độc lập của hai người.

Kết quả chạy hiện tại được lưu trong docs/verification/evaluation.json. Script đếm mọi dự đoán có kết luận theo phạm vi nhiệm vụ, kể cả false positives; có regression test thêm asset sai để đảm bảo Precision giảm. URL giữ semantics path/query. Zero denominator trả 0, bucket không có dự đoán phải được diễn giải là không có mẫu.

B0 dùng rules-demo trong DB tạm và không lấy kết quả AI đã lưu từ DB người dùng. B1 là B0 cộng provider thật trên đúng các nguồn đã lưu, chỉ chạy khi có --with-ai và cấu hình đầy đủ. Demo UI luôn dùng rules-demo để bảo đảm offline, không thay provider nghiên cứu bằng fixture mà gọi đó là AI thật.

## Chỉ số tự động

Precision/Recall/F1 thực thể theo evaluated_entity_types, tài sản theo khóa type+canonical_value, quan hệ theo bộ ba; relation metrics theo predicate; confidence buckets, coverage, số needs_review, evidence traceability và FP/FN. Evidence traceability cần source URL, timestamp, hash và quote valid; không đo thay độ hỗ trợ ngữ nghĩa.

ModelRun lưu provider/model, prompt/schema version, input hash, output, temperature, duration và token usage nếu provider trả về. Currency cost=null khi chưa có bảng giá. Không suy ra chi phí từ model confidence.

## Chưa chạy

Không có kết quả độc lập về model thật, nguồn Internet reachable rate, hai hồ sơ tổ chức thật, gán nhãn hai người, Precision tin cậy cao 90%, đánh giá thời gian duyệt, độ ổn định model hoặc chất lượng ngữ nghĩa evidence. Các giá trị này phải được đo khi nhóm cung cấp dữ liệu, phạm vi và cấu hình.

## Lỗi được phát hiện trong audit

- Precision asset trước đây chỉ lấy dự đoán có trong ground truth, làm mất false positives; đã sửa và có regression test.
- Luật sản phẩm trước đây gán cả root/status cùng tài liệu cho sản phẩm; đã dùng ngữ cảnh anchor/link và negative cases.
- Nhãn fixture thiếu quan hệ product -> normalized endpoint được chính source liên kết; đã bổ sung vào nhãn v2 và ghi lý do, không trình bày đây là nghiên cứu độc lập.
- Manual assertion về official channel trước đây tự confirmed bằng từ khóa; hiện cần backlink snapshot hoặc review.
- Claim/entity ID do model bịa và quote sai được chặn/review; schema/quote existence vẫn không chứng minh nhận định đúng ngữ nghĩa.

Không tự điền số liệu thật chưa đo hoặc chọn kết quả model tốt nhất sau nhiều lần chạy.
