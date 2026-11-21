"""Dựng phần "Quảng cáo khách hàng" trên thẻ Lark từ số liệu ads_sources.

Góc nhìn agency: chi tiêu của khách tăng là tốt (doanh thu dịch vụ tăng),
khách giảm mạnh hoặc ngừng chi tiêu là rủi ro cần account manager gọi ngay.
"""

import os
from collections import defaultdict

from send_report import fmt_money, vn


def _env_float(name, default):
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def _pct_change(cur, prev):
    if not prev:
        return ""
    diff = (cur - prev) / prev * 100
    if abs(diff) < 0.05:
        return " · ⚪ 0%"
    return f" · {'🟢' if diff > 0 else '🔴'} {vn(f'{diff:+.0f}')}%"


def _count(v):
    return f"{v:,.0f}".replace(",", ".")


def _key(a):
    return (a["platform"], a["id"])


def _totals(accounts):
    t = defaultdict(float)
    for a in accounts:
        for k in ("spend", "impressions", "clicks", "messages", "leads", "purchases", "conversions"):
            t[k] += a[k]
        t[f"spend_{a['platform']}"] += a["spend"]
        if a["platform"] == "TikTok":
            t["tiktok_conversions"] += a["conversions"]
        if a["spend"] > 0:
            t["active"] += 1
    return t


def collect_ads_alerts(current, previous):
    """Khách ngừng/giảm chi tiêu và chi phí/kết quả tăng vọt, xếp theo mức chi kỳ trước."""
    min_spend = _env_float("ADS_MIN_SPEND", 500_000)
    drop_pct = _env_float("ADS_DROP_PCT", 50)
    cpr_rise = _env_float("ADS_CPR_RISE", 50)
    max_items = int(_env_float("ADS_MAX_ALERTS", 8))

    cur = {_key(a): a for a in current}
    found = []
    for p in previous:
        if p["spend"] < min_spend:
            continue
        c = cur.get(_key(p))
        label = f"{p['platform']} · {p['name']}"
        if not c or c["spend"] == 0:
            found.append((p["spend"], f"{label} **ngừng chi tiêu** (kỳ trước {fmt_money(p['spend'])})"))
            continue
        change = (c["spend"] - p["spend"]) / p["spend"] * 100
        if change <= -drop_pct:
            found.append((p["spend"], f"{label} chi tiêu **giảm {abs(change):.0f}%** "
                                      f"({fmt_money(p['spend'])} → {fmt_money(c['spend'])})"))
            continue
        if p["conversions"] and c["conversions"]:
            cpr_prev = p["spend"] / p["conversions"]
            cpr_cur = c["spend"] / c["conversions"]
            rise = (cpr_cur - cpr_prev) / cpr_prev * 100
            if rise >= cpr_rise:
                found.append((p["spend"], f"{label} chi phí/kết quả **tăng {rise:.0f}%** "
                                          f"({fmt_money(cpr_prev)} → {fmt_money(cpr_cur)})"))

    found.sort(key=lambda x: -x[0])
    alerts = [text for _, text in found[:max_items]]
    if len(found) > max_items:
        alerts.append(f"… và {len(found) - max_items} tài khoản khác")
    return alerts


def build_ads_elements(ads):
    """Trả về (elements, alerts). Chỉ cộng tài khoản VND; ngoại tệ ghi chú riêng."""
    if not ads["current"] and not ads["previous"] and ads["errors"]:
        # Lỗi hết thì báo lỗi, không hiện "0đ" gây hiểu nhầm là khách ngừng chạy
        return [{"tag": "div", "text": {"tag": "lark_md",
                 "content": "**📣 Quảng cáo khách hàng**\n⚠️ Không lấy được số liệu: "
                            + "; ".join(ads["errors"])}}], []
    current = [a for a in ads["current"] if a["currency"] == "VND"]
    previous = [a for a in ads["previous"] if a["currency"] == "VND"]
    foreign = sorted({a["currency"] for a in ads["current"] if a["currency"] != "VND" and a["spend"] > 0})

    cur, prev = _totals(current), _totals(previous)
    alerts = collect_ads_alerts(current, previous)

    def field(label, value, change=""):
        return {"is_short": True, "text": {"tag": "lark_md", "content": f"**{label}**\n{value}{change}"}}

    fields = [
        field("Tổng chi tiêu", fmt_money(cur["spend"]), _pct_change(cur["spend"], prev["spend"])),
        field("TK đang chạy", _count(cur["active"]), _pct_change(cur["active"], prev["active"])),
    ]
    for platform in ("TikTok", "Meta"):
        if cur[f"spend_{platform}"] or prev[f"spend_{platform}"]:
            fields.append(field(f"Chi tiêu {platform}", fmt_money(cur[f"spend_{platform}"]),
                                _pct_change(cur[f"spend_{platform}"], prev[f"spend_{platform}"])))
    if cur["impressions"]:
        fields.append(field("CTR", vn(f"{cur['clicks'] / cur['impressions'] * 100:.2f}") + "%"))
    if cur["clicks"]:
        fields.append(field("CPC", fmt_money(cur["spend"] / cur["clicks"])))
    for key, label in (("messages", "Tin nhắn (Meta)"), ("leads", "Lead (Meta)"),
                       ("purchases", "Đơn mua"), ("tiktok_conversions", "Chuyển đổi (TikTok)")):
        if cur[key]:
            fields.append(field(label, _count(cur[key]), _pct_change(cur[key], prev[key])))

    prev_by_key = {_key(a): a for a in previous}
    top = sorted((a for a in current if a["spend"] > 0), key=lambda a: -a["spend"])
    top_n = int(_env_float("ADS_TOP_N", 10))
    lines = []
    for i, a in enumerate(top[:top_n], 1):
        p = prev_by_key.get(_key(a))
        line = f"{i}. {a['platform']} · {a['name']} — **{fmt_money(a['spend'])}**"
        line += _pct_change(a["spend"], p["spend"]) if p else " · 🆕"
        if a["conversions"]:
            line += f" · {_count(a['conversions'])} KQ · {fmt_money(a['spend'] / a['conversions'])}/KQ"
        lines.append(line)

    start, end = ads["range"]
    period_text = f"{start:%d/%m}" if start == end else f"{start:%d/%m}–{end:%d/%m}"
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
                                "content": f"**📣 Quảng cáo khách hàng ({period_text}, so với kỳ trước)**"}},
        {"tag": "div", "fields": fields},
    ]
    if lines:
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                                                "content": f"**Top {len(lines)} tài khoản chi tiêu**\n" + "\n".join(lines)}})

    notes = []
    if foreign:
        notes.append(f"Chưa cộng TK ngoại tệ: {', '.join(foreign)}")
    notes += [f"Lỗi {e}" for e in ads["errors"]]
    if notes:
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": " · ".join(notes)}]})
    return elements, alerts
