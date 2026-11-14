"""Lấy số liệu quảng cáo trực tiếp từ TikTok Ads và Meta Ads API.

Mỗi tài khoản quảng cáo được chuẩn hoá thành một dict:
    {platform, id, name, currency, spend, impressions, clicks,
     messages, leads, purchases, conversions}

Biến môi trường:
    TIKTOK_ACCESS_TOKEN     token TikTok Marketing API (long-term)
    TIKTOK_ADVERTISER_IDS   danh sách advertiser_id, cách nhau dấu phẩy
                            (bỏ trống → tự lấy hết nếu có TIKTOK_APP_ID + TIKTOK_APP_SECRET)
    TIKTOK_APP_ID, TIKTOK_APP_SECRET
    META_ACCESS_TOKEN       token System User có quyền ads_read
    META_AD_ACCOUNT_IDS     danh sách account_id (bỏ trống → mọi TK token thấy được)
    META_API_VERSION        mặc định v23.0
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

TIKTOK_API = "https://business-api.tiktok.com/open_api/v1.3"
TIKTOK_METRICS = ["spend", "impressions", "clicks", "conversion", "complete_payment", "currency"]

# Meta trả về hàng chục loại action; chỉ lấy 3 loại kết quả agency hay báo cáo
META_ACTIONS = {
    "messages": "onsite_conversion.messaging_conversation_started_7d",
    "leads": "lead",
    "purchases": "omni_purchase",
}


def _split_ids(raw):
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "techpro-lark-report", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {e.code} từ {urllib.parse.urlsplit(url).netloc}: {body}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Không kết nối được {urllib.parse.urlsplit(url).netloc}: {e}") from None


def report_range(period, today=None):
    """Khoảng ngày của kỳ báo cáo và kỳ liền trước (cùng độ dài).

    daily   → hôm qua, so với hôm kia
    weekly  → thứ Hai–Chủ nhật tuần trước, so với tuần trước nữa
    monthly → tháng trước, so với tháng trước nữa
    """
    today = today or date.today()
    if period == "weekly":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return (start, end), (start - timedelta(days=7), start - timedelta(days=1))
    if period == "monthly":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        prev_end = start - timedelta(days=1)
        return (start, end), (prev_end.replace(day=1), prev_end)
    day = today - timedelta(days=1)
    return (day, day), (day - timedelta(days=1), day - timedelta(days=1))


# ── TikTok ────────────────────────────────────────────────────────────────────

def _tiktok_call(path, params, token=None):
    query = urllib.parse.urlencode(
        {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in params.items()})
    headers = {"Access-Token": token} if token else {}
    body = _get_json(f"{TIKTOK_API}{path}?{query}", headers)
    if body.get("code") != 0:
        raise RuntimeError(f"TikTok API lỗi {body.get('code')}: {body.get('message')}")
    return body.get("data") or {}


def tiktok_advertisers(token):
    """{advertiser_id: tên}. Cần TIKTOK_APP_ID/SECRET nếu không khai TIKTOK_ADVERTISER_IDS."""
    ids = _split_ids(os.environ.get("TIKTOK_ADVERTISER_IDS"))
    if ids:
        return {i: i for i in ids}
    app_id, secret = os.environ.get("TIKTOK_APP_ID"), os.environ.get("TIKTOK_APP_SECRET")
    if not (app_id and secret):
        raise RuntimeError("Cần TIKTOK_ADVERTISER_IDS, hoặc TIKTOK_APP_ID + TIKTOK_APP_SECRET để tự lấy danh sách TK")
    data = _tiktok_call("/oauth2/advertiser/get/",
                        {"app_id": app_id, "secret": secret, "access_token": token})
    return {a["advertiser_id"]: a.get("advertiser_name") or a["advertiser_id"] for a in data.get("list", [])}


def _tiktok_names(token, ids):
    names = {}
    for i in range(0, len(ids), 100):
        data = _tiktok_call("/advertiser/info/", {"advertiser_ids": ids[i:i + 100], "fields": ["name"]}, token)
        for a in data.get("list", []):
            names[str(a.get("advertiser_id"))] = a.get("name")
    return names


def fetch_tiktok(token, start, end):
    advertisers = tiktok_advertisers(token)
    ids = list(advertisers)
    if any(advertisers[i] == i for i in ids):
        try:
            advertisers.update({k: v for k, v in _tiktok_names(token, ids).items() if v})
        except RuntimeError:
            pass  # thiếu tên thì hiện ID, không chặn báo cáo

    accounts = []
    # Báo cáo nhiều TK một lần, tối đa 5 advertiser_id mỗi lệnh
    for i in range(0, len(ids), 5):
        data = _tiktok_call("/report/integrated/get/", {
            "report_type": "BASIC",
            "data_level": "AUCTION_ADVERTISER",
            "dimensions": ["advertiser_id"],
            "advertiser_ids": ids[i:i + 5],
            "metrics": TIKTOK_METRICS,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "page_size": 1000,
        }, token)
        for row in data.get("list", []):
            m = row.get("metrics", {})
            adv = str(row.get("dimensions", {}).get("advertiser_id"))
            accounts.append({
                "platform": "TikTok",
                "id": adv,
                "name": advertisers.get(adv, adv),
                "currency": m.get("currency") or "VND",
                "spend": _num(m.get("spend")),
                "impressions": _num(m.get("impressions")),
                "clicks": _num(m.get("clicks")),
                "messages": 0.0,
                "leads": 0.0,
                "purchases": _num(m.get("complete_payment")),
                "conversions": _num(m.get("conversion")),
            })
    return accounts


# ── Meta ──────────────────────────────────────────────────────────────────────

def fetch_meta(token, start, end):
    version = os.environ.get("META_API_VERSION") or "v23.0"
    only = {i.removeprefix("act_") for i in _split_ids(os.environ.get("META_AD_ACCOUNT_IDS"))}
    time_range = json.dumps({"since": start.isoformat(), "until": end.isoformat()})
    fields = (f"account_id,name,currency,"
              f"insights.time_range({time_range}){{spend,impressions,clicks,actions}}")
    url = (f"https://graph.facebook.com/{version}/me/adaccounts?"
           + urllib.parse.urlencode({"fields": fields, "limit": 100, "access_token": token}))

    accounts = []
    while url:
        body = _get_json(url)
        if "error" in body:
            raise RuntimeError(f"Meta API lỗi: {body['error'].get('message')}")
        for acc in body.get("data", []):
            if only and acc.get("account_id") not in only:
                continue
            rows = (acc.get("insights") or {}).get("data") or []
            if not rows:
                continue  # không chạy trong kỳ
            ins = rows[0]
            actions = {a["action_type"]: _num(a.get("value")) for a in ins.get("actions") or []}
            stat = {k: actions.get(v, 0.0) for k, v in META_ACTIONS.items()}
            accounts.append({
                "platform": "Meta",
                "id": acc["account_id"],
                "name": acc.get("name") or acc["account_id"],
                "currency": acc.get("currency") or "VND",
                "spend": _num(ins.get("spend")),
                "impressions": _num(ins.get("impressions")),
                "clicks": _num(ins.get("clicks")),
                **stat,
                # Tin nhắn, lead, đơn mua thường trùng người → lấy loại lớn nhất làm "kết quả chính"
                "conversions": max(stat.values()),
            })
        url = (body.get("paging") or {}).get("next")
    return accounts


# ── Tổng hợp ──────────────────────────────────────────────────────────────────

def fetch_all(period, today=None):
    """Trả về {"current": [...], "previous": [...], "range": ..., "errors": [...]}, hoặc None nếu chưa cấu hình."""
    sources = []
    if os.environ.get("TIKTOK_ACCESS_TOKEN"):
        sources.append(("TikTok", fetch_tiktok, os.environ["TIKTOK_ACCESS_TOKEN"]))
    if os.environ.get("META_ACCESS_TOKEN"):
        sources.append(("Meta", fetch_meta, os.environ["META_ACCESS_TOKEN"]))
    if not sources:
        return None

    cur_range, prev_range = report_range(period, today)
    result = {"current": [], "previous": [], "range": cur_range, "errors": []}
    for name, fetch, token in sources:
        try:
            current, previous = fetch(token, *cur_range), fetch(token, *prev_range)
            result["current"] += current
            result["previous"] += previous
        except RuntimeError as e:
            # Một nền tảng lỗi thì vẫn gửi phần còn lại, kèm ghi chú lỗi
            result["errors"].append(f"{name}: {e}")
    return result
