"""Gửi cùng nội dung thẻ báo cáo Lark sang Telegram qua Bot API.

Không dựng lại số liệu: nhận thẻ do send_report.build_card() tạo ra rồi
chuyển sang tin nhắn HTML của Telegram, để Lark và Telegram luôn khớp nhau.

Biến môi trường:
    TELEGRAM_BOT_TOKEN   token bot lấy từ @BotFather (bắt buộc nếu gửi Telegram)
    TELEGRAM_CHAT_ID     ID nhóm/người nhận; nhiều nơi thì cách nhau dấu phẩy
    TELEGRAM_THREAD_ID   ID chủ đề (topic) nếu nhóm bật Topics (tuỳ chọn)
"""

import html
import json
import re
import urllib.error
import urllib.request

API_BASE = "https://api.telegram.org"
MAX_LEN = 4096  # giới hạn độ dài 1 tin nhắn của Telegram


def md_to_html(text):
    """lark_md chỉ dùng **đậm** → <b>đậm</b>; các ký tự <, >, & được escape."""
    escaped = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.S)


def _field_line(content):
    """'**GMV**\\n1,24 tỷ · 🟢 +18,7%\\nĐạt 83% mục tiêu' → '• <b>GMV</b>: 1,24 tỷ · 🟢 +18,7% · Đạt 83% mục tiêu'."""
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    if not lines:
        return ""
    head = md_to_html(lines[0])
    rest = " · ".join(md_to_html(l) for l in lines[1:])
    return f"• {head}: {rest}" if rest else f"• {head}"


def card_to_blocks(card):
    """Trả về (danh sách khối HTML, danh sách nút (chữ, link))."""
    title = html.escape(card["header"]["title"]["content"], quote=False)
    icon = "🚨" if card["header"].get("template") == "red" else "📈"
    blocks = [f"{icon} <b>{title}</b>"]
    buttons = []

    for el in card["elements"]:
        tag = el.get("tag")
        if tag == "hr":
            blocks.append("──────────")
        elif tag == "div" and "fields" in el:
            lines = [_field_line(f["text"]["content"]) for f in el["fields"]]
            blocks.append("\n".join(l for l in lines if l))
        elif tag == "div" and "text" in el:
            blocks.append(md_to_html(el["text"]["content"]))
        elif tag == "note":
            text = " · ".join(e.get("content", "") for e in el.get("elements", []))
            blocks.append(f"<i>{html.escape(text, quote=False)}</i>")
        elif tag == "action":
            for a in el.get("actions", []):
                if a.get("url"):
                    buttons.append((a["text"]["content"], a["url"]))

    # Tiêu đề nhóm ("📊 Tổng quan") đứng sát danh sách chỉ số ngay sau nó
    merged = []
    for b in blocks:
        if merged and re.fullmatch(r"<b>[^<]*</b>", merged[-1]) and not b.startswith("─"):
            merged[-1] += "\n" + b
        else:
            merged.append(b)
    return merged, buttons


def split_messages(blocks, limit=MAX_LEN):
    """Ghép các khối thành tin nhắn ≤ limit ký tự, chỉ cắt giữa các khối/dòng để không vỡ thẻ HTML."""
    pieces = []
    for b in blocks:
        if len(b) <= limit:
            pieces.append(b)
            continue
        chunk = ""
        for line in b.split("\n"):
            while len(line) > limit:  # một dòng quá dài (hiếm): cắt cứng
                pieces.append(line[:limit])
                line = line[limit:]
            if chunk and len(chunk) + 1 + len(line) > limit:
                pieces.append(chunk)
                chunk = line
            else:
                chunk = f"{chunk}\n{line}" if chunk else line
        if chunk:
            pieces.append(chunk)

    messages, cur = [], ""
    for p in pieces:
        if cur and len(cur) + 2 + len(p) > limit:
            messages.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        messages.append(cur)
    return messages


def card_to_messages(card):
    blocks, buttons = card_to_blocks(card)
    return split_messages(blocks), buttons


def parse_chat_ids(raw):
    return [c.strip() for c in (raw or "").split(",") if c.strip()]


def _post(token, method, payload):
    req = urllib.request.Request(
        f"{API_BASE}/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = json.loads(res.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        # Telegram trả 400/401/403 kèm lý do trong body — đọc ra để báo lỗi dễ hiểu
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            body = {"ok": False, "description": f"HTTP {e.code}"}
    if not body.get("ok"):
        raise RuntimeError(f"Telegram từ chối tin nhắn: {body.get('description', body)}")
    return body


def send_to_telegram(token, chat_ids, card, thread_id=None):
    """Gửi thẻ tới từng chat; nút "Mở dashboard" gắn vào tin cuối. Trả về số tin đã gửi."""
    if not chat_ids:
        raise ValueError("Thiếu TELEGRAM_CHAT_ID")
    messages, buttons = card_to_messages(card)
    errors, sent = [], 0
    for chat_id in chat_ids:
        try:
            for i, text in enumerate(messages):
                payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                           "disable_web_page_preview": True}
                if thread_id:
                    payload["message_thread_id"] = int(thread_id)
                if buttons and i == len(messages) - 1:
                    payload["reply_markup"] = {"inline_keyboard": [
                        [{"text": t, "url": u}] for t, u in buttons]}
                _post(token, "sendMessage", payload)
                sent += 1
        except Exception as e:  # một nhóm lỗi không chặn các nhóm khác
            errors.append(f"chat {chat_id}: {str(e).replace(token, '***')}")
    if errors:
        raise RuntimeError("; ".join(errors))
    return sent
