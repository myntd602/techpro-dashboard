# Bot báo cáo KPI tự động trên Lark và Telegram

Bot tự gom số liệu từ 2 nguồn rồi gửi thẻ báo cáo vào nhóm Lark, và/hoặc nhóm Telegram (xem Bước 6):

- **Google Sheet** tab `KPI_Tháng` (cùng nguồn với dashboard): GMV, doanh thu, sàn… — nhập tay.
- **TikTok Ads + Meta Ads API**: chi tiêu, kết quả của các tài khoản quảng cáo khách hàng — **tự lấy, không nhập tay** (xem Bước 5).

Hai nguồn độc lập: có nguồn nào thì báo cáo nguồn đó. Nơi nhận cũng vậy: khai Lark thì gửi Lark, khai Telegram thì gửi Telegram, khai cả hai thì gửi cả hai cùng một nội dung.

| Lịch gửi (giờ VN) | Loại |
|---|---|
| 08:30 hằng ngày | Báo cáo ngày |
| 09:00 thứ Hai | Báo cáo tuần |
| 09:00 ngày 1 hằng tháng | Báo cáo tháng |

Thẻ báo cáo gồm: 4 nhóm chỉ số (Tổng quan, TikTok Shop, Shopee, Quảng cáo), so sánh với kỳ trước (🟢 tốt lên / 🔴 xấu đi), % đạt mục tiêu, và mục **⚠️ Cần xử lý** ở đầu thẻ. Khi có cảnh báo, thẻ chuyển màu đỏ.

> Lưu ý: GitHub có thể gửi trễ 5–30 phút so với giờ hẹn vào giờ cao điểm.

---

## Bước 1 — Chuẩn bị Google Sheet (5 phút)

Tab `KPI_Tháng` giữ nguyên như dashboard đang dùng, **thêm 2 cột tuỳ chọn**:

| A: Chỉ số | B: Giá trị | C: Mục tiêu | D: Kỳ trước |
|---|---|---|---|
| GMV_thuc_te | 1240000000 | 1500000000 | 1045000000 |
| ROAS | 6.3 | 6 | 5.9 |
| Chi_phi_Ads | 156000000 | 150000000 | 127800000 |

- Cột C để trống thì không tính % mục tiêu; cột D để trống thì không so sánh kỳ trước.
- Với chi phí, CPO, CPC, tỷ lệ hoàn hàng: cột C là **mức trần** (vượt trần mới bị cảnh báo).
- Nên nhập số thô (`156000000`), không nhập `156M`.
- File mẫu đầy đủ 19 chỉ số: `lark-report/sample_kpi.csv`.

Lấy link CSV: **File → Chia sẻ → Xuất bản lên web** → chọn tab `KPI_Tháng` → chọn **.csv** → Xuất bản → copy link (link có `output=csv`).

## Bước 2 — Tạo bot trong nhóm Lark (2 phút)

1. Mở nhóm Lark muốn nhận báo cáo (ví dụ nhóm "Ban điều hành").
2. **Settings → Bots → Add Bot → Custom Bot**. Đặt tên: `TechPro Report`.
3. Copy **Webhook URL**.
4. Bật **Signature verification** (khuyến nghị) → copy **Secret**.

Không nên chỉ dùng "Keyword" — ai có link webhook cũng gửi được tin vào nhóm.

## Bước 3 — Khai báo trên GitHub (3 phút)

Vào repo `techpro-dashboard` → **Settings → Secrets and variables → Actions**.

Tab **Secrets** → **New repository secret**, tạo các mục (nếu chỉ dùng số liệu Ads thì bỏ qua `KPI_CSV_URL`):

| Tên | Giá trị |
|---|---|
| `KPI_CSV_URL` | Link CSV ở Bước 1 |
| `LARK_WEBHOOK_URL` | Webhook URL ở Bước 2 |
| `LARK_WEBHOOK_SECRET` | Secret ở Bước 2 |

Tab **Variables** (tuỳ chọn):

