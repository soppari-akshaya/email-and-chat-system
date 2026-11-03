import os
import sqlite3
from datetime import datetime, timezone
from flask import Flask, redirect, url_for, render_template, send_from_directory, make_response
from flask_login import current_user, login_required
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config
from extensions import (
    db,
    login_manager,
    socketio,
    csrf,
    migrate,
    limiter
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce WAL mode and busy timeout for high-concurrency SQLite operations."""
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def ensure_db_schema(app):
    """Safely apply schema migrations for new columns without data loss across SQLite and PostgreSQL."""
    if app.config.get("TESTING"):
        return

    try:
        from sqlalchemy import inspect, text

        engine = db.engine
        dialect_name = engine.dialect.name
        is_pg = (dialect_name == "postgresql")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        # 1. user_profiles
        if "user_profiles" in tables:
            up_cols = {c["name"] for c in inspector.get_columns("user_profiles")}
            with engine.begin() as conn:
                if is_pg:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS desktop_notifications_enabled BOOLEAN DEFAULT TRUE;"))
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS email_notifications_enabled BOOLEAN DEFAULT TRUE;"))
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS private_chat_notifications_enabled BOOLEAN DEFAULT TRUE;"))
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS group_chat_notifications_enabled BOOLEAN DEFAULT TRUE;"))
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS sound_enabled BOOLEAN DEFAULT TRUE;"))
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS google_id VARCHAR(128);"))
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS notification_preferences VARCHAR(255) DEFAULT 'email,chat,sound';"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_profiles_google_id ON user_profiles (google_id);"))
                    conn.execute(text("UPDATE user_profiles SET desktop_notifications_enabled = TRUE WHERE desktop_notifications_enabled IS NULL;"))
                    conn.execute(text("UPDATE user_profiles SET email_notifications_enabled = TRUE WHERE email_notifications_enabled IS NULL;"))
                    conn.execute(text("UPDATE user_profiles SET private_chat_notifications_enabled = TRUE WHERE private_chat_notifications_enabled IS NULL;"))
                    conn.execute(text("UPDATE user_profiles SET group_chat_notifications_enabled = TRUE WHERE group_chat_notifications_enabled IS NULL;"))
                    conn.execute(text("UPDATE user_profiles SET sound_enabled = TRUE WHERE sound_enabled IS NULL;"))
                    conn.execute(text("UPDATE user_profiles SET notification_preferences = 'email,chat,sound' WHERE notification_preferences IS NULL;"))
                else:
                    if "desktop_notifications_enabled" not in up_cols:
                        conn.execute(text("ALTER TABLE user_profiles ADD COLUMN desktop_notifications_enabled BOOLEAN DEFAULT 1;"))
                    if "email_notifications_enabled" not in up_cols:
                        conn.execute(text("ALTER TABLE user_profiles ADD COLUMN email_notifications_enabled BOOLEAN DEFAULT 1;"))
                    if "private_chat_notifications_enabled" not in up_cols:
                        conn.execute(text("ALTER TABLE user_profiles ADD COLUMN private_chat_notifications_enabled BOOLEAN DEFAULT 1;"))
                    if "group_chat_notifications_enabled" not in up_cols:
                        conn.execute(text("ALTER TABLE user_profiles ADD COLUMN group_chat_notifications_enabled BOOLEAN DEFAULT 1;"))
                    if "sound_enabled" not in up_cols:
                        conn.execute(text("ALTER TABLE user_profiles ADD COLUMN sound_enabled BOOLEAN DEFAULT 1;"))
                    if "google_id" not in up_cols:
                        conn.execute(text("ALTER TABLE user_profiles ADD COLUMN google_id VARCHAR(128);"))
                    if "notification_preferences" not in up_cols:
                        conn.execute(text("ALTER TABLE user_profiles ADD COLUMN notification_preferences VARCHAR(255) DEFAULT 'email,chat,sound';"))

        # 2. users
        if "users" in tables:
            with engine.begin() as conn:
                if is_pg:
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS online_status VARCHAR(20) DEFAULT 'offline';"))
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP WITH TIME ZONE;"))

        # 3. conversations
        if "conversations" in tables:
            with engine.begin() as conn:
                if is_pg:
                    conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMP WITH TIME ZONE;"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at ON conversations (last_message_at);"))

        # 4. emails
        if "emails" in tables:
            em_cols = {c["name"] for c in inspector.get_columns("emails")}
            with engine.begin() as conn:
                if is_pg:
                    conn.execute(text("ALTER TABLE emails ADD COLUMN IF NOT EXISTS label VARCHAR(50);"))
                else:
                    if "label" not in em_cols:
                        conn.execute(text("ALTER TABLE emails ADD COLUMN label VARCHAR(50);"))

        # 5. chat_messages
        if "chat_messages" in tables:
            cm_cols = {c["name"] for c in inspector.get_columns("chat_messages")}
            with engine.begin() as conn:
                if is_pg:
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reply_to_id INTEGER;"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(20) DEFAULT 'sent';"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP WITH TIME ZONE;"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS seen_at TIMESTAMP WITH TIME ZONE;"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE;"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP WITH TIME ZONE;"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_name VARCHAR(255);"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_path VARCHAR(500);"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_mimetype VARCHAR(150);"))
                    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_size INTEGER;"))
                else:
                    if "reply_to_id" not in cm_cols:
                        conn.execute(text("ALTER TABLE chat_messages ADD COLUMN reply_to_id INTEGER;"))

        # 6. email_attachments
        if "email_attachments" in tables:
            ea_cols = {c["name"] for c in inspector.get_columns("email_attachments")}
            with engine.begin() as conn:
                if is_pg:
                    conn.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS mimetype VARCHAR(150) DEFAULT 'application/octet-stream';"))
                else:
                    if "mimetype" not in ea_cols:
                        conn.execute(text("ALTER TABLE email_attachments ADD COLUMN mimetype VARCHAR(150) DEFAULT 'application/octet-stream';"))

        # 7. push_subscriptions
        if is_pg and "push_subscriptions" not in tables:
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS push_subscriptions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        endpoint TEXT NOT NULL UNIQUE,
                        p256dh VARCHAR(255) NOT NULL,
                        auth VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_push_subscriptions_endpoint ON push_subscriptions (endpoint);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id ON push_subscriptions (user_id);"))

    except Exception as e:
        app.logger.warning(f"Schema check error: {e}")


def create_app(config_class=Config, test_config=None):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Cloudflare Reverse Proxy Header handling
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    if test_config:
        app.config.update(test_config)

    
    # CREATE UPLOAD DIRECTORIES
    
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    for folder in ["email_attachments", "chat_attachments", "profiles"]:
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], folder), exist_ok=True)

    
    # INITIALIZE FLASK EXTENSIONS
    
    db.init_app(app)
    login_manager.init_app(app)

    # Register Socket.IO events before initializing app so handlers are retained
    import chat_module.events

    socketio.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in first."
    login_manager.login_message_category = "warning"

    
    # IMPORT DATABASE MODELS
    
    from auth_module.models import User, UserProfile
    from email_module.models import Email, EmailAttachment
    from chat_module.models import Conversation, ConversationMember, ChatMessage
    from notification_module.models import Notification, PushSubscription

    
    # REGISTER BLUEPRINTS
    
    from auth_module import auth_bp
    app.register_blueprint(auth_bp)

    from email_module import email_bp
    app.register_blueprint(email_bp)

    from chat_module import chat_bp
    app.register_blueprint(chat_bp)

    from notification_module import notification_bp
    app.register_blueprint(notification_bp)

    from admin_module import admin_bp
    app.register_blueprint(admin_bp)

    
    # REGISTER SOCKET.IO EVENTS
    
    import chat_module.events

    
    # CONTEXT PROCESSORS (GLOBAL TEMPLATE VARIABLES)
    
    @app.context_processor
    def inject_global_data():
        if current_user.is_authenticated:
            unread_notifs = Notification.query.filter_by(
                recipient_id=current_user.id,
                is_read=False
            ).count()

            unread_emails = Email.query.filter_by(
                recipient_id=current_user.id,
                folder="inbox",
                is_read=False
            ).count()

            return {
                "unread_notifications": unread_notifs,
                "unread_emails": unread_emails,
                "is_admin": current_user.role == "admin"
            }
        return {
            "unread_notifications": 0,
            "unread_emails": 0,
            "is_admin": False
        }

    
    # ROUTES
    
    @app.after_request
    def set_security_headers(response):
        # Allow cross-origin popup opener communication for Google/Firebase authentication
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
        return response

    @app.route("/google-login", methods=["POST"])
    def root_google_login():
        from auth_module.routes import google_login
        return google_login()

    @app.route("/sw.js")
    def service_worker():
        response = make_response(send_from_directory(os.path.join(app.root_path, "static"), "sw.js"))
        response.headers["Content-Type"] = "application/javascript"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        try:
            unread_notifications = Notification.query.filter_by(
                recipient_id=current_user.id,
                is_read=False
            ).count()
        except Exception as e:
            app.logger.warning(f"Error fetching unread notifications: {e}")
            unread_notifications = 0

        try:
            unread_emails = Email.query.filter_by(
                recipient_id=current_user.id,
                folder="inbox",
                is_read=False
            ).count()
        except Exception as e:
            app.logger.warning(f"Error fetching unread emails: {e}")
            unread_emails = 0

        try:
            sent_emails_count = Email.query.filter_by(
                sender_id=current_user.id,
                folder="sent"
            ).count()
        except Exception as e:
            app.logger.warning(f"Error fetching sent emails count: {e}")
            sent_emails_count = 0

        try:
            memberships = ConversationMember.query.filter_by(
                user_id=current_user.id
            ).all()
            active_chats_count = len(memberships)
        except Exception as e:
            app.logger.warning(f"Error fetching memberships: {e}")
            memberships = []
            active_chats_count = 0

        try:
            recent_emails = Email.query.filter_by(
                recipient_id=current_user.id,
                folder="inbox"
            ).order_by(Email.created_at.desc()).limit(5).all()
        except Exception as e:
            app.logger.warning(f"Error fetching recent emails: {e}")
            recent_emails = []

        try:
            recent_conversations = [
                m.conversation for m in memberships if m.conversation is not None
            ]

            def get_conv_timestamp(conv):
                if not conv:
                    return datetime.min.replace(tzinfo=timezone.utc)
                val = conv.last_message_at or conv.created_at
                if not val:
                    return datetime.min.replace(tzinfo=timezone.utc)
                if getattr(val, "tzinfo", None) is None:
                    return val.replace(tzinfo=timezone.utc)
                return val.astimezone(timezone.utc)

            recent_conversations.sort(key=get_conv_timestamp, reverse=True)
            recent_conversations = recent_conversations[:5]
        except Exception as e:
            app.logger.warning(f"Error sorting recent conversations: {e}")
            recent_conversations = []

        return render_template(
            "dashboard.html",
            unread_notifications=unread_notifications,
            unread_emails=unread_emails,
            sent_emails_count=sent_emails_count,
            active_chats_count=active_chats_count,
            recent_emails=recent_emails,
            recent_conversations=recent_conversations,
            username=current_user.username or "User",
            email=current_user.email or ""
        )

    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        import traceback
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        tb = traceback.format_exc()
        app.logger.error(f"Unhandled Exception: {tb}")
        from flask import request
        if request.args.get("show_error") == "1":
            return f"<h1>Server Error (500)</h1><pre>{tb}</pre>", 500
        return f"<h1>Internal Server Error</h1><pre style='display:none'>{tb}</pre>", 500

    
    # CREATE DATABASE TABLES AND RUN AUTO-MIGRATION
    
    with app.app_context():
        db.create_all()
        ensure_db_schema(app)

        try:
            admin = User.query.filter_by(email="admin@connecthub.com").first()
            if not admin:
                admin = User(
                    username="admin",
                    email="admin@connecthub.com",
                    role="admin",
                    is_active=True,
                    is_verified=True,
                    online_status="offline"
                )
                admin.set_password("AdminPass123!")
                admin.profile = UserProfile(
                    full_name="System Administrator",
                    bio="ConnectHub Platform Administrator"
                )
                db.session.add(admin)
                db.session.commit()
            elif admin.role != "admin":
                admin.role = "admin"
                db.session.commit()
        except Exception as e:
            app.logger.warning(f"Admin init warning: {e}")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True
    )
