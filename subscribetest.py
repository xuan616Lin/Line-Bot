# subscribetest.py

import re
from linebot.v3.messaging import (
    ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, PostbackAction
)
import db  # 你在專案根目錄下建立的 db.py，裡面有 list/add/remove_subscription

# 可訂閱主題清單
ALL_TOPICS = ["大雨","土石流","地震","颱風","海嘯","火災","洪水","暴風雪"]

# 訂閱管理模式：{ user_id: 'subscribe' | 'unsubscribe' | None }
user_modes = {}

def get_recommended_keywords(user_id):
    # 範例：固定回傳 5 個熱門詞，改接你的分析結果也行
    return ["AI", "疫情", "豪大雨", "農業部", "缺電預警"]

def handle_subscribe(event, line_bot_api):
    user_id = event.source.user_id
    # 進入管理訂閱，重置模式
    user_modes[user_id] = None

    # 從資料庫讀出使用者目前所有訂閱
    current = db.list_subscriptions(user_id)
    topics_str = "、".join(current) if current else "目前沒有訂閱任何主題"
    reply_text = f"你目前的訂閱：\n{topics_str}\n請選擇操作："

    items = [
        QuickReplyItem(
            action=PostbackAction(label="🔥 推薦關鍵字", data="action=recommend_keywords")
        )
    ]
    # 新增訂閱
    if len(current) < len(ALL_TOPICS):
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="＋ 新增訂閱", data="action=start_add_subscription")
            )
        )
    # 取消訂閱
    if current:
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="🚫 取消訂閱", data="action=start_remove_subscription")
            )
        )
    # 完成
    items.append(
        QuickReplyItem(
            action=PostbackAction(label="✅ 完成設定", data="action=confirm_subscription")
        )
    )

    qr = QuickReply(items=items)
    return line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=reply_text, quick_reply=qr)]
        )
    )

