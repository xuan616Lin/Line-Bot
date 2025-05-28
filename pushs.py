# pushs.py
import os, time, schedule
from datetime import datetime, timedelta
from urllib.parse import quote
import requests, xml.etree.ElementTree as ET
from dotenv import load_dotenv
load_dotenv()

from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    TextMessage, QuickReply, QuickReplyItem, PostbackAction,
    PushMessageRequest, ReplyMessageRequest, FlexMessage, FlexContainer, DatetimePickerAction
)
from subscribetest import ALL_TOPICS             # 只有主題清單 :contentReference[oaicite:1]{index=1}
import db                                       # 讀寫訂閱與推播設定 :contentReference[oaicite:2]{index=2}

# 快取使用者的推播偏好（不包括訂閱清單）
user_push_selection = {}   # { user_id: { topic: bool, ... } }
user_push_time      = {}   # { user_id: "HH:MM", ... }

def get_default_push_time():
    return (datetime.now() + timedelta(minutes=1)).strftime("%H:%M")

def fetch_google_news(topic, count=3):
    rss = f"https://news.google.com/rss/search?q={quote(topic)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        r = requests.get(rss, timeout=5); r.raise_for_status()
        root = ET.fromstring(r.content)
    except:
        return []
    items = root.findall('.//item')[:count]
    return [{"title": it.findtext('title','').strip(),
             "url": it.findtext('link','').strip()} for it in items]

def build_push_quickreply(user_id):
    # 以 DB 為來源，不用 user_subscriptions
    subs     = db.list_subscriptions(user_id)
    settings = user_push_selection.setdefault(user_id, db.list_push_topics(user_id))
    items = []
    for topic in subs:
        enabled = settings.get(topic, False)
        label   = f"{topic}主題{'不' if enabled else ''}推播"
        choice  = not enabled
        items.append( QuickReplyItem(
            action=PostbackAction(
                label=label,
                data=f"action=set_push_choice&topic={topic}&choice={int(choice)}"
            )
        ))
    if any(settings.values()):
        items.append( QuickReplyItem(
            action=DatetimePickerAction(
                label="設定推播時間",
                data="action=set_push_time",
                mode="time",
                initial=get_default_push_time(),
                min="00:00", max="23:59"
            )
        ))
    items.append( QuickReplyItem(
        action=PostbackAction(label="完成推播設定", data="action=confirm_push")
    ))
    return QuickReply(items=items)

def build_push_status_text(user_id):
    subs     = db.list_subscriptions(user_id)
    settings = user_push_selection.get(user_id, {})
    push_t   = [t for t,en in settings.items() if en]
    txt = "請選擇要推播的訂閱主題:"
    if push_t:
        txt += "\n" + "\n".join(f"{t}:推播" for t in push_t)
        if ttime := user_push_time.get(user_id):
            txt += f"\n{ttime} 將推播 {'、'.join(push_t)} 的資訊"
    return txt

def handle_push_message(event, line_bot_api):
    user_id = event.source.user_id
    subs    = db.list_subscriptions(user_id)
    if not subs:
        from linebot.v3.messaging import QuickReplyItem  # 重新引入避免循環
        qr = QuickReply(items=[ QuickReplyItem(
            action=PostbackAction(label="＋ 新增訂閱", data="action=start_add_subscription")
        )])
        msg = TextMessage(text="目前沒有訂閱主題，請先新增訂閱", quick_reply=qr)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )
    # 每次都從 DB 載入最新選擇
    user_push_selection[user_id] = db.list_push_topics(user_id)
    text = build_push_status_text(user_id)
    qr   = build_push_quickreply(user_id)
    return line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(reply_token=event.reply_token,
                            messages=[TextMessage(text=text, quick_reply=qr)])
    )

def handle_push_postback(event, line_bot_api):
    data    = event.postback.data or ""
    user_id = event.source.user_id
    # 處理選擇推播與設定時間等，維持與 DB 同步
    if data.startswith("action=set_push_choice"):
        parts = dict(p.split("=",1) for p in data.split("&")[1:])
        topic = parts["topic"]
        choice= bool(int(parts["choice"]))
        # 更新快取 & DB
        user_push_selection.setdefault(user_id, {})[topic] = choice
        db.set_push_choice(user_id, topic, choice)
        # 若全取消則清掉時間
        if not any(user_push_selection[user_id].values()):
            db.set_push_time(user_id, None)
            user_push_time.pop(user_id, None)
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[ TextMessage(text=build_push_status_text(user_id),
                                       quick_reply=build_push_quickreply(user_id)) ]
            )
        )
    if data == "action=set_push_time":
        t = event.postback.params.get("time")
        if t:
            db.set_push_time(user_id, t)
            user_push_time[user_id] = t
            msg = TextMessage(text=f"{t}將會傳送 {'、'.join([tp for tp,en in user_push_selection[user_id].items() if en])} 的資訊",
                              quick_reply=build_push_quickreply(user_id))
        else:
            msg = TextMessage(text="設定推播時間失敗", quick_reply=build_push_quickreply(user_id))
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )
    if data == "action=confirm_push":
        sel = [t for t,en in user_push_selection.get(user_id,{}).items() if en]
        tme = user_push_time.get(user_id,"未設定時間")
        final = ("已完成所有推播設定，無主題啟用。" if not sel
                 else f"設定 {'、'.join(sel)} 推播，{tme} 將送出。")
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token,
                                messages=[TextMessage(text=final)])
        )

def send_scheduled_news():
    now = datetime.now().strftime("%H:%M")
    # 重新從 DB 載入所有排程與選擇
    schedule_map = db.list_push_schedule()
    topics_map   = {uid: db.list_push_topics(uid) for uid in schedule_map}
    for uid, t in schedule_map.items():
        if t == now:
            bubbles = []
            for topic, enabled in topics_map[uid].items():
                if not enabled: continue
                for n in fetch_google_news(topic):
                    bubbles.append({
                        "type":"bubble","size":"micro",
                        "body":{"type":"box","layout":"vertical","contents":[
                            {"type":"text","text":topic,"weight":"bold","size":"md","margin":"md"},
                            {"type":"text","text":n["title"],"size":"sm","weight":"bold","wrap":True,"margin":"sm"}
                        ]},
                        "footer":{"type":"box","layout":"vertical","contents":[
                            {"type":"button","action":{"type":"uri","label":"開啟新聞","uri":n["url"]},
                             "style":"primary","height":"sm","gravity":"center","margin":"md"}
                        ],"spacing":"sm","paddingAll":"10px"}
                    })
            if bubbles:
                config = Configuration(access_token=os.getenv('CHANNEL_ACCESS_TOKEN'))
                with ApiClient(config) as client:
                    api = MessagingApi(client)
                    carousel = {"type":"carousel","contents":bubbles}
                    flex = FlexMessage(alt_text="定時新聞推播",
                                      contents=FlexContainer.from_dict(carousel))
                    api.push_message(PushMessageRequest(to=uid, messages=[flex]))

def start_push_scheduler():
    schedule.every(1).minutes.do(send_scheduled_news)
    while True:
        schedule.run_pending()
        time.sleep(1)
