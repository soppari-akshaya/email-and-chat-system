from datetime import datetime, timezone
from extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True
    )

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True
    )

    message = db.Column(db.String(255), nullable=False)

    is_read = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    @property
    def created_at_iso(self):
        if self.created_at is None:
            return ""
        if self.created_at.tzinfo is None:
            dt = self.created_at.replace(tzinfo=timezone.utc)
        else:
            dt = self.created_at.astimezone(timezone.utc)
        return dt.isoformat()

    sender = db.relationship("User", foreign_keys=[sender_id])


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    endpoint = db.Column(db.Text, nullable=False, unique=True, index=True)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    @property
    def created_at_iso(self):
        if self.created_at is None:
            return ""
        if self.created_at.tzinfo is None:
            dt = self.created_at.replace(tzinfo=timezone.utc)
        else:
            dt = self.created_at.astimezone(timezone.utc)
        return dt.isoformat()

    user = db.relationship("User", backref=db.backref("push_subscriptions", cascade="all, delete-orphan", lazy="dynamic"))
