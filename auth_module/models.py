from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db, login_manager


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), default="user", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)
    last_seen = db.Column(db.DateTime(timezone=True), nullable=True)
    online_status = db.Column(db.String(20), default="offline", nullable=False)

    profile = db.relationship(
        "UserProfile",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    @property
    def is_online(self):
        return self.online_status == "online"

    @property
    def profile_image_url(self):
        if self.profile and self.profile.profile_image:
            return f"/auth/profile-image/{self.id}"
        return None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


class UserProfile(db.Model):
    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )

    full_name = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.String(300), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    profile_image = db.Column(db.String(255), nullable=True)
    notification_preferences = db.Column(db.String(255), default="email,chat,sound", nullable=True)

    # Granular Persistent Notification Settings
    desktop_notifications_enabled = db.Column(db.Boolean, default=True, nullable=True)
    email_notifications_enabled = db.Column(db.Boolean, default=True, nullable=True)
    private_chat_notifications_enabled = db.Column(db.Boolean, default=True, nullable=True)
    group_chat_notifications_enabled = db.Column(db.Boolean, default=True, nullable=True)
    sound_enabled = db.Column(db.Boolean, default=True, nullable=True)

    # Google Authentication UID Linking
    google_id = db.Column(db.String(128), nullable=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    def wants_desktop_notifs(self):
        return self.desktop_notifications_enabled is not False

    def wants_email_notifs(self):
        return self.email_notifications_enabled is not False

    def wants_chat_notifs(self):
        return self.private_chat_notifications_enabled is not False

    def wants_group_notifs(self):
        return self.group_chat_notifications_enabled is not False

    def wants_sound(self):
        return self.sound_enabled is not False

    def get_notification_preferences_list(self):
        prefs = []
        if self.desktop_notifications_enabled is not False:
            prefs.append("desktop")
        if self.email_notifications_enabled is not False:
            prefs.append("email")
        if self.private_chat_notifications_enabled is not False:
            prefs.append("private_chat")
        if self.group_chat_notifications_enabled is not False:
            prefs.append("group_chat")
        if self.sound_enabled is not False:
            prefs.append("sound")
        return prefs

    def set_notification_preferences(self, prefs_list):
        if isinstance(prefs_list, str):
            prefs_list = [p.strip() for p in prefs_list.split(",") if p.strip()]
        prefs_set = set(prefs_list or [])
        self.desktop_notifications_enabled = ("desktop" in prefs_set or "desktop_notifications" in prefs_set)
        self.email_notifications_enabled = ("email" in prefs_set or "email_notifications" in prefs_set)
        self.private_chat_notifications_enabled = ("private_chat" in prefs_set or "chat" in prefs_set)
        self.group_chat_notifications_enabled = ("group_chat" in prefs_set or "chat" in prefs_set)
        self.sound_enabled = ("sound" in prefs_set or "sound_enabled" in prefs_set)
        self.notification_preferences = ",".join(self.get_notification_preferences_list())


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
