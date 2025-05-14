from linebot.v3.messaging import (
    ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, PostbackAction
)
import re

# 模擬儲存：user_subscriptions 格式 { user_id: [topic1, topic2, ...] }
user_subscriptions = {}

# 可訂閱主題清單
ALL_TOPICS = ["大雨","土石流","地震","颱風","海嘯","火災","洪水","暴風雪",]

# 訂閱管理模式：{'user_id': 'subscribe'|'unsubscribe'|None}
user_modes = {}

def get_recommended_keywords(user_id):
    """
    取出系統推薦的熱門關鍵字，實際可接外部分析結果或 DB。
    """
    # 範例：固定回傳 5 個熱門詞
    return ["AI", "疫情", "豪大雨", "農業部", "缺電預警"]

def handle_subscribe(event, line_bot_api):
    user_id = event.source.user_id if hasattr(event.source, 'user_id') else "unknown"
    # 進入管理訂閱，重置模式
    user_modes[user_id] = None

    current = user_subscriptions.setdefault(user_id, [])
    topics_str = "、".join(current) if current else "目前沒有訂閱任何主題"
    reply_text = f"你目前的訂閱：\n{topics_str}\n請選擇操作："

    items = [
        QuickReplyItem(
            action=PostbackAction(label="🔥 推薦關鍵字", data="action=recommend_keywords")
        )
    ]
    # 原有新增／取消
    if len(current) < len(ALL_TOPICS):
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="＋ 新增訂閱", data="action=start_add_subscription")
            )
        )
    if current:
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="🚫 取消訂閱", data="action=start_remove_subscription")
            )
        )
    items.append(
        QuickReplyItem(
            action=PostbackAction(label="✅ 完成設定", data="action=confirm_subscription")
        )
    )

    quick_reply = QuickReply(items=items)
    return line_bot_api.reply_message_with_http_info(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=reply_text, quick_reply=quick_reply)]
        )
    )

