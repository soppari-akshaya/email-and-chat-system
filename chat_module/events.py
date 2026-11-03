from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room
from datetime import datetime, timezone

from extensions import db, socketio
from auth_module.models import User
from chat_module.models import (
    Conversation,
    ConversationMember,
    ChatMessage,
    ChatMessageReceipt
)
from notification_module.models import Notification


# --------------------------------------------------
# ACTIVE USERS
# --------------------------------------------------

active_users = {}


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def utc_iso(value):
    """Return a UTC ISO timestamp with an explicit timezone."""
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)

    return value.isoformat().replace("+00:00", "Z")


def is_conversation_member(conversation_id, user_id):
    return ConversationMember.query.filter_by(
        conversation_id=conversation_id,
        user_id=user_id
    ).first() is not None


def get_message_data(message):
    """Prepare message data for Socket.IO responses."""
    reply_data = None
    if message.reply_to:
        reply_data = {
            "id": message.reply_to.id,
            "sender_name": message.reply_to.sender.username if message.reply_to.sender else "User",
            "content": "This message was deleted." if message.reply_to.is_deleted else (message.reply_to.content or message.reply_to.attachment_name or "Attachment")
        }

    status = message.get_status_for_sender()

    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "sender_name": message.sender.username if message.sender else "User",
        "sender_avatar": message.sender.profile.profile_image if (message.sender and message.sender.profile) else None,
        "content": message.content,
        "created_at": utc_iso(message.created_at),
        "is_edited": message.is_edited,
        "edited_at": utc_iso(message.edited_at),
        "is_deleted": message.is_deleted,
        "attachment_name": message.attachment_name,
        "attachment_mimetype": message.attachment_mimetype,
        "attachment_size": message.attachment_size,
        "has_attachment": bool(message.attachment_path),
        "reply_to": reply_data,
        "status": status,
        "delivery_status": status,
        "delivered_at": utc_iso(message.delivered_at),
        "seen_at": utc_iso(message.seen_at)
    }


def get_message_preview(message):
    """Get the text displayed below a conversation name."""
    if message.is_deleted:
        return "This message was deleted."

    if message.content and message.content != "This message was deleted.":
        return message.content

    if message.attachment_name:
        return f"📎 {message.attachment_name}"

    return "New message"


def notify_conversation_members(conversation_id, event_name, payload):
    """Send an event to every connected member's personal room."""
    conversation = db.session.get(Conversation, conversation_id)
    members = ConversationMember.query.filter_by(
        conversation_id=conversation_id
    ).all()

    for member in members:
        member_payload = dict(payload)
        if conversation and not conversation.is_group:
            other = [m for m in members if m.user_id != member.user_id]
            if other and other[0].user:
                partner_user = other[0].user
                member_payload["title"] = partner_user.username
                member_payload["partner_id"] = partner_user.id
                member_payload["is_group"] = False
                member_payload["has_avatar"] = bool(partner_user.profile and partner_user.profile.profile_image)
                member_payload["partner_email"] = partner_user.email
        elif conversation and conversation.is_group:
            member_payload["title"] = conversation.name or "Group Chat"
            member_payload["is_group"] = True

        socketio.emit(
            event_name,
            member_payload,
            to=f"user_{member.user_id}"
        )


def refresh_conversation_preview(conversation_id, sender_id):
    """Refresh the sidebar preview after editing or deleting a message."""
    conversation = db.session.get(Conversation, conversation_id)
    if not conversation:
        return

    latest_message = (
        ChatMessage.query
        .filter_by(conversation_id=conversation_id)
        .order_by(
            ChatMessage.created_at.desc(),
            ChatMessage.id.desc()
        )
        .first()
    )

    if not latest_message:
        return

    notify_conversation_members(
        conversation_id,
        "conversation_list_update",
        {
            "conversation_id": conversation_id,
            "last_message_at": utc_iso(
                conversation.last_message_at or latest_message.created_at
            ),
            "last_message": get_message_preview(latest_message),
            "sender_id": sender_id,
            "sender_name": latest_message.sender.username if latest_message.sender else "User"
        }
    )


# --------------------------------------------------
# JOIN CONVERSATION
# --------------------------------------------------

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

    room = f"conversation_{conversation_id}"
    join_room(room)

    # Mark non-delivered messages as delivered
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

    now = utc_now()
    for receipt in receipts:
        receipt.delivered_at = now
        if receipt.chat_message:
            receipt.chat_message.delivered_at = now
            if receipt.chat_message.delivery_status == "sent":
                receipt.chat_message.delivery_status = "delivered"

    if receipts:
        db.session.commit()
        for receipt in receipts:
            payload = {
                "message_id": receipt.message_id,
                "recipient_id": current_user.id,
                "conversation_id": conversation_id,
                "status": "delivered"
            }
            socketio.emit("receipt_update", payload, to=room)
            if receipt.chat_message:
                socketio.emit("receipt_update", payload, to=f"user_{receipt.chat_message.sender_id}")

    emit("conversation_joined", {"conversation_id": conversation_id})


