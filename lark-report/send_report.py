#!/usr/bin/env python3
"""Gửi báo cáo KPI tự động vào nhóm Lark.

Đọc tab KPI_Tháng (cùng nguồn với dashboard Vanhanh.html), dựng thẻ báo cáo
(interactive card) và gửi qua Custom Bot webhook của nhóm Lark.

Cấu trúc tab KPI_Tháng:
    Cột A: mã chỉ số (GMV_thuc_te, ROAS, ...)
    Cột B: giá trị hiện tại
    Cột C: mục tiêu (tuỳ chọn)
    Cột D: giá trị kỳ trước (tuỳ chọn)

Biến môi trường:
    KPI_CSV_URL          link CSV publish của tab KPI_Tháng (bắt buộc)
    LARK_WEBHOOK_URL     webhook của Custom Bot (bắt buộc, trừ khi --dry-run)
    LARK_WEBHOOK_SECRET  secret nếu bot bật "Signature verification" (tuỳ chọn)
    DASHBOARD_URL        link dashboard để gắn nút "Mở dashboard" (tuỳ chọn)
    ROAS_MIN             ngưỡng cảnh báo ROAS (mặc định 4)
    RETURN_MAX           ngưỡng cảnh báo tỷ lệ hoàn hàng, % (mặc định 3)
    TARGET_MIN           ngưỡng cảnh báo % đạt mục tiêu (mặc định 80)

Chỉ dùng thư viện chuẩn của Python, không cần cài thêm gì.
"""

import argparse
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

# (mã chỉ số, tên hiển thị, kiểu định dạng, chiều tốt: +1 tăng là tốt, -1 giảm là tốt)
SECTIONS = [
    ("Tổng quan", [
        ("GMV_thuc_te", "GMV thực tế", "money", 1),
        ("Doanh_thu_thuan", "Doanh thu thuần", "money", 1),
        ("Tong_don_hang", "Tổng đơn hàng", "count", 1),
        ("Chi_phi_Ads", "Chi phí Ads", "money", -1),
        ("ROAS", "ROAS", "roas", 1),
        ("Ty_le_hoan_hang", "Tỷ lệ hoàn hàng", "pct", -1),
    ]),
    ("TikTok Shop", [
        ("TT_GMV", "GMV", "money", 1),
        ("TT_Don_thanh_cong", "Đơn thành công", "count", 1),
        ("TT_AOV", "AOV", "money", 1),
        ("TT_Hoan_hang", "Hoàn hàng", "pct", -1),
    ]),
    ("Shopee", [
        ("SP_GMV", "GMV", "money", 1),
        ("SP_Don_thanh_cong", "Đơn thành công", "count", 1),
        ("SP_AOV", "AOV", "money", 1),
        ("SP_Rating", "Rating", "rating", 1),
    ]),
    ("Quảng cáo", [
        ("Ads_ROAS", "ROAS", "roas", 1),
        ("Ads_Don_tu_Ads", "Đơn từ Ads", "count", 1),
        ("Ads_CPO", "CPO", "money", -1),
        ("Ads_CTR", "CTR", "pct", 1),
        ("Ads_CPC", "CPC", "money", -1),
    ]),
]

PERIOD_TITLES = {
    "daily": "Báo cáo ngày",
    "weekly": "Báo cáo tuần",
    "monthly": "Báo cáo tháng",
}


def build_csv_url(url, sheet_name="KPI_Tháng"):
    """Giống buildCsvUrl() trong dashboard: chấp nhận link publish hoặc link sheet thường."""
    if "output=csv" in url or "/pub?" in url:
        return url
    if "gviz/tq" in url:
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        query.update({"tqx": "out:csv", "sheet": sheet_name})
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError("Không tìm được Sheet ID trong KPI_CSV_URL")
    return (f"https://docs.google.com/spreadsheets/d/{m.group(1)}/gviz/tq"
            f"?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}")


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "techpro-lark-report"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8-sig")