def handle_subscribe_postback(event, line_bot_api):
    data = event.postback.data or ""
    user_id = event.source.user_id if hasattr(event.source, 'user_id') else "unknown"
    current = user_subscriptions.setdefault(user_id, [])

    # 推薦關鍵字
    if data == "action=recommend_keywords":
        recs = get_recommended_keywords(user_id)
        items = [QuickReplyItem(
            action=PostbackAction(label=k, data=f"action=subscribe&topic={k}")
        ) for k in recs]
        items.append(QuickReplyItem(
            action=PostbackAction(label="⬅ 返回", data="action=manage_subscription")
        ))
        msg = TextMessage(text="系統推薦關鍵字，請選擇要訂閱：", quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[msg])
        )

    if data == "action=manage_subscription":
        return handle_subscribe(event, line_bot_api)
    
    # 1. 開始新增
    if data == "action=start_add_subscription":
        user_modes[user_id] = 'subscribe'
        available = [t for t in ALL_TOPICS if t not in current]
        items = [
            QuickReplyItem(
                action=PostbackAction(label=t, data=f"action=subscribe&topic={t}")
            )
            for t in available
        ]
        # 【新增】如果已有至少一個訂閱，就提供「取消訂閱」入口
        if current:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="取消訂閱", data="action=start_remove_subscription")
                )
            )
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="完成訂閱設定", data="action=confirm_subscription")
            )
        )
        msg = TextMessage(text="請選擇要新增的訂閱主題：", quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(ReplyMessageRequest(
            reply_token=event.reply_token, messages=[msg]
        ))

    # 2. 真正訂閱（QuickReply 按鈕）
    if data.startswith("action=subscribe&topic="):
        topic = data.split("action=subscribe&topic=")[1]
        if topic not in current:
            current.append(topic)

        # 重新列出可新增的主題
        available = [t for t in ALL_TOPICS if t not in current]
        items = [
            QuickReplyItem(
                action=PostbackAction(label=t, data=f"action=subscribe&topic={t}")
            )
            for t in available
        ]
        # 【新增】如果已有至少一個訂閱，就提供「取消訂閱」入口
        if current:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="取消訂閱", data="action=start_remove_subscription")
                )
            )
        items.append(
            QuickReplyItem(
                action=PostbackAction(label="完成訂閱設定", data="action=confirm_subscription")
            )
        )

        topics_str = "、".join(current) or "目前沒有訂閱任何主題"
        reply_text = f"你目前的訂閱：\n{topics_str}\n請選擇操作："
        msg = TextMessage(text=reply_text, quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(ReplyMessageRequest(
            reply_token=event.reply_token, messages=[msg]
        ))

    # 開始取消
    if data == "action=start_remove_subscription":
        user_modes[user_id] = 'unsubscribe'
        if not current:
            msg = TextMessage(text="目前沒有訂閱任何主題可以取消")
        else:
            items = [QuickReplyItem(action=PostbackAction(label=t, data=f"action=unsubscribe&topic={t}"))
                     for t in current]
            items.append(QuickReplyItem(action=PostbackAction(label="完成訂閱設定", data="action=confirm_subscription")))
            msg = TextMessage(text="請選擇要取消的訂閱主題：", quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(ReplyMessageRequest(
            reply_token=event.reply_token, messages=[msg]
        ))

    # 真正取消（QuickReply 按鈕）
    if data.startswith("action=unsubscribe&topic="):
        topic = data.split("action=unsubscribe&topic=")[1]
        if topic in current:
            current.remove(topic)
        # 重新呈現取消列表或新增入口
        items = []
        if current:
            items += [QuickReplyItem(action=PostbackAction(label=t, data=f"action=unsubscribe&topic={t}"))
                      for t in current]
            available = [t for t in ALL_TOPICS if t not in current]
            if available:
                items.append(QuickReplyItem(action=PostbackAction(label="新增訂閱", data="action=start_add_subscription")))
        else:
            items.append(QuickReplyItem(action=PostbackAction(label="新增訂閱", data="action=start_add_subscription")))
        items.append(QuickReplyItem(action=PostbackAction(label="完成訂閱設定", data="action=confirm_subscription")))

        topics_str = "、".join(current) or "目前沒有訂閱任何主題"
        reply_text = f"你目前的訂閱：\n{topics_str}\n請選擇操作："
        msg = TextMessage(text=reply_text, quick_reply=QuickReply(items=items))
        return line_bot_api.reply_message_with_http_info(ReplyMessageRequest(
            reply_token=event.reply_token, messages=[msg]
        ))

    # 完成設定
    if data == "action=confirm_subscription":
        user_modes[user_id] = None
        topics_str = "、".join(current) or "目前沒有訂閱任何主題"
        msg = TextMessage(text=f"你目前的訂閱：\n{topics_str}\n已完成訂閱設定")
        return line_bot_api.reply_message_with_http_info(ReplyMessageRequest(
            reply_token=event.reply_token, messages=[msg]
        ))
    pass

def handle_subscribe_text(event, line_bot_api):
    user_id = event.source.user_id if hasattr(event.source, 'user_id') else "unknown"
    mode = user_modes.get(user_id)

    # 只有在「新增」或「取消」模式下才處理文字
    if mode not in ('subscribe', 'unsubscribe'):
        return False

    text = event.message.text.strip()
    current = user_subscriptions.setdefault(user_id, [])

    # 新增模式
    # --- 新增模式 ---
    if mode == 'subscribe':
        # 處理手動加入
        if text in current:
            action_msg = f"你已經訂閱過「{text}」。"
        else:
            current.append(text)
            action_msg = f"你已成功訂閱「{text}」。"

        # **維持在「新增訂閱」模式**，重新組 QuickReply
        available = [t for t in ALL_TOPICS if t not in current]
        items = [
            QuickReplyItem(
                action=PostbackAction(label=t, data=f"action=subscribe&topic={t}")
            ) for t in available
        ]
        # 同時保留「手動取消訂閱」入口
        if current:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(label="🚫 取消訂閱", data="action=start_remove_subscription")
                )
            )
        # 完成按鈕
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

    # 取消模式：支援多個，用「、」「,」「，」切分
    else:  # mode == 'unsubscribe'
        tokens = [t.strip() for t in __import__('re').split(r'[、,，]', text) if t.strip()]
        unsubscribed = []
        not_subscribed = []
        for t in tokens:
            if t in current:
                current.remove(t)
                unsubscribed.append(t)
            else:
                not_subscribed.append(t)
        parts = []
        if unsubscribed:
            parts.append(f"已取消訂閱「{'、'.join(unsubscribed)}」")
        if not_subscribed:
            parts.append(f"未訂閱過「{'、'.join(not_subscribed)}」")
        action_msg = "；".join(parts) if parts else "未偵測到有效主題。"

    # 處理完文字後，回到管理首頁
    user_modes[user_id] = None
    return handle_subscribe(event, line_bot_api)