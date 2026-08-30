# Ideas Hub CMS

CMS là control plane cho dữ liệu market intelligence. Dashboard công khai dùng để đọc và khám phá; CMS dùng để vận hành, kiểm tra và duyệt dữ liệu.

## Use cases đã triển khai

| Khu vực | Nhu cầu vận hành | Hành động trong CMS |
| --- | --- | --- |
| Nguồn dữ liệu | Thêm RSS mới mà không cần gọi API thủ công | Tạo ứng viên, chạy validation rồi mới kích hoạt |
| Nguồn dữ liệu | Nguồn lỗi, chất lượng thấp hoặc cần tạm dừng | Chỉnh sửa metadata, bật/tắt nhưng không xoá lineage |
| Khám phá nguồn | Tự mở rộng publisher từ bài đã crawl | Xem điểm, hard gate, feed, bài mẫu và bằng chứng nguồn dẫn |
| Khám phá nguồn | Human-in-the-loop cho ứng viên 60–84 điểm | Approve, reject hoặc rescan; nguồn duyệt bootstrap 3 bài |
| Pipeline | Cần lấy dữ liệu ngay thay vì chờ lịch 30 phút | Enqueue một nguồn hoặc tất cả nguồn đang bật |
| Pipeline | Theo dõi tốc độ và lỗi crawl | Xem lần chạy gần nhất, duration, số bài mới và failures theo source |
| Content QA | LLM trích xuất thiếu hoặc sai ngữ cảnh | Sửa tiêu đề, URL, tác giả và 8 nhóm insight |
| Event curation | Cụm máy tạo có tên khó đọc hoặc thiếu diễn giải | Sửa tên và tóm tắt cụm sự kiện |
| Opportunity review | Cần human-in-the-loop trước khi coi là cơ hội thật | Sửa luận điểm và chuyển trạng thái candidate → reviewing → validated/rejected/archived |

## Quyết định phạm vi

- Không xoá cứng source, article hoặc event từ UI. Các record này tạo thành chuỗi bằng chứng; xoá có thể làm hỏng event, signal và opportunity liên quan.
- CMS hiện dành cho môi trường local/internal. Trước khi public ra Internet cần thêm authentication, role-based access và audit log.
- Crawl chạy bất đồng bộ qua Celery để thao tác UI không bị treo trong lúc tải và phân tích bài.
