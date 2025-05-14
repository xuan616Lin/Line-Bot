# apps.py
from flask import Flask, request, abort
from dotenv import load_dotenv
load_dotenv()

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage

from news import handle_news
from subscribetest import (
    handle_subscribe, handle_subscribe_postback, handle_subscribe_text
    )
from pushs import (
    handle_push_message, handle_push_postback, start_push_scheduler
    )

import os
import threading

app = Flask(__name__)

configuration =Configuration(
    access_token=os.getenv('CHANNEL_ACCESS_TOKEN')
)
line_handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))


# 啟動推播排程緒
threading.Thread(target=start_push_scheduler, daemon=True).start()

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        text = event.message.text.strip()
        if text == "即時新聞":
            handle_news(event, line_bot_api)
        elif text == "管理我的訂閱":
            handle_subscribe(event, line_bot_api)
        elif text == "推播訊息":
            handle_push_message(event, line_bot_api)
        else:
            # 先嘗試文字訂閱處理，若回傳 False 才當作一般回覆
            if not handle_subscribe_text(event, line_bot_api):
                line_bot_api.reply_message_with_http_info(
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
        # 推播相關
        if data.startswith("action=set_push_choice") or \
            data.startswith("action=set_push_time") or \
            data in ("action=confirm_push", "action=cancel_push"):
            handle_push_postback(event, line_bot_api)
        # 訂閱相關（含推薦／搜尋／返回管理首頁）
        elif (
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
            handle_subscribe_postback(event, line_bot_api)

if __name__ == "__main__":
    app.run(port=8000, debug=True)