| Tên | Ý nghĩa | Mặc định |
|---|---|---|
| `DASHBOARD_URL` | Link dashboard, hiện nút "Mở dashboard" trên thẻ | không có nút |
| `ROAS_MIN` | Cảnh báo khi ROAS dưới mức này | 4 |
| `RETURN_MAX` | Cảnh báo khi tỷ lệ hoàn hàng (%) trên mức này | 3 |
| `TARGET_MIN` | Cảnh báo khi đạt dưới X% mục tiêu | 80 |

## Bước 4 — Gửi thử

**Actions → Báo cáo KPI gửi Lark và Telegram → Run workflow** → chọn loại báo cáo → **Run**. Khoảng 30 giây sau thẻ xuất hiện trong nhóm Lark.

Nếu lỗi (dấu ✗ đỏ), bấm vào lần chạy để xem dòng cuối:

| Thông báo | Cách sửa |
|---|---|
| `Chưa có nguồn dữ liệu` / `Chưa khai nơi nhận` | Chưa tạo secret hoặc gõ sai tên |
| `sign match fail` | Secret sai, hoặc bot không bật Signature verification nhưng vẫn khai `LARK_WEBHOOK_SECRET` |
| `HTTP Error 400/404` khi đọc sheet | Sheet chưa "Xuất bản lên web" đúng tab |
| `không có chỉ số nào khớp mã` | Cột A sai tên mã (phải đúng như file mẫu, phân biệt hoa thường) |

## Bước 5 — Tự lấy số liệu quảng cáo TikTok + Meta

Phần **📣 Quảng cáo khách hàng** trên thẻ gồm:

- Tổng chi tiêu (tách TikTok / Meta), số TK đang chạy, CTR, CPC, tin nhắn, lead, đơn mua — so với kỳ trước.
- Top 10 tài khoản chi tiêu nhiều nhất, kèm số kết quả và chi phí/kết quả.
- Cảnh báo cho account manager, xếp theo mức chi tiêu của khách:
  - Khách **ngừng chi tiêu** (kỳ trước chi ≥ 500k, kỳ này 0đ).
  - Khách **giảm chi tiêu ≥ 50%**.
  - **Chi phí/kết quả tăng ≥ 50%**.

Kỳ so sánh: báo cáo ngày = hôm qua vs hôm kia; tuần = thứ Hai–CN tuần trước vs tuần trước nữa; tháng = tháng trước vs tháng trước nữa.

Quy ước:
- Chỉ cộng tài khoản tiền **VND**. TK USD/PHP/HKD không cộng vào tổng (ghi chú dưới thẻ).
- Meta: "kết quả" của 1 tài khoản = loại lớn nhất trong tin nhắn / lead / đơn mua (không cộng dồn vì cùng 1 khách thường được đếm ở cả tin nhắn lẫn lead).
- TikTok: "kết quả" = cột Conversion theo mục tiêu tối ưu của chiến dịch.
- Chiến dịch **GMV Max** (TikTok Shop) không nằm trong báo cáo này — TikTok tách riêng loại báo cáo đó.

### 5a. Token TikTok (cần làm 1 lần, có thể mất vài ngày chờ duyệt)

1. Vào **business-api.tiktok.com/portal** → đăng nhập bằng tài khoản TikTok for Business đang quản lý các TK quảng cáo → **Become a Developer**.
2. **My Apps → Create** app. Phần quyền (Scope) tick **Ad Account Management** và **Reporting**. Gửi duyệt. TikTok duyệt app thủ công; thời gian em không chắc chắn, thường vài ngày làm việc.
3. Sau khi duyệt: mở **Advertiser authorization URL** của app → chọn tất cả TK quảng cáo → **Confirm**. Trình duyệt chuyển sang một link có `auth_code=...` → copy đoạn mã đó.
4. Nhờ 1 bạn kỹ thuật chạy (2 phút, máy có Python):
   ```
   python3 lark-report/lay_token_tiktok.py APP_ID APP_SECRET AUTH_CODE
   ```
   Kết quả in ra **access token** — dán vào secret `TIKTOK_ACCESS_TOKEN`.
5. Thêm secret `TIKTOK_APP_ID` và `TIKTOK_APP_SECRET` (lấy trong trang app) để bot tự nhận diện mọi TK đã uỷ quyền, kể cả TK thêm sau này (thêm TK mới thì làm lại bước 3–4).