# --------------------------------------------------
# SEND MESSAGE
# --------------------------------------------------

@socketio.on("send_message")
def send_message(data):
    if not current_user.is_authenticated:
        emit("message_error", {"error": "Please log in again."})
        return

    try:
        conversation_id = int(data.get("conversation_id"))
        content = str(data.get("content", "")).strip()
        reply_to_id = data.get("reply_to_id")
        if reply_to_id is not None:
            reply_to_id = int(reply_to_id)
    except (TypeError, ValueError, AttributeError):
        emit("message_error", {"error": "Invalid message."})
        return

    if not content or len(content) > 5000:
        emit("message_error", {"error": "Message must contain 1–5000 characters."})
        return

    if not is_conversation_member(conversation_id, current_user.id):
        emit("message_error", {"error": "You are not a member of this conversation."})
        return

    # Verify reply_to exists in conversation if provided
    if reply_to_id:
        reply_msg = ChatMessage.query.filter_by(id=reply_to_id, conversation_id=conversation_id).first()
        if not reply_msg:
            reply_to_id = None

    message = ChatMessage(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=content,
        reply_to_id=reply_to_id
    )

    db.session.add(message)
    db.session.flush()

    members = ConversationMember.query.filter_by(
        conversation_id=conversation_id
    ).all()

    now = utc_now()
    delivered_count = 0
    for member in members:
        if member.user_id == current_user.id:
            continue

        is_online = member.user_id in active_users
        deliv_time = now if is_online else None
        if is_online:
            delivered_count += 1

        db.session.add(
            ChatMessageReceipt(
                message_id=message.id,
                recipient_id=member.user_id,
                delivered_at=deliv_time
            )
        )

        db.session.add(
            Notification(
                recipient_id=member.user_id,
                sender_id=current_user.id,
                conversation_id=conversation_id,
                message=f"{current_user.username}: {content[:60]}"
            )
        )

    if delivered_count > 0:
        message.delivered_at = now
        message.delivery_status = "delivered"
    else:
        message.delivery_status = "sent"

    conversation = db.session.get(Conversation, conversation_id)
    if conversation:
        conversation.last_message_at = message.created_at

    db.session.commit()

    message_data = get_message_data(message)

    # 1. Emit to conversation room (for users currently viewing the chat)
    socketio.emit(
        "new_message",
        message_data,
        to=f"conversation_{conversation_id}"
    )

    # 2. Emit to each conversation member's personal room and push notification & badges
    for member in members:
        socketio.emit(
            "new_message",
            message_data,
            to=f"user_{member.user_id}"
        )

        if member.user_id != current_user.id:
            socketio.emit(
                "new_notification",
                {
                    "message": f"{current_user.username}: {content[:60]}",
                    "conversation_id": conversation_id,
                    "type": "chat",
                    "link": f"/chat/conversation/{conversation_id}"
                },
                to=f"user_{member.user_id}"
            )

            try:
                from email_module.models import Email
                unread_emails = Email.query.filter_by(recipient_id=member.user_id, folder="inbox", is_read=False).count()
                unread_notifs = Notification.query.filter_by(recipient_id=member.user_id, is_read=False).count()
                socketio.emit(
                    "update_unread_counts",
                    {
                        "unread_emails": unread_emails,
                        "unread_notifications": unread_notifs
                    },
                    to=f"user_{member.user_id}"
                )
            except Exception:
                pass

    notify_conversation_members(
        conversation_id,
        "conversation_list_update",
        {
            "conversation_id": conversation_id,
            "last_message_at": utc_iso(message.created_at),
            "last_message": message.content,
            "sender_id": current_user.id,
            "sender_name": current_user.username
        }
    )


# --------------------------------------------------
# EDIT MESSAGE
# --------------------------------------------------

