#!/usr/bin/env python3
"""Đổi auth_code của TikTok lấy access token dài hạn (chạy 1 lần khi cài đặt).

Cách dùng:
    python3 lark-report/lay_token_tiktok.py APP_ID APP_SECRET AUTH_CODE

auth_code nằm trong link TikTok chuyển về sau khi bấm "Confirm" trên trang uỷ quyền
(phần ?auth_code=...), chỉ dùng được 1 lần và hết hạn sau khoảng 1 giờ.
"""

import json
import sys
import urllib.request

if len(sys.argv) != 4:
    sys.exit(__doc__)

app_id, secret, auth_code = sys.argv[1:]
req = urllib.request.Request(
    "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/",
    data=json.dumps({"app_id": app_id, "secret": secret, "auth_code": auth_code}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=30) as res:
    body = json.loads(res.read().decode("utf-8"))

if body.get("code") != 0:
    sys.exit(f"TikTok báo lỗi {body.get('code')}: {body.get('message')}")

data = body["data"]
print("Access token (dán vào secret TIKTOK_ACCESS_TOKEN):")
print(data["access_token"])
print(f"\nToken này xem được {len(data.get('advertiser_ids', []))} tài khoản quảng cáo.")