### 5b. Token Meta (khoảng 15 phút, không phải chờ duyệt)

1. Vào **developers.facebook.com → My Apps → Create App** → loại **Business** → gắn với Business Manager của TechPro.
2. Vào **business.facebook.com → Cài đặt doanh nghiệp → Người dùng → Người dùng hệ thống** → **Thêm** (vai trò Admin).
3. Chọn người dùng hệ thống vừa tạo → **Chỉ định tài sản** → chọn các tài khoản quảng cáo → quyền **Xem hiệu quả** là đủ.
4. **Tạo mã mới** → chọn app ở bước 1 → thời hạn **Không bao giờ** → tick quyền `ads_read` → copy mã → dán vào secret `META_ACCESS_TOKEN`.

Token người dùng hệ thống không hết hạn khi nhân viên nghỉ việc hay đổi mật khẩu — đừng dùng token cá nhân.

### 5c. Tuỳ chọn (tab Variables)

| Tên | Ý nghĩa | Mặc định |
|---|---|---|
| `TIKTOK_ADVERTISER_IDS` | Chỉ lấy các TK này (ID cách nhau dấu phẩy). Bắt buộc nếu không khai `TIKTOK_APP_ID/SECRET` | mọi TK đã uỷ quyền |
| `META_AD_ACCOUNT_IDS` | Chỉ lấy các TK này | mọi TK token thấy được |
| `ADS_MIN_SPEND` | Chỉ cảnh báo khách có chi tiêu kỳ trước từ mức này (đ) | 500000 |
| `ADS_DROP_PCT` | Cảnh báo khi chi tiêu giảm từ X% | 50 |
| `ADS_CPR_RISE` | Cảnh báo khi chi phí/kết quả tăng từ X% | 50 |
| `META_API_VERSION` | Phiên bản Graph API, chỉ đổi khi Meta báo phiên bản cũ hết hạn | v23.0 |

Khi một nền tảng lỗi (token hết hạn, mất kết nối), bot **vẫn gửi** phần còn lại và ghi rõ lỗi dưới thẻ.

| Thông báo lỗi trên thẻ | Cách sửa |
|---|---|
| `TikTok API lỗi 40105` / `40100` | Token TikTok sai hoặc bị thu hồi → làm lại 5a bước 3–4 |
| `Meta API lỗi: Error validating access token` | Token Meta hết hạn/bị xoá → tạo lại theo 5b bước 4 |
| `Cần TIKTOK_ADVERTISER_IDS, hoặc TIKTOK_APP_ID + TIKTOK_APP_SECRET` | Thiếu 1 trong 2 cách khai danh sách TK |

## Bước 6 — Gửi báo cáo về Telegram (khoảng 10 phút)

Telegram nhận **đúng nội dung** như thẻ Lark: mục ⚠️ Cần xử lý, các nhóm chỉ số, phần 📣 Quảng cáo khách hàng (TikTok + Meta), top tài khoản và nút "Mở dashboard". Có cảnh báo thì tiêu đề có 🚨. Không dùng Lark thì bỏ qua Bước 2, chỉ cần bước này.

### 6a. Tạo bot bằng BotFather

1. Mở Telegram, ô tìm kiếm gõ **@BotFather** → chọn tài khoản có **dấu tích xanh** (cẩn thận tài khoản giả mạo tên gần giống).
2. Bấm **Start**, rồi gõ `/newbot`.
3. BotFather hỏi tên hiển thị → gõ ví dụ `TechPro Report`.
4. BotFather hỏi username → gõ tên **kết thúc bằng `bot`**, không dấu, không cách, ví dụ `techpro_report_bot`. Nếu báo đã có người dùng thì thêm số: `techpro_report2_bot`.
5. BotFather trả về một dòng dạng `8123456789:AAH...` — đây là **token**. Copy lại, coi như mật khẩu: ai có token này đều gửi được tin dưới tên bot.

Lỡ để lộ token: vào @BotFather gõ `/revoke` → chọn bot → nhận token mới → cập nhật lại secret ở 6c.

