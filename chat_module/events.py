
from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room
from datetime import datetime, timezone

from extensions import db, socketio
from auth_module.models import User
from chat_module.models import (
    ConversationMember,
    ChatMessage,
    ChatMessageReceipt
)
from notification_module.models import Notification


# Track active connections for each user
active_users = {}


def utc_now():
    return datetime.now(timezone.utc)


def is_conversation_member(conversation_id, user_id):
    return ConversationMember.query.filter_by(
        conversation_id=conversation_id,
        user_id=user_id
    ).first() is not None


# JOIN CONVERSATION
@socketio.on("join_conversation")
def join_conversation(data):
    if not current_user.is_authenticated:
        return

    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError, AttributeError):
        return

    if not is_conversation_member(conversation_id, current_user.id):
        return

    join_room(f"conversation_{conversation_id}")

    # Mark received messages as delivered
    receipts = (
        ChatMessageReceipt.query
        .join(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.sender_id != current_user.id,
            ChatMessageReceipt.recipient_id == current_user.id,
            ChatMessageReceipt.delivered_at.is_(None)
        )
        .all()
    )

    for receipt in receipts:
        receipt.delivered_at = utc_now()

    if receipts:
        db.session.commit()

        for receipt in receipts:
            emit(
                "receipt_update",
                {
                    "message_id": receipt.message_id,
                    "recipient_id": current_user.id,
                    "status": "delivered"
                },
                room=f"conversation_{conversation_id}"
            )


# SEND MESSAGE
@socketio.on("send_message")
def send_message(data):
    if not current_user.is_authenticated:
        emit("message_error", {"error": "Please log in again."})
        return

    try:
        conversation_id = int(data.get("conversation_id"))
        content = str(data.get("content", "")).strip()
    except (TypeError, ValueError, AttributeError):
        emit("message_error", {"error": "Invalid message."})
        return

    if not content or len(content) > 5000:
        emit(
            "message_error",
            {"error": "Message must contain 1–5000 characters."}
        )
        return

    if not is_conversation_member(conversation_id, current_user.id):
        emit(
            "message_error",
            {"error": "You are not a member of this conversation."}
        )
        return

    message = ChatMessage(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=content
    )

    db.session.add(message)
    db.session.flush()

    members = ConversationMember.query.filter_by(
        conversation_id=conversation_id
    ).all()

    for conversation_member in members:

        if conversation_member.user_id != current_user.id:

            # Create individual delivery/read receipt
            receipt = ChatMessageReceipt(
                message_id=message.id,
                recipient_id=conversation_member.user_id
            )

            db.session.add(receipt)

            # Create notification
            notification = Notification(
                recipient_id=conversation_member.user_id,
                sender_id=current_user.id,
                conversation_id=conversation_id,
                message=f"{current_user.username} sent you a message."
            )

            db.session.add(notification)

    db.session.commit()

    message_data = {
        "id": message.id,
        "conversation_id": conversation_id,
        "sender_id": current_user.id,
        "sender_name": current_user.username,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "status": "sent"
    }

    emit(
        "new_message",
        message_data,
        room=f"conversation_{conversation_id}"
    )

    emit(
        "new_notification",
        {
            "message": f"{current_user.username} sent you a message."
        },
        room=f"conversation_{conversation_id}",
        include_self=False
    )


# MARK MESSAGES AS READ
@socketio.on("mark_messages_read")
def mark_messages_read(data):
    if not current_user.is_authenticated:
        return

    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError, AttributeError):
        return

    if not is_conversation_member(conversation_id, current_user.id):
        return

    receipts = (
        ChatMessageReceipt.query
        .join(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.sender_id != current_user.id,
            ChatMessageReceipt.recipient_id == current_user.id,
            ChatMessageReceipt.read_at.is_(None)
        )
        .all()
    )

    for receipt in receipts:
        now = utc_now()

        if receipt.delivered_at is None:
            receipt.delivered_at = now

        receipt.read_at = now

    if receipts:
        db.session.commit()

        for receipt in receipts:
            emit(
                "receipt_update",
                {
                    "message_id": receipt.message_id,
                    "recipient_id": current_user.id,
                    "status": "read"
                },
                room=f"conversation_{conversation_id}"
            )


# TYPING INDICATOR
@socketio.on("typing")
def typing(data):
    if not current_user.is_authenticated:
        return

    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError, AttributeError):
        return

    if is_conversation_member(conversation_id, current_user.id):
        emit(
            "user_typing",
            {"username": current_user.username},
            room=f"conversation_{conversation_id}",
            include_self=False
        )


# ONLINE STATUS
@socketio.on("connect")
def handle_connect(auth=None):
    if not current_user.is_authenticated:
        return

    user_id = current_user.id

    if user_id not in active_users:
        active_users[user_id] = set()

    active_users[user_id].add(request.sid)

    socketio.emit(
        "user_status",
        {
            "user_id": user_id,
            "username": current_user.username,
            "status": "online"
        }
    )


@socketio.on("disconnect")
def handle_disconnect(reason=None):
    if not current_user.is_authenticated:
        return

    user_id = current_user.id

    if user_id in active_users:
        active_users[user_id].discard(request.sid)

        if not active_users[user_id]:
            del active_users[user_id]

            user = db.session.get(User, user_id)

            if user:
                user.last_seen = utc_now()
                db.session.commit()

            socketio.emit(
                "user_status",
                {
                    "user_id": user_id,
                    "username": current_user.username,
                    "status": "offline"
                }
            )


@socketio.on("request_online_users")
def send_online_users():
    if not current_user.is_authenticated:
        return

    emit(
        "online_users",
        {"user_ids": list(active_users.keys())}
    )
