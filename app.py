# app.py

import os
from dotenv import load_dotenv

# 1. 先載入 .env
load_dotenv()

# 2. 初始化資料庫（create table if not exists…）
import db
from db import init_db
init_db()

from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage,ImageMessage
)

# 從子模組 import 各功能處理器
from news import handle_news
from subscribetest import (
    handle_subscribe,
    handle_subscribe_postback,
    handle_subscribe_text
)
from pushs import (
    handle_push_message,
    handle_push_postback,
    start_push_scheduler
)

import threading

app = Flask(__name__)

# 3. 從環境變數讀取 LINE Bot 憑證
configuration = Configuration(access_token=os.getenv("CHANNEL_ACCESS_TOKEN"))
line_handler  = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# 4. 啟動背景推播排程
threading.Thread(target=start_push_scheduler, daemon=True).start()

@app.route("/callback", methods=["GET","POST"])
def callback():
    if request.method == "GET":
        return "OK", 200
    
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
        
    return "OK",200

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        text = event.message.text.strip()

        if text == "即時新聞":
            return handle_news(event, line_bot_api)

        elif text == "管理我的訂閱":
            return handle_subscribe(event, line_bot_api)

        elif text == "推播訊息":
            return handle_push_message(event, line_bot_api)

        else:
            # 只有在訂閱文字模式下才消化，否則回文字
            if not handle_subscribe_text(event, line_bot_api):
                return line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=text)]
                    )
                )

@line_handler.add(PostbackEvent)
def handle_postback(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        data = event.postback.data or ""

        # --- 推播相關 ---
        if (
            data.startswith("action=set_push_choice")
            or data.startswith("action=set_push_time")
            or data in ("action=confirm_push", "action=cancel_push")
        ):
            return handle_push_postback(event, line_bot_api)

        # --- 訂閱相關 ---
        if (
            data.startswith("action=subscribe&topic=")
            or data.startswith("action=unsubscribe&topic=")
            or data in (
                "action=start_add_subscription",
                "action=start_remove_subscription",
                "action=confirm_subscription",
                "action=recommend_keywords",
                "action=manage_subscription",
            )
        ):
            return handle_subscribe_postback(event, line_bot_api)

if __name__ == "__main__":
    # 在本地測試可以跑 8000 埠，部署到 Vercel 時會自動以環境變數 PORT 覆蓋
    app.run(host="0.0.0.0", port=8000, debug=True)