@socketio.on("edit_message")
def edit_message(data):
    if not current_user.is_authenticated:
        emit("message_error", {"error": "Please log in again."})
        return

    try:
        message_id = int(data.get("message_id"))
        content = str(data.get("content", "")).strip()
    except (TypeError, ValueError, AttributeError):
        emit("message_error", {"error": "Invalid message details."})
        return

    if not content or len(content) > 5000:
        emit("message_error", {"error": "Message must contain 1–5000 characters."})
        return

    message = db.session.get(ChatMessage, message_id)
    if not message:
        emit("message_error", {"error": "Message not found."})
        return

    if message.sender_id != current_user.id:
        emit("message_error", {"error": "You can only edit your own messages."})
        return

    if message.is_deleted:
        emit("message_error", {"error": "Deleted messages cannot be edited."})
        return

    message.content = content
    message.is_edited = True
    message.edited_at = utc_now()
    db.session.commit()

    emit(
        "message_updated",
        {
            "message_id": message.id,
            "conversation_id": message.conversation_id,
            "content": message.content,
            "is_edited": True,
            "edited_at": utc_iso(message.edited_at)
        },
        to=f"conversation_{message.conversation_id}"
    )

    refresh_conversation_preview(message.conversation_id, current_user.id)


# --------------------------------------------------
# DELETE MESSAGE
# --------------------------------------------------

@socketio.on("delete_message")
def delete_message(data):
    if not current_user.is_authenticated:
        emit("message_error", {"error": "Please log in again."})
        return

    try:
        message_id = int(data.get("message_id"))
    except (TypeError, ValueError, AttributeError):
        emit("message_error", {"error": "Invalid message ID."})
        return

    message = db.session.get(ChatMessage, message_id)
    if not message:
        emit("message_error", {"error": "Message not found."})
        return

    if message.sender_id != current_user.id:
        emit("message_error", {"error": "You can only delete your own messages."})
        return

    if message.is_deleted:
        emit("message_error", {"error": "Message is already deleted."})
        return

    message.is_deleted = True
    message.content = "This message was deleted."
    db.session.commit()

    emit(
        "message_deleted",
        {
            "message_id": message.id,
            "conversation_id": message.conversation_id,
            "content": message.content,
            "is_deleted": True
        },
        to=f"conversation_{message.conversation_id}"
    )

    refresh_conversation_preview(message.conversation_id, current_user.id)


# --------------------------------------------------
# MARK MESSAGES AS READ
# --------------------------------------------------

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

    now = utc_now()
    for receipt in receipts:
        if receipt.delivered_at is None:
            receipt.delivered_at = now
        receipt.read_at = now
        if receipt.chat_message:
            receipt.chat_message.seen_at = now
            receipt.chat_message.delivery_status = "seen"

    if receipts:
        db.session.commit()
        for receipt in receipts:
            payload = {
                "message_id": receipt.message_id,
                "recipient_id": current_user.id,
                "conversation_id": conversation_id,
                "status": "read"
            }
            socketio.emit("receipt_update", payload, to=f"conversation_{conversation_id}")
            if receipt.chat_message:
                socketio.emit("receipt_update", payload, to=f"user_{receipt.chat_message.sender_id}")


# --------------------------------------------------
# TYPING INDICATOR
# --------------------------------------------------

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
            to=f"conversation_{conversation_id}",
            include_self=False
        )


# --------------------------------------------------
# ONLINE STATUS
# --------------------------------------------------

@socketio.on("connect")
def handle_connect(auth=None):
    if not current_user.is_authenticated:
        return

    user_id = current_user.id
    if user_id not in active_users:
        active_users[user_id] = set()

    active_users[user_id].add(request.sid)
    join_room(f"user_{user_id}")

    # Update online_status in SQLite
    user = db.session.get(User, user_id)
    if user:
        user.online_status = "online"
        user.last_seen = utc_now()
        db.session.commit()

    # Mark any pending messages for this user as delivered in SQLite
    pending_receipts = (
        ChatMessageReceipt.query
        .filter(
            ChatMessageReceipt.recipient_id == user_id,
            ChatMessageReceipt.delivered_at.is_(None)
        )
        .all()
    )
    if pending_receipts:
        now = utc_now()
        for r in pending_receipts:
            r.delivered_at = now
            if r.chat_message:
                r.chat_message.delivered_at = now
                if r.chat_message.delivery_status == "sent":
                    r.chat_message.delivery_status = "delivered"
                payload = {
                    "message_id": r.message_id,
                    "recipient_id": user_id,
                    "conversation_id": r.chat_message.conversation_id,
                    "status": "delivered"
                }
                socketio.emit("receipt_update", payload, to=f"conversation_{r.chat_message.conversation_id}")
                socketio.emit("receipt_update", payload, to=f"user_{r.chat_message.sender_id}")
        db.session.commit()

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
                user.online_status = "offline"
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



# --------------------------------------------------
# SEND ONLINE USERS
# --------------------------------------------------

@socketio.on("request_online_users")
def send_online_users():
    if not current_user.is_authenticated:
        return

    emit(
        "online_users",
        {"user_ids": list(active_users.keys())}
    )