def handle_subscribe_postback(event, line_bot_api):
    data = event.postback.data or ""
    user_id = event.source.user_id
    current = db.list_subscriptions(user_id)

    # 推薦關鍵字
    if data == "action=recommend_keywords":
        recs = get_recommended_keywords(user_id)
        items = [
            QuickReplyItem(
                action=PostbackAction(label=k, data=f"action=subscribe&topic={k}")
            ) for k in recs
        ]
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="⬅ 返回", data="action=manage_subscription")
            )
        )
        msg = TextMessage(text="系統推薦關鍵字，請選擇要訂閱：", quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    # 返回管理首頁
    if data == "action=manage_subscription":
        return handle_subscribe(event, line_bot_api)

    # 1. 開始新增
    if data == "action=start_add_subscription":
        user_modes[user_id] = 'subscribe'
        available = [t for t in ALL_TOPICS if t not in current]
        items = [
            QuickReplyItem(
                action=PostbackAction(label=t, data=f"action=subscribe&topic={t}")
            ) for t in available
        ]
        # 若已有訂閱，保留切換到取消流程
        if current:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="🚫 取消訂閱", data="action=start_remove_subscription")
                )
            )
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="✅ 完成訂閱設定", data="action=confirm_subscription")
            )
        )
        msg = TextMessage(text="請選擇要新增的訂閱主題：", quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    # 2. 真正訂閱（QuickReply 按鈕）
    if data.startswith("action=subscribe&topic="):
        topic = data.split("action=subscribe&topic=")[1]
        db.add_subscription(user_id, topic)
        current = db.list_subscriptions(user_id)

        available = [t for t in ALL_TOPICS if t not in current]
        items = [
            QuickReplyItem(
                action=PostbackAction(label=t, data=f"action=subscribe&topic={t}")
            ) for t in available
        ]
        if current:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="🚫 取消訂閱", data="action=start_remove_subscription")
                )
            )
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="✅ 完成訂閱設定", data="action=confirm_subscription")
            )
        )

        topics_str = "、".join(current) or "目前沒有訂閱任何主題"
        reply_text = f"你目前的訂閱：\n{topics_str}\n請選擇操作："
        msg = TextMessage(text=reply_text, quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    # 開始取消
    if data == "action=start_remove_subscription":
        user_modes[user_id] = 'unsubscribe'
        if not current:
            msg = TextMessage(text="目前沒有訂閱任何主題可以取消")
        else:
            items = [
                QuickReplyItem(
                    action=PostbackAction(label=t, data=f"action=unsubscribe&topic={t}")
                ) for t in current
            ]
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="✅ 完成訂閱設定", data="action=confirm_subscription")
                )
            )
            msg = TextMessage(text="請選擇要取消的訂閱主題：", quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    # 真正取消（QuickReply 按鈕）
    if data.startswith("action=unsubscribe&topic="):
        topic = data.split("action=unsubscribe&topic=")[1]
        db.remove_subscription(user_id, topic)
        current = db.list_subscriptions(user_id)

        items = []
        if current:
            items += [
                QuickReplyItem(
                    action=PostbackAction(label=t, data=f"action=unsubscribe&topic={t}")
                ) for t in current
            ]
            # 如果還能新增
            available = [t for t in ALL_TOPICS if t not in current]
            if available:
                items.append(
                    QuickReplyItem(
                        action=PostbackAction(label="＋ 新增訂閱", data="action=start_add_subscription")
                    )
                )
        else:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="＋ 新增訂閱", data="action=start_add_subscription")
                )
            )
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="✅ 完成訂閱設定", data="action=confirm_subscription")
            )
        )

        topics_str = "、".join(current) or "目前沒有訂閱任何主題"
        reply_text = f"你目前的訂閱：\n{topics_str}\n請選擇操作："
        msg = TextMessage(text=reply_text, quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    # 完成設定
    if data == "action=confirm_subscription":
        user_modes[user_id] = None
        current = db.list_subscriptions(user_id)
        topics_str = "、".join(current) if current else "目前沒有訂閱任何主題"
        msg = TextMessage(text=f"你目前的訂閱：\n{topics_str}\n已完成訂閱設定")
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

def handle_subscribe_text(event, line_bot_api):
    user_id = event.source.user_id
    mode = user_modes.get(user_id)

    # 只有在「新增(subscribe)」或「取消(unsubscribe)」模式下才處理文字
    if mode not in ('subscribe', 'unsubscribe'):
        return False

    text = event.message.text.strip()
    current = db.list_subscriptions(user_id)

    # 文字新增訂閱
    if mode == 'subscribe':
        if text in current:
            action_msg = f"你已經訂閱過「{text}」。"
        else:
            db.add_subscription(user_id, text)
            action_msg = f"你已成功訂閱「{text}」。"
        current = db.list_subscriptions(user_id)

        # 維持在「新增訂閱」模式，重組 QuickReply
        available = [t for t in ALL_TOPICS if t not in current]
        items = [
            QuickReplyItem(
                action=PostbackAction(label=t, data=f"action=subscribe&topic={t}")
            ) for t in available
        ]
        if current:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="🚫 取消訂閱", data="action=start_remove_subscription")
                )
            )
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="✅ 完成訂閱設定", data="action=confirm_subscription")
            )
        )

        topics_str = "、".join(current) or "目前沒有訂閱任何主題"
        reply_text = f"{action_msg}\n你目前的訂閱：\n{topics_str}\n請繼續新增或其他操作："
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text, quick_reply=QuickReply(items=items))]
            )
        )
        return True

    # 文字取消訂閱（支援多重分隔）
    tokens = [t.strip() for t in re.split(r'[、,，]', text) if t.strip()]
    unsubscribed, not_subscribed = [], []
    for t in tokens:
        if t in current:
            db.remove_subscription(user_id, t)
            unsubscribed.append(t)
        else:
            not_subscribed.append(t)

    parts = []
    if unsubscribed:
        parts.append(f"已取消訂閱「{'、'.join(unsubscribed)}」")
    if not_subscribed:
        parts.append(f"未訂閱過「{'、'.join(not_subscribed)}」")
    action_msg = "；".join(parts) if parts else "未偵測到有效主題。"

    # 文字取消後，回到管理首頁
    user_modes[user_id] = None
    return handle_subscribe(event, line_bot_api)
