# news.py
import time
import concurrent.futures
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote

from linebot.v3.messaging import (
    ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, PushMessageRequest,
    PostbackAction, FlexMessage, FlexContainer
)

import db    # <= 新增

def fetch_google_news(topic, count=3):
    rss_url = (
        "https://news.google.com/rss/"
        f"search?q={quote(topic)}"
        "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    try:
        r = requests.get(rss_url, timeout=5)
        r.raise_for_status()
    except Exception:
        return []
    root = ET.fromstring(r.content)
    items = root.findall('.//item')[:count]
    news_list = []
    for item in items:
        title = item.findtext('title', default='').strip()
        link  = item.findtext('link',  default='').strip()
        news_list.append({"title": title, "url": link})
    return news_list

def handle_news(event, line_bot_api):
    user_id = event.source.user_id if hasattr(event.source, 'user_id') else "unknown"
    # 從資料庫讀訂閱清單
    topics = db.list_subscriptions(user_id)

    # 無訂閱時
    if not topics:
        qr = QuickReply(items=[
            QuickReplyItem(
                action=PostbackAction(label="＋ 新增訂閱", data="action=start_add_subscription")
            )
        ])
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="目前沒有訂閱主題，請先新增訂閱", quick_reply=qr)]
            )
        )

    # 顯示待命訊息
    line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text="正在搜尋最新新聞，請稍候…")]
        )
    )

    # 並行抓每個主題的新聞
    all_news = {}
    with concurrent.futures.ThreadPoolExecutor() as exe:
        futures = {exe.submit(fetch_google_news, t, 3): t for t in topics}
        for fut in concurrent.futures.as_completed(futures):
            all_news[futures[fut]] = fut.result()

    bubbles = []
    for topic, items in all_news.items():
        for n in items:
            # （選擇性）把這筆新聞寫進 news_history
            # with db.get_conn() as conn, conn.cursor() as cur:
            #     cur.execute(
            #       "INSERT INTO news_history(user_id,topic,title,url) VALUES(%s,%s,%s,%s)",
            #       (user_id, topic, n["title"], n["url"])
            #     )

            bubbles.append({
                "type": "bubble",
                "size": "micro",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": topic, "weight": "bold", "size": "md", "margin": "md"},
                        {"type": "text", "text": n["title"], "size": "sm", "weight": "bold", "wrap": True, "margin": "sm"}
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "action": {"type": "uri", "label": "開啟新聞", "uri": n["url"]},
                            "style": "primary", "height": "sm", "gravity": "center", "margin": "md"
                        }
                    ],
                    "spacing": "sm", "paddingAll": "10px"
                }
            })

    if bubbles:
        flex = FlexMessage(
            alt_text="即時新聞",
            contents=FlexContainer.from_dict({"type": "carousel", "contents": bubbles})
        )
        return line_bot_api.push_message_with_http_info(
            PushMessageRequest(to=user_id, messages=[flex])
        )