def parse_number(raw):
    """Đọc số từ ô sheet: '1.240.000', '1,240,000', '6.3', '2,4%', '156000000'."""
    if raw is None:
        return None
    s = re.sub(r"[^0-9,.\-]", "", str(raw))
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        # Dấu xuất hiện sau cùng là dấu thập phân
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") > 1 or s.count(".") > 1:
        s = s.replace(",", "").replace(".", "")
    elif "," in s:
        # Một dấu phẩy: đúng 3 chữ số phía sau thì là phân cách nghìn
        s = s.replace(",", "") if re.search(r",\d{3}$", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_kpi_csv(text):
    """Trả về {mã: {"value", "target", "prev"}}; bỏ qua dòng tiêu đề/dòng trống."""
    data = {}
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].strip():
            continue
        cells = [c.strip() for c in row] + ["", "", ""]
        data[cells[0]] = {
            "value": parse_number(cells[1]),
            "target": parse_number(cells[2]),
            "prev": parse_number(cells[3]),
        }
    return data


def vn(num_text):
    """Dấu thập phân kiểu Việt Nam: 6.3 -> 6,3."""
    return num_text.replace(".", ",")


def fmt_money(v):
    a = abs(v)
    if a >= 1e9:
        return vn(f"{v / 1e9:.2f}") + " tỷ"
    if a >= 1e6:
        return f"{v / 1e6:.0f} tr"
    if a >= 1e4:
        return f"{v / 1e3:.0f}k"
    return f"{v:,.0f}đ".replace(",", ".")


def fmt_value(v, kind):
    if v is None:
        return "—"
    if kind == "money":
        return fmt_money(v)
    if kind == "count":
        return f"{v:,.0f}".replace(",", ".")
    if kind == "roas":
        return vn(f"{v:.1f}") + "x"
    if kind == "pct":
        return vn(f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}") + "%"
    if kind == "rating":
        return vn(f"{v:.1f}") + "★"
    return str(v)


def fmt_change(item, kind, good_dir):
    """So với kỳ trước: 🟢 nếu đi đúng hướng, 🔴 nếu ngược hướng."""
    v, prev = item["value"], item["prev"]
    if v is None or prev is None or prev == 0:
        return ""
    if kind in ("pct", "roas", "rating"):
        diff = v - prev
        unit = {"pct": "pp", "roas": "x", "rating": ""}[kind]
        text = vn(f"{diff:+.1f}") + unit
    else:
        diff = v - prev
        text = vn(f"{diff / prev * 100:+.1f}") + "%"
    if diff == 0:
        return " · ⚪ 0"
    icon = "🟢" if (diff > 0) == (good_dir > 0) else "🔴"
    return f" · {icon} {text}"


def target_ratio(item, good_dir):
    """% đạt mục tiêu; với chỉ số càng thấp càng tốt (chi phí, CPO) là % ngân sách đã dùng."""
    v, target = item["value"], item["target"]
    if v is None or not target:
        return None
    return v / target * 100


def fmt_target(item, good_dir):
    ratio = target_ratio(item, good_dir)
    if ratio is None:
        return ""
    if good_dir > 0:
        return f"\nĐạt {ratio:.0f}% mục tiêu"
    if ratio > 100:
        return f"\nVượt trần {ratio - 100:.0f}%"
    return f"\nTrong trần ({ratio:.0f}%)"


def collect_alerts(data):
    roas_min = float(os.environ.get("ROAS_MIN") or 4)
    return_max = float(os.environ.get("RETURN_MAX") or 3)
    target_min = float(os.environ.get("TARGET_MIN") or 80)
    alerts, flagged = [], set()

    for key, label in (("ROAS", "ROAS tổng"), ("Ads_ROAS", "ROAS Ads")):
        v = data.get(key, {}).get("value")
        if v is not None and v < roas_min:
            alerts.append(f"{label} **{fmt_value(v, 'roas')}** dưới ngưỡng {roas_min:g}x")
            flagged.add(key)

    for key, label in (("Ty_le_hoan_hang", "Hoàn hàng tổng"), ("TT_Hoan_hang", "Hoàn hàng TikTok")):
        v = data.get(key, {}).get("value")
        if v is not None and v > return_max:
            alerts.append(f"{label} **{fmt_value(v, 'pct')}** vượt ngưỡng {return_max:g}%")
            flagged.add(key)

    for section, metrics in SECTIONS:
        for key, label, _, good_dir in metrics:
            item = data.get(key)
            if key in flagged or not item:
                continue
            ratio = target_ratio(item, good_dir)
            if ratio is None:
                continue
            if good_dir > 0 and ratio < target_min:
                alerts.append(f"{section} · {label} mới đạt **{ratio:.0f}%** mục tiêu")
            elif good_dir < 0 and ratio > 100:
                alerts.append(f"{section} · {label} vượt trần **{ratio - 100:.0f}%**")
    return alerts


