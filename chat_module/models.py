
from datetime import datetime, timezone
from extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)

    is_group = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    name = db.Column(db.String(100), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now
    )

    # Updated whenever a new message is sent.
    # Used to display the latest active conversation first.
    last_message_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=True,
        index=True
    )

    members = db.relationship(
        "ConversationMember",
        backref="conversation",
        cascade="all, delete-orphan"
    )

    messages = db.relationship(
        "ChatMessage",
        backref="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )


class ConversationMember(db.Model):
    __tablename__ = "conversation_members"

    id = db.Column(db.Integer, primary_key=True)

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    joined_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now
    )

    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint(
            "conversation_id",
            "user_id",
            name="unique_conversation_member"
        ),
    )


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now
    )

    # Attachment support
    attachment_name = db.Column(
        db.String(255),
        nullable=True
    )

    attachment_path = db.Column(
        db.String(500),
        nullable=True
    )

    attachment_mimetype = db.Column(
        db.String(150),
        nullable=True
    )

    attachment_size = db.Column(
        db.Integer,
        nullable=True
    )

    # Message editing support
    is_edited = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    edited_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    # Message deletion support
    is_deleted = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    sender = db.relationship("User")

    receipts = db.relationship(
        "ChatMessageReceipt",
        backref="chat_message",
        cascade="all, delete-orphan",
        lazy=True
    )


class ChatMessageReceipt(db.Model):
    __tablename__ = "chat_message_receipts"

    id = db.Column(db.Integer, primary_key=True)

    message_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    delivered_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    read_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    recipient = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint(
            "message_id",
            "recipient_id",
            name="unique_message_recipient_receipt"
        ),
    )
