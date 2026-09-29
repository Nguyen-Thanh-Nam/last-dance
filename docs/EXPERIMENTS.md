# Thiết kế thực nghiệm

## Bộ dữ liệu

`data/evaluation_ground_truth.json` là fixture có nhãn thủ công cho Acme Robotics giả lập. Nó có:

- một trang chính thức;
- tài khoản Facebook được website liên kết;
- bài đăng công khai giới thiệu Fleet Console;
- URL app, host status và endpoint có hai bộ giá trị query;
- quan hệ đúng và trường hợp không đủ căn cứ.

Fixture không đại diện cho tổ chức thật và không được dùng làm bằng chứng ngoài hệ thống.

## Chỉ số

- `precision = TP / (TP + FP)`;
- `recall = TP / (TP + FN)`;
- `F1 = 2PR / (P + R)`;
- `traceability_rate = claims có source + quote hợp lệ / tổng claims`;
- `confidence_bucket_accuracy`: độ chính xác trong từng bucket confirmed, related/probable, needs_review;
- duplicate reduction: số URL đầu vào và số endpoint sau chuẩn hóa;
- thời gian xử lý: duration từng collector và tổng run.

`python scripts/evaluate.py` chạy cùng fixture cho rules-demo. Khi có AI thật, đặt `AI_PROVIDER=openai-compatible`, ghi lại model/endpoint/thời gian chạy và chạy lại trên cùng fixture; script không tự gọi AI khi thiếu cấu hình và ghi rõ `not_run`.

## Báo cáo lỗi

Kết quả phải kèm ví dụ TP, FP, FN và nguyên nhân. Ví dụ FP là chứng thư CT cũ hoặc host CDN; FN là bài đăng Facebook không fetch được và cần nhập thủ công. Không điền số liệu truy cập nguồn thật nếu chưa chạy kiểm tra mạng.
