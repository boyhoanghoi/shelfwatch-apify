# Launch drafts — not sent

## English — e-commerce / automation community

I built ShelfWatch for teams who already keep a list of competing Shopify
products and check their prices or sizes manually.

Paste product URLs, run once, then schedule the same monitor. It remembers your
previous saved checks and returns variant price changes, restocks and sold-out
observations as JSON/CSV. You can forward the useful events through your own
n8n/Make workflow; the Actor does not send messages itself.

Pricing is $0.002 per successful product check, including checks with no change;
variants and alert exports are included. Public compatible Shopify themes only,
up to 250 exposed variants, no exact inventory counts or access bypasses.

I'm looking for feedback from someone already monitoring 10–50 product URLs.
Does the sample output replace a manual check you currently do?

Actor: https://apify.com/reliable_quatrain/shopify-price-restock-monitor-shelfwatch

## Tiếng Việt — nhóm bán hàng / automation

Mình làm ShelfWatch cho shop hoặc agency đang phải mở từng link sản phẩm Shopify
để xem đối thủ đổi giá hay size/màu nào có thể mua lại.

Nhập URL sản phẩm, chạy lần đầu và đặt lịch với cùng tên monitor. Công cụ tự nhớ
lần kiểm tra trước, xuất thay đổi ở từng biến thể và file CSV/JSON để nối workflow.
Không cần tự sao chép snapshot giữa các lần chạy.

Phí $0.002/sản phẩm kiểm tra thành công, kể cả không đổi; biến thể/alert không
tính thêm. Chỉ hỗ trợ storefront Shopify tương thích và dữ liệu công khai, không
phải số tồn kho chính xác. Nguồn bị chặn có thể không dùng được.

Mình muốn nhận phản hồi từ người đang kiểm tra khoảng 10–50 link thủ công xem
đầu ra này có giúp tiết kiệm một việc lặp lại không.

Actor: https://apify.com/reliable_quatrain/shopify-price-restock-monitor-shelfwatch
