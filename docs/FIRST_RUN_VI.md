# Dùng ShelfWatch để theo dõi giá và restock

Khách phù hợp: shop/agency theo dõi sản phẩm đối thủ, người làm trang so sánh giá
hoặc bản tin deal đã có danh sách sản phẩm cần xem lại mỗi ngày.

1. Mở Actor, dán các URL trang sản phẩm Shopify vào **Product URLs**. Dùng URL
   `https://.../products/ten-san-pham`, bỏ `?variant=...` và mã tracking.
2. Đặt `monitorName`, ví dụ `doi-thu-giay`. Mỗi tên là một lịch sử độc lập trong
   tài khoản Apify của người chạy; dữ liệu các khách không dùng chung.
3. Chạy với 2 sản phẩm trước. Hai kết quả thành công có phí Actor **$0.004**.
   Lần đầu là `FIRST_OBSERVATION`, không phải chứng minh sản phẩm vừa ra mắt.
4. Xem dataset/`checks.csv` để kiểm tra giá, biến thể và URL nguồn. `ALERTS`,
   `alerts.csv`, `alerts.ndjson`, `digest.md` chỉ mô tả các thay đổi được quan sát.
5. **Save as a new task**, rồi tạo lịch chạy hằng ngày, giữ nguyên monitorName.
   Actor tự đọc baseline; bạn không phải sao chép snapshot. Chưa có lịch nào
   được tự tạo trong tài khoản chủ dự án, tránh phát sinh chạy định kỳ ngoài ý muốn.

**Phí tính trên mỗi sản phẩm kiểm tra thành công đã lưu, kể cả không đổi.**
Một sản phẩm có nhiều biến thể vẫn chỉ là một lượt. Trang lỗi/bị chặn không có
sự kiện kiểm tra. Báo cáo và alert không tính thêm. Thông tin giá hiện hành trên
Store có quyền ưu tiên; storage và gói Apify của khách có điều kiện riêng.

## Hiểu kết quả

- `PRICE_DROP`, `PRICE_RISE`: giá biến thể đổi so với lần lưu trước, cùng currency
  đã nhận diện. Chỉ báo giá quan sát, không tính phí ship/checkout/subscription.
- `BACK_IN_STOCK`, `OUT_OF_STOCK`: cờ có thể mua thay đổi. Đây không phải số lượng
  tồn kho; preorder/backorder vẫn có thể được đánh dấu có thể mua.
- `VARIANT_FIRST_OBSERVATION`: biến thể chưa có trong baseline đang giữ, không
  đảm bảo vừa được tạo. Nguồn tối đa 250 biến thể và có thể không đầy đủ.
- `NO_ALERT`: không có điều kiện alert phù hợp. Thay đổi nhỏ dưới ngưỡng hoặc
  giá chưa rõ currency có thể không tạo alert. Lần kiểm tra vẫn tính phí.
- `minPriceChangePercent` chỉ lọc alert tăng/giảm giá, so với lần kiểm tra đã
  lưu liền trước. Baseline vẫn cập nhật khi biến động nhỏ bị lọc; không cộng dồn.

Không suy luận sản phẩm/biến thể bị xóa từ lỗi tải hoặc sự vắng mặt. Nếu đổi tên
monitor, URL/locale hoặc xóa state store, lịch sử tương ứng sẽ bắt đầu lại.
Không đổi tên monitor nếu bạn muốn tiếp tục lịch theo dõi cũ.

## Lỗi và tính liên tục

Actor tuân thủ robots, không vượt CAPTCHA hay đăng nhập. Website headless,
đổi nền tảng hoặc chặn request có thể không hỗ trợ. Xem `DIAGNOSTICS` khi lỗi.
Không gửi alert ra email/Slack tự động; bạn kết nối đầu ra qua workflow của mình.

Hai lượt cùng monitor không được ghi đồng thời. Lượt đang bận sẽ dừng trước khi
tải sản phẩm/tính phí; khóa sau một lần crash hết hạn trong 10 phút. Chỉ kết quả
đã lưu và tính phí mới cập nhật baseline. Nếu ghi state lỗi sau khi lưu dataset,
lượt chạy báo lỗi; kết quả đã lưu vẫn có trong dataset. Dùng `eventId` để bỏ trùng
khi gửi thông báo lại. Đây không phải hệ thống đảm bảo giao thông báo đúng một lần.

`SUMMARY` có `stateStoreId`, số lượt lưu/tính phí và `baselineWrites`. Storage
riêng vẫn tồn tại đến khi bạn xóa nó và có chi phí lưu trữ theo gói Apify.
Muốn reset an toàn, dùng một monitorName mới.

## Với chủ dự án muốn có khách đầu tiên

Dùng [bài giới thiệu nháp](LAUNCH_POSTS.md) và [kế hoạch tìm khách](ACQUISITION_PLAN_VI.md).
Ưu tiên một người đang làm công việc này thủ công và đo xem họ có tạo lịch chạy
lại không. Bản build/test không phải doanh thu; xem Paying users và Profit trong
Insights → Monetization. Không có cam kết lượt mua hoặc thu nhập.
