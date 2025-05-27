# pushs.py

import os
from dotenv import load_dotenv
load_dotenv()
import time
import schedule
from datetime import datetime, timedelta
from urllib.parse import quote
import requests
import xml.etree.ElementTree as ET

from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    TextMessage, QuickReply, QuickReplyItem, PostbackAction,
    PushMessageRequest, ReplyMessageRequest, FlexMessage, FlexContainer,
    DatetimePickerAction
)
import db
from db import get_conn

def get_default_push_time():
    now = datetime.now() + timedelta(minutes=1)
    return now.strftime("%H:%M")

def fetch_google_news(topic, count=3):
    rss_url = (
        "https://news.google.com/rss/"
        f"search?q={quote(topic)}"
        "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    try:
        resp = requests.get(rss_url, timeout=5)
        resp.raise_for_status()
    except:
        return []
    root = ET.fromstring(resp.content)
    items = root.findall('.//item')[:count]
    result = []
    for it in items:
        title = it.findtext('title', '').strip()
        link  = it.findtext('link',  '').strip()
        result.append({"title": title, "url": link})
    return result

def build_push_quickreply(user_id):
    subs = db.list_subscriptions(user_id)
    items = []
    for topic in subs:
        sel = topic in db.list_push_topics(user_id)
        label = f"{topic}主題{'不' if sel else ''}推播"
        choice = "cancel" if sel else "push"
        items.append(
            QuickReplyItem(
                action=PostbackAction(
                    label=label,
                    data=f"action=set_push_choice&topic={topic}&choice={choice}"
                )
            )
        )
    # 若已至少選一個推播，顯示時間選擇器
    if any(t in db.list_push_topics(user_id) for t in subs):
        initial = db.get_push_time(user_id) or get_default_push_time()
        items.append(
            QuickReplyItem(
                action=DatetimePickerAction(
                    label="設定推播時間",
                    data="action=set_push_time",
                    mode="time",
                    initial=initial,
                    min="00:00",
                    max="23:59"
                )
            )
        )
    # 完成按鈕
    items.append(
        QuickReplyItem(
            action=PostbackAction(label="完成推播設定", data="action=confirm_push")
        )
    )
    return QuickReply(items=items)

def build_push_status_text(user_id):
    subs = db.list_subscriptions(user_id)
    push_topics = db.list_push_topics(user_id)
    text = "請選擇要推播的訂閱主題:"
    if push_topics:
        for t in push_topics:
            text += f"\n{t}: 推播"
        pt = db.get_push_time(user_id)
        if pt:
            text += f"\n{pt} 將會傳送 { '、'.join(push_topics) } 的資訊給你"
    return text

def handle_push_message(event, line_bot_api):
    user_id = event.source.user_id
    subs = db.list_subscriptions(user_id)
    if not subs:
        qr = QuickReply(items=[
            QuickReplyItem(
                action=PostbackAction(label="＋ 新增訂閱", data="action=start_add_subscription")
            )
        ])
        msg = TextMessage(text="目前沒有訂閱主題，請先新增訂閱", quick_reply=qr)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    status = build_push_status_text(user_id)
    qr = build_push_quickreply(user_id)
    msg = TextMessage(text=status, quick_reply=qr)
    return line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
    )

def handle_push_postback(event, line_bot_api):
    data = event.postback.data or ""
    user_id = event.source.user_id

    # 切換推播選擇
    if data.startswith("action=set_push_choice"):
        parts = dict(p.split("=",1) for p in data.split("&")[1:])
        topic, choice = parts["topic"], parts["choice"]
        is_selected = (choice == "push")
        db.set_push_choice(user_id, topic, is_selected)
        # 若都取消，清除時間設定
        if not db.list_push_topics(user_id):
            db.set_push_time(user_id, None)
        text = build_push_status_text(user_id)
        qr = build_push_quickreply(user_id)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=text, quick_reply=qr)]
            )
        )

    # 設定推播時間
    if data == "action=set_push_time":
        t = event.postback.params.get("time")
        if t:
            db.set_push_time(user_id, t)
            topics = db.list_push_topics(user_id)
            ts = "、".join(topics) if topics else "無"
            text = f"{t} 將會傳送 {ts} 的資訊給你"
            qr = build_push_quickreply(user_id)
        else:
            text = "設定推播時間失敗"
            qr = None
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=text, quick_reply=qr)]
            )
        )

    # 完成設定
    if data == "action=confirm_push":
        topics = db.list_push_topics(user_id)
        if not topics:
            final = "已完成所有推播設定，但目前沒有任何主題設定為推播。"
        else:
            ts = "、".join(topics)
            ft = db.get_push_time(user_id) or "未設定時間"
            if ft == "未設定時間":
                final = f"設定 {ts} 推播的訂閱主題\n尚未設定推播時間\n已完成所有推播設定"
            else:
                final = f"設定 {ts} 推播的訂閱主題\n{ft} 將會推播 {ts} 的資訊\n已完成所有推播設定"
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=final)])
        )

    # 取消所有推播
    if data == "action=cancel_push":
        subs = db.list_subscriptions(user_id)
        for t in subs:
            db.set_push_choice(user_id, t, False)
        db.set_push_time(user_id, None)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="已取消推播設定")])
        )

def send_scheduled_news():
    now_str = datetime.now().strftime("%H:%M")
    # 查詢所有在此時刻有設定推播時間的 user
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM push_times WHERE push_time = %s", (now_str,))
        users = [r[0] for r in cur.fetchall()]

    for user_id in users:
        topics = db.list_push_topics(user_id)
        all_bubbles = []
        for topic in topics:
            news_list = fetch_google_news(topic, 3)
            for n in news_list:
                bubble = {
                    "type": "bubble", "size": "micro",
                    "body": {
                        "type": "box", "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": topic, "weight": "bold", "size": "md", "margin": "md"},
                            {"type": "text", "text": n["title"], "size": "sm", "weight": "bold", "wrap": True, "margin": "sm"}
                        ]
                    },
                    "footer": {
                        "type": "box", "layout": "vertical",
                        "contents": [
                            {"type": "button",
                             "action": {"type": "uri", "label": "開啟新聞", "uri": n["url"]},
                             "style": "primary", "height": "sm", "gravity": "center", "margin": "md"}
                        ],
                        "spacing": "sm", "paddingAll": "10px"
                    }
                }
                all_bubbles.append(bubble)

        if not all_bubbles:
            continue

        configuration = Configuration(access_token=os.getenv('CHANNEL_ACCESS_TOKEN'))
        with ApiClient(configuration) as client:
            api = MessagingApi(client)
            for i in range(0, len(all_bubbles), 10):
                carousel = {"type": "carousel", "contents": all_bubbles[i:i+10]}
                flex = FlexMessage(alt_text="定時新聞推播", contents=FlexContainer.from_dict(carousel))
                api.push_message(PushMessageRequest(to=user_id, messages=[flex]))

def start_push_scheduler():
    schedule.every(1).minutes.do(send_scheduled_news)
    while True:
        schedule.run_pending()
        time.sleep(1)
