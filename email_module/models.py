
from datetime import datetime, timezone

from extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class Email(db.Model):
    __tablename__ = "emails"

    id = db.Column(db.Integer, primary_key=True)

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    subject = db.Column(db.String(255), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")

    folder = db.Column(db.String(20), nullable=False, default="inbox")

    is_read = db.Column(db.Boolean, default=False, nullable=False)
    is_starred = db.Column(db.Boolean, default=False, nullable=False)
    is_important = db.Column(db.Boolean, default=False, nullable=False)

    sent_at = db.Column(db.DateTime(timezone=True), default=utc_now)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    # Sender relationship
    sender = db.relationship(
        "User",
        foreign_keys="Email.sender_id",
        backref="sent_emails"
    )

    # Recipient relationship
    recipient = db.relationship(
        "User",
        foreign_keys="Email.recipient_id",
        backref="received_emails"
    )

    attachments = db.relationship(
        "EmailAttachment",
        backref="email",
        cascade="all, delete-orphan",
        lazy=True
    )


class EmailAttachment(db.Model):
    __tablename__ = "email_attachments"

    id = db.Column(db.Integer, primary_key=True)

    email_id = db.Column(
        db.Integer,
        db.ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)

    uploaded_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now
    )