def build_card(data, period, dashboard_url=None, now=None):
    now = now or datetime.now(VN_TZ)
    alerts = collect_alerts(data)
    elements = []

    if alerts:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md",
                     "content": "**⚠️ Cần xử lý**\n" + "\n".join(f"• {a}" for a in alerts)},
        })
        elements.append({"tag": "hr"})

    shown = 0
    for title, metrics in SECTIONS:
        fields = []
        for key, label, kind, good_dir in metrics:
            item = data.get(key)
            if not item or item["value"] is None:
                continue
            content = (f"**{label}**\n{fmt_value(item['value'], kind)}"
                       f"{fmt_change(item, kind, good_dir)}{fmt_target(item, good_dir)}")
            fields.append({"is_short": True, "text": {"tag": "lark_md", "content": content}})
        if not fields:
            continue
        shown += len(fields)
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**📊 {title}**"}})
        elements.append({"tag": "div", "fields": fields})

    if shown == 0:
        raise ValueError("Tab KPI_Tháng không có chỉ số nào khớp mã — kiểm tra cột A")

    if dashboard_url:
        elements.append({"tag": "action", "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "Mở dashboard"},
            "type": "primary",
            "url": dashboard_url,
        }]})

    elements.append({"tag": "note", "elements": [{
        "tag": "plain_text",
        "content": f"Nguồn: Google Sheet KPI_Tháng · Gửi lúc {now:%H:%M %d/%m/%Y}",
    }]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red" if alerts else "blue",
            "title": {"tag": "plain_text",
                      "content": f"TechPro · {PERIOD_TITLES[period]} {now:%d/%m/%Y}"},
        },
        "elements": elements,
    }


def sign(secret, timestamp):
    """Chữ ký theo tài liệu Lark Custom Bot: HMAC-SHA256 với key = '{timestamp}\\n{secret}'."""
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_to_lark(webhook_url, card, secret=None):
    payload = {"msg_type": "interactive", "card": card}
    if secret:
        ts = str(int(time.time()))
        payload.update({"timestamp": ts, "sign": sign(secret, ts)})
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.loads(res.read().decode("utf-8") or "{}")
    code = body.get("code", body.get("StatusCode", 0))
    if code != 0:
        raise RuntimeError(f"Lark từ chối tin nhắn: {body}")
    return body


def main():
    parser = argparse.ArgumentParser(description="Gửi báo cáo KPI vào nhóm Lark")
    parser.add_argument("--period", choices=PERIOD_TITLES, default="daily")
    parser.add_argument("--csv-file", help="Đọc CSV từ file thay vì từ Google Sheet (để thử)")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in thẻ ra màn hình, không gửi")
    args = parser.parse_args()

    if args.csv_file:
        with open(args.csv_file, encoding="utf-8-sig") as f:
            text = f.read()
    else:
        csv_url = os.environ.get("KPI_CSV_URL")
        if not csv_url:
            sys.exit("Thiếu KPI_CSV_URL")
        text = fetch_text(build_csv_url(csv_url))

    card = build_card(parse_kpi_csv(text), args.period, os.environ.get("DASHBOARD_URL"))

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    webhook = os.environ.get("LARK_WEBHOOK_URL")
    if not webhook:
        sys.exit("Thiếu LARK_WEBHOOK_URL")
    send_to_lark(webhook, card, os.environ.get("LARK_WEBHOOK_SECRET"))
    print("Đã gửi báo cáo vào Lark.")


if __name__ == "__main__":
    main()
