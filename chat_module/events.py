
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

    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "sender_name": message.sender.username,
        "content": message.content,
        "created_at": utc_iso(message.created_at),
        "is_edited": message.is_edited,
        "edited_at": utc_iso(message.edited_at),
        "is_deleted": message.is_deleted,
        "attachment_name": message.attachment_name,
        "attachment_mimetype": message.attachment_mimetype,
        "attachment_size": message.attachment_size,
        "has_attachment": bool(message.attachment_path),
        "status": "sent"
    }


def get_message_preview(message):
    """Get the text displayed below a conversation name."""

    if message.is_deleted:
        return "This message was deleted."

    if message.content and message.content != "This message was deleted.":
        return message.content

    if message.attachment_name:
        return message.attachment_name

    return "New message"


def notify_conversation_members(conversation_id, event_name, payload):
    """Send an event to every connected member's personal room."""

    members = ConversationMember.query.filter_by(
        conversation_id=conversation_id
    ).all()

    for member in members:
        socketio.emit(
            event_name,
            payload,
            to=f"user_{member.user_id}"
        )


def update_conversation_activity(conversation_id, message):
    """Update latest activity and notify all conversation members."""

    conversation = db.session.get(
        Conversation,
        conversation_id
    )

    if not conversation:
        return

    conversation.last_message_at = message.created_at

    db.session.commit()

    notify_conversation_members(
        conversation_id,
        "conversation_list_update",
        {
            "conversation_id": conversation_id,
            "last_message_at": utc_iso(message.created_at),
            "last_message": get_message_preview(message),
            "sender_id": message.sender_id,
            "sender_name": message.sender.username
        }
    )


def refresh_conversation_preview(conversation_id, sender_id):
    """Refresh the sidebar preview after editing or deleting a message."""

    conversation = db.session.get(
        Conversation,
        conversation_id
    )

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
            "sender_name": latest_message.sender.username
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

    if not is_conversation_member(
        conversation_id,
        current_user.id
    ):
        return

    room = f"conversation_{conversation_id}"

    join_room(room)

    # Find messages that have not yet been delivered.
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
                to=room
            )

    emit(
        "conversation_joined",
        {
            "conversation_id": conversation_id
        }
    )


# --------------------------------------------------
# SEND MESSAGE
# --------------------------------------------------

@socketio.on("send_message")
def send_message(data):

    if not current_user.is_authenticated:
        emit(
            "message_error",
            {"error": "Please log in again."}
        )
        return

    try:
        conversation_id = int(data.get("conversation_id"))
        content = str(data.get("content", "")).strip()

    except (TypeError, ValueError, AttributeError):
        emit(
            "message_error",
            {"error": "Invalid message."}
        )
        return

    if not content or len(content) > 5000:
        emit(
            "message_error",
            {
                "error": "Message must contain 1–5000 characters."
            }
        )
        return

    if not is_conversation_member(
        conversation_id,
        current_user.id
    ):
        emit(
            "message_error",
            {
                "error": "You are not a member of this conversation."
            }
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

    for member in members:

        if member.user_id == current_user.id:
            continue

        # Create delivery receipt.
        db.session.add(
            ChatMessageReceipt(
                message_id=message.id,
                recipient_id=member.user_id
            )
        )

        # Create notification.
        db.session.add(
            Notification(
                recipient_id=member.user_id,
                sender_id=current_user.id,
                conversation_id=conversation_id,
                message=(
                    f"{current_user.username} sent you a message."
                )
            )
        )

    # Update latest conversation activity.
    conversation = db.session.get(
        Conversation,
        conversation_id
    )

    conversation.last_message_at = message.created_at

    db.session.commit()

    message_data = get_message_data(message)

    # Send the message to everyone currently inside the chat.
    socketio.emit(
        "new_message",
        message_data,
        to=f"conversation_{conversation_id}"
    )

    # Send notification to other users in the chat room.
    socketio.emit(
        "new_notification",
        {
            "message": (
                f"{current_user.username} sent you a message."
            )
        },
        to=f"conversation_{conversation_id}",
        include_self=False
    )

    # Update every member's conversation list.
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
        emit(
            "message_error",
            {"error": "Please log in again."}
        )
        return

    try:
        message_id = int(data.get("message_id"))
        content = str(data.get("content", "")).strip()

    except (TypeError, ValueError, AttributeError):
        emit(
            "message_error",
            {"error": "Invalid message details."}
        )
        return

    if not content or len(content) > 5000:
        emit(
            "message_error",
            {
                "error": "Message must contain 1–5000 characters."
            }
        )
        return

    message = db.session.get(
        ChatMessage,
        message_id
    )

    if not message:
        emit(
            "message_error",
            {"error": "Message not found."}
        )
        return

    if message.sender_id != current_user.id:
        emit(
            "message_error",
            {
                "error": "You can only edit your own messages."
            }
        )
        return

    if message.is_deleted:
        emit(
            "message_error",
            {
                "error": "Deleted messages cannot be edited."
            }
        )
        return

    if not is_conversation_member(
        message.conversation_id,
        current_user.id
    ):
        emit(
            "message_error",
            {"error": "Access denied."}
        )
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

    # Update sidebar preview if this is the latest message.
    refresh_conversation_preview(
        message.conversation_id,
        current_user.id
    )


# --------------------------------------------------
# DELETE MESSAGE
# --------------------------------------------------

@socketio.on("delete_message")
def delete_message(data):

    if not current_user.is_authenticated:
        emit(
            "message_error",
            {"error": "Please log in again."}
        )
        return

    try:
        message_id = int(data.get("message_id"))

    except (TypeError, ValueError, AttributeError):
        emit(
            "message_error",
            {"error": "Invalid message ID."}
        )
        return

    message = db.session.get(
        ChatMessage,
        message_id
    )

    if not message:
        emit(
            "message_error",
            {"error": "Message not found."}
        )
        return

    if message.sender_id != current_user.id:
        emit(
            "message_error",
            {
                "error": "You can only delete your own messages."
            }
        )
        return

    if not is_conversation_member(
        message.conversation_id,
        current_user.id
    ):
        emit(
            "message_error",
            {"error": "Access denied."}
        )
        return

    if message.is_deleted:
        emit(
            "message_error",
            {"error": "Message is already deleted."}
        )
        return

    message.is_deleted = True
    message.content = "This message was deleted."

    # Keep the attachment stored for now.
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

    # Refresh the conversation list preview.
    refresh_conversation_preview(
        message.conversation_id,
        current_user.id
    )


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

    if not is_conversation_member(
        conversation_id,
        current_user.id
    ):
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
                to=f"conversation_{conversation_id}"
            )


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

    if is_conversation_member(
        conversation_id,
        current_user.id
    ):

        emit(
            "user_typing",
            {
                "username": current_user.username
            },
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

    # Personal room for conversation-list updates.
    join_room(f"user_{user_id}")

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

        # Only mark offline when all connections are disconnected.
        if not active_users[user_id]:

            del active_users[user_id]

            user = db.session.get(
                User,
                user_id
            )

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


# --------------------------------------------------
# SEND ONLINE USERS
# --------------------------------------------------

@socketio.on("request_online_users")
def send_online_users():

    if not current_user.is_authenticated:
        return

    emit(
        "online_users",
        {
            "user_ids": list(active_users.keys())
        }
    )
