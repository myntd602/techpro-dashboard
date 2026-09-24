# Bot báo cáo KPI tự động trên Lark

Mỗi sáng bot tự đọc tab `KPI_Tháng` trên Google Sheet (cùng nguồn với dashboard) và gửi thẻ báo cáo vào nhóm Lark:

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

Tab **Secrets** → **New repository secret**, tạo 3 mục:

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

**Actions → Báo cáo KPI gửi Lark → Run workflow** → chọn loại báo cáo → **Run**. Khoảng 30 giây sau thẻ xuất hiện trong nhóm Lark.

Nếu lỗi (dấu ✗ đỏ), bấm vào lần chạy để xem dòng cuối:

| Thông báo | Cách sửa |
|---|---|
| `Thiếu KPI_CSV_URL` / `Thiếu LARK_WEBHOOK_URL` | Chưa tạo secret hoặc gõ sai tên |
| `sign match fail` | Secret sai, hoặc bot không bật Signature verification nhưng vẫn khai `LARK_WEBHOOK_SECRET` |
| `HTTP Error 400/404` khi đọc sheet | Sheet chưa "Xuất bản lên web" đúng tab |
| `không có chỉ số nào khớp mã` | Cột A sai tên mã (phải đúng như file mẫu, phân biệt hoa thường) |

## Đổi giờ gửi

Sửa các dòng `cron` trong `.github/workflows/lark-report.yml`. Giờ tính theo UTC = giờ VN trừ 7. Ví dụ 17:00 VN → `0 10 * * *`.
