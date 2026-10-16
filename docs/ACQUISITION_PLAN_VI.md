# Kiểm chứng khách trả phí đầu tiên — ShelfWatch

Mục tiêu 14 ngày: tìm một shop/agency thực sự tạo lịch theo dõi và quay lại dùng,
không đặt mục tiêu tăng số lượt chạy thử của chủ dự án. Mọi nội dung bên dưới là
kế hoạch; chưa có tin nhắn hay bài đăng nào được gửi tự động.

## Khách đầu tiên cụ thể

Agency e-commerce hoặc shop DTC có khoảng 10–50 URL sản phẩm Shopify của đối thủ
và hiện đang mở từng link để kiểm tra giá/size còn hàng. Người chưa có watchlist
hoặc chỉ muốn tải cả catalogue một lần không phải nhóm ưu tiên cho bản này.

## Các bước thực hiện

1. Chọn một nhóm cộng đồng có quy định cho phép giới thiệu công cụ phù hợp.
   Dùng bài nháp trong LAUNCH_POSTS.md, ghi rõ phí kể cả không đổi và giới hạn nguồn.
   Không đăng hàng loạt, gửi DM tự động hay sử dụng email lấy từ dữ liệu scrape.
2. Mời người quan tâm dùng 2–5 URL của chính họ. Đưa ví dụ CSV/alert và hướng dẫn
   đọc nguồn. Ví dụ test trên Allbirds/Death Wish không phải khách hàng chứng thực.
3. Xem cùng họ một kết quả đúng và một tình huống không có alert. Nếu nguồn bị chặn
   hoặc currency không nhận diện được, ghi nhận thay vì hứa hỗ trợ mọi store.
4. Hướng dẫn Save task → Schedule, giữ nguyên monitorName. Hỏi họ có dùng đầu ra
   để quyết định gì không, alert nào thừa/thiếu và có quay lại tuần sau không.
5. Ghi dữ liệu tổng hợp vào acquisition-log.csv, không ghi thông tin cá nhân không
   cần thiết. Chỉ coi Paying users/Profit trong Apify Insights là tín hiệu doanh thu.

## Mốc đánh giá

- Ngày 3: có ai đưa URL thật và hoàn thành lần chạy đầu không?
- Ngày 7: có ai tạo task/lịch hoặc chạy lại cùng monitorName không?
- Ngày 14: có khách trả phí, phản hồi hữu ích hoặc lý do bỏ cuộc cụ thể không?

Nếu không có lượt quay lại, ưu tiên sửa onboarding/nguồn/đầu ra theo phản hồi.
Không mua quảng cáo trước khi một người dùng xác nhận giá trị. 50 sản phẩm × 30
ngày × $0.002 = $3 phí Actor của khách, không phải $3 lợi nhuận ròng của chủ dự án;
phí nền tảng và chi phí phát sinh còn được trừ. Không có cam kết doanh thu $5.
