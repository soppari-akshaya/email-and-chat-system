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
    label = db.Column(db.String(50), nullable=True, default=None)

    sent_at = db.Column(db.DateTime(timezone=True), default=utc_now)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    @property
    def created_at_iso(self):
        if self.created_at is None:
            return ""
        if self.created_at.tzinfo is None:
            dt = self.created_at.replace(tzinfo=timezone.utc)
        else:
            dt = self.created_at.astimezone(timezone.utc)
        return dt.isoformat()

    @property
    def sent_at_iso(self):
        target = self.sent_at or self.created_at
        if target is None:
            return ""
        if target.tzinfo is None:
            dt = target.replace(tzinfo=timezone.utc)
        else:
            dt = target.astimezone(timezone.utc)
        return dt.isoformat()

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
    mimetype = db.Column(db.String(150), nullable=True, default="application/octet-stream")

    uploaded_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now
    )
