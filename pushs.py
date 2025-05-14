# pushs.py
import time
import schedule
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
from urllib.parse import quote
import requests
import xml.etree.ElementTree as ET

from linebot.v3.messaging import ( Configuration, ApiClient, MessagingApi,
    TextMessage, QuickReply, QuickReplyItem, PostbackAction,
    PushMessageRequest, ReplyMessageRequest, FlexMessage, FlexContainer,DatetimePickerAction
)
from subscribetest import user_subscriptions, ALL_TOPICS

# 使用者設定：哪些訂閱要推播
user_push_selection = {}   # { user_id: { topic: "push"/"cancel", ... } }
# 使用者設定的時間
user_push_time = {}        # { user_id: "HH:MM" }

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
        link  = it.findtext('link', '').strip()
        result.append({"title": title, "url": link})
    return result

def build_push_quickreply(user_id):
    settings = user_push_selection.setdefault(user_id, {})
    subs = user_subscriptions.get(user_id, [])
    items = []
    for topic in subs:
        settings.setdefault(topic, "cancel")
        current = settings[topic]
        label = f"{topic}主題{'不' if current=='push' else ''}推播"
        choice = "cancel" if current=="push" else "push"
        items.append(QuickReplyItem(
            action=PostbackAction(
                label=label,
                data=f"action=set_push_choice&topic={topic}&choice={choice}"
            )
        ))
    if any(v=="push" for v in settings.values()):
        items.append(QuickReplyItem(
            action=DatetimePickerAction(
                label="設定推播時間",
                data="action=set_push_time",
                mode="time",
                initial=get_default_push_time(),
                min="00:00",
                max="23:59"
            )
        ))
    items.append(QuickReplyItem(
        action=PostbackAction(label="完成推播設定", data="action=confirm_push")
    ))
    return QuickReply(items=items)

def build_push_status_text(user_id):
    subs = user_subscriptions.get(user_id, [])
    settings = user_push_selection.get(user_id, {})
    push_topics = [t for t in subs if settings.get(t)=="push"]
    text = "請選擇要推播的訂閱主題:"
    if push_topics:
        for t in push_topics:
            text += "\n" + f"{t}:推播"
        if user_id in user_push_time:
            tt = user_push_time[user_id]
            txt = "、".join(push_topics)
            text += f"\n{tt}將會傳送 {txt} 的資訊給你"
    return text

def handle_push_message(event, line_bot_api):
    user_id = event.source.user_id
    subs = user_subscriptions.get(user_id, [])
    if not subs:
        qr = QuickReply(items=[
            QuickReplyItem(
                action=PostbackAction(label="新增訂閱", data="action=start_add_subscription")
            )
        ])
        msg = TextMessage(text="目前沒有訂閱主題，請先新增訂閱", quick_reply=qr)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    # 初始化／清理設定
    sel = user_push_selection.setdefault(user_id, {t:"cancel" for t in subs})
    for t in list(sel):
        if t not in subs:
            sel.pop(t)

    status = build_push_status_text(user_id)
    qr = build_push_quickreply(user_id)
    msg = TextMessage(text=status, quick_reply=qr)
    return line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
    )

def handle_push_postback(event, line_bot_api):
    data = event.postback.data or ""
    user_id = event.source.user_id

    if data.startswith("action=set_push_choice"):
        parts = dict(part.split("=",1) for part in data.split("&")[1:])
        topic = parts.get("topic")
        choice = parts.get("choice")
        if topic and choice:
            user_push_selection.setdefault(user_id, {})[topic] = choice
            # 若都取消，清除時間
            if not any(v=="push" for v in user_push_selection[user_id].values()):
                user_push_time.pop(user_id, None)
            text = build_push_status_text(user_id)
            qr = build_push_quickreply(user_id)
            msg = TextMessage(text=text, quick_reply=qr)
            return line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
            )

    if data == "action=set_push_time":
        t = event.postback.params.get("time")
        if t:
            user_push_time[user_id] = t
            topics = [tp for tp,v in user_push_selection[user_id].items() if v=="push"]
            ts = "、".join(topics) if topics else "無"
            text = f"{t}將會傳送 {ts} 的資訊給你"
            qr = build_push_quickreply(user_id)
        else:
            text = "設定推播時間失敗"
            qr = None
        msg = TextMessage(text=text, quick_reply=qr)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    if data == "action=confirm_push":
        settings = user_push_selection.get(user_id, {})
        topics = [t for t,v in settings.items() if v=="push"]
        if not topics:
            final = "已完成所有推播設定，但目前沒有任何主題設定為推播。"
        else:
            ts = "、".join(topics)
            ft = user_push_time.get(user_id, "未設定時間")
            if ft=="未設定時間":
                final = f"設定 {ts} 推播的訂閱主題\n尚未設定推播時間\n已完成所有推播設定"
            else:
                final = f"設定 {ts} 推播的訂閱主題\n{ft}將會推播 {ts} 的資訊\n已完成所有推播設定"
        msg = TextMessage(text=final)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    if data == "action=cancel_push":
        msg = TextMessage(text="已取消推播設定")
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

def send_scheduled_news():
    now_str = datetime.now().strftime("%H:%M")
    for user_id, t in user_push_time.items():
        if t == now_str:
            sel = user_push_selection.get(user_id, {})
            push_topics = [tp for tp,v in sel.items() if v=="push"]
            # 準備所有要推的 bubbles
            all_bubbles = []
            for topic in push_topics:
                news_list = fetch_google_news(topic, 3)
                for n in news_list:
                    bubble = {
                        "type": "bubble",
                        "size": "micro",
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": topic,
                                    "weight": "bold",
                                    "size": "md",
                                    "margin": "md"
                                },
                                {
                                    "type": "text",
                                    "text": n["title"],
                                    "size": "sm",
                                    "weight": "bold",
                                    "wrap": True,
                                    "margin": "sm"
                                }
                            ]
                        },
                        "footer": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "uri",
                                        "label": "開啟新聞",
                                        "uri": n["url"]
                                    },
                                    "style": "primary",
                                    "height": "sm",
                                    "gravity": "center",
                                    "margin": "md"
                                }
                            ],
                            "spacing": "sm",
                            "paddingAll": "10px"
                        }
                    }
                    all_bubbles.append(bubble)
            configuration =Configuration(
                access_token=os.getenv('CHANNEL_ACCESS_TOKEN')
                )
            with ApiClient(configuration) as client:
                api = MessagingApi(client)
                for i in range(0, len(all_bubbles), 10):
                    carousel = {
                        "type": "carousel",
                        "contents": all_bubbles[i:i+10]
                    }
                    flex = FlexMessage(
                        alt_text="定時新聞推播",
                        contents=FlexContainer.from_dict(carousel)
                    )
                    api.push_message(
                        PushMessageRequest(to=user_id, messages=[flex])
                    )

def start_push_scheduler():
    # 每分鐘檢查推播
    schedule.every(1).minutes.do(send_scheduled_news)
    while True:
        schedule.run_pending()
        time.sleep(1)