### 6b. Đưa bot vào nhóm và lấy Chat ID

1. Tạo (hoặc mở) nhóm Telegram muốn nhận báo cáo, ví dụ "TechPro – Ban điều hành". Nên để nhóm **riêng tư** vì báo cáo có số liệu khách hàng.
2. Vào thông tin nhóm → **Thêm thành viên** → tìm username bot (ví dụ `@techpro_report_bot`) → Thêm.
3. Trong nhóm, gõ một tin: `/start@techpro_report_bot` (thay bằng username bot của chị) rồi gửi.
4. Trên trình duyệt máy tính, mở link sau, thay `TOKEN` bằng token ở 6a (giữ nguyên chữ `bot` phía trước):
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```
5. Trang hiện ra một đoạn chữ. Tìm (Ctrl + F) cụm `"chat":{"id":` — con số ngay sau là **Chat ID**, thường dạng `-1001234567890`. Copy **cả dấu trừ**.
   - Nếu trang chỉ hiện `{"ok":true,"result":[]}`: gửi lại tin ở bước 3 rồi tải lại trang (Telegram chỉ giữ tin trong 24 giờ).
   - Có nhiều đoạn `"chat"`: chọn đoạn có `"title":"<tên nhóm của chị>"`. Đoạn có `"type":"private"` là chat riêng với bot, không phải nhóm.

Muốn nhận báo cáo ở chat riêng thay vì nhóm: nhắn `/start` cho bot, mở link ở bước 4, lấy `"id"` trong đoạn `"type":"private"` (số dương).

### 6c. Khai báo trên GitHub

Repo `techpro-dashboard` → **Settings → Secrets and variables → Actions** → tab **Secrets** → **New repository secret**:

| Tên | Giá trị |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token ở 6a |
| `TELEGRAM_CHAT_ID` | Chat ID ở 6b. Gửi nhiều nhóm thì ghi cách nhau dấu phẩy: `-1001111111111,-1002222222222` |

Tuỳ chọn, tab **Variables**: nhóm có bật **Topics** (chủ đề) và muốn báo cáo vào đúng 1 chủ đề → tạo `TELEGRAM_THREAD_ID` = số cuối trong link của chủ đề đó (bấm chuột phải vào tin trong chủ đề → Copy Message Link, link dạng `t.me/c/123/45/67` thì số chủ đề là `45`).

Gửi thử như Bước 4. Tin nhắn dài quá giới hạn của Telegram (4.096 ký tự) sẽ tự tách thành 2–3 tin liên tiếp.

Khi Lark và Telegram cùng khai: một bên lỗi thì bên kia **vẫn nhận** báo cáo; lần chạy vẫn báo ✗ đỏ để chị biết bên nào lỗi.

| Thông báo lỗi | Cách sửa |
|---|---|
| `Telegram: ... Unauthorized` | Token sai, thiếu ký tự, hoặc đã `/revoke` → dán lại token mới |
| `Telegram: ... chat not found` | Chat ID sai/thiếu dấu trừ, hoặc bot chưa được thêm vào nhóm |
| `Telegram: ... bot was kicked` / `not a member` | Bot bị xoá khỏi nhóm → thêm lại |
| `Telegram: ... group chat was upgraded to a supergroup` | Nhóm đổi loại nên đổi Chat ID → làm lại 6b bước 3–5, lấy ID mới (bắt đầu bằng `-100`) |
| `Telegram: ... message thread not found` | `TELEGRAM_THREAD_ID` sai, hoặc nhóm đã tắt Topics → sửa hoặc xoá biến |
| `Thiếu TELEGRAM_BOT_TOKEN` | Đã khai Chat ID nhưng chưa khai token |

Bạn kỹ thuật muốn xem trước nội dung tin Telegram mà không gửi:
```
python3 lark-report/send_report.py --csv-file lark-report/sample_kpi.csv --ads-json lark-report/sample_ads.json --telegram-preview
```

## Đổi giờ gửi

Sửa các dòng `cron` trong `.github/workflows/lark-report.yml`. Giờ tính theo UTC = giờ VN trừ 7. Ví dụ 17:00 VN → `0 10 * * *`.
