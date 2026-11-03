import os
import sqlite3
from flask import Flask, redirect, url_for, render_template
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
    """Safely apply schema migrations for new columns without data loss."""
    if app.config.get("TESTING"):
        return

    if not app.config.get("SQLALCHEMY_DATABASE_URI", "").startswith("sqlite"):
        return

    db_path = os.path.join(os.path.dirname(__file__), "application.db")
    if not os.path.exists(db_path):
        return

    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()

        def add_col_if_missing(table, col, col_def):
            cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

        add_col_if_missing("emails", "label", "VARCHAR(50)")
        add_col_if_missing("chat_messages", "reply_to_id", "INTEGER")
        add_col_if_missing("user_profiles", "notification_preferences", "VARCHAR(255) DEFAULT 'email,chat,sound'")
        add_col_if_missing("email_attachments", "mimetype", "VARCHAR(150) DEFAULT 'application/octet-stream'")

        con.commit()
        con.close()
    except Exception as e:
        app.logger.warning(f"Schema check error: {e}")


def create_app(config_class=Config, test_config=None):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Cloudflare Reverse Proxy Header handling
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    if test_config:
        app.config.update(test_config)

    # --------------------------------------------------
    # CREATE UPLOAD DIRECTORIES
    # --------------------------------------------------
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    for folder in ["email_attachments", "chat_attachments", "profiles"]:
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], folder), exist_ok=True)

    # --------------------------------------------------
    # INITIALIZE FLASK EXTENSIONS
    # --------------------------------------------------
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

    # --------------------------------------------------
    # IMPORT DATABASE MODELS
    # --------------------------------------------------
    from auth_module.models import User, UserProfile
    from email_module.models import Email, EmailAttachment
    from chat_module.models import Conversation, ConversationMember, ChatMessage
    from notification_module.models import Notification

    # --------------------------------------------------
    # REGISTER BLUEPRINTS
    # --------------------------------------------------
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

    # --------------------------------------------------
    # REGISTER SOCKET.IO EVENTS
    # --------------------------------------------------
    import chat_module.events

    # --------------------------------------------------
    # CONTEXT PROCESSORS (GLOBAL TEMPLATE VARIABLES)
    # --------------------------------------------------
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

    # --------------------------------------------------
    # ROUTES
    # --------------------------------------------------
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
            from datetime import timezone
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

    # --------------------------------------------------
    # CREATE DATABASE TABLES AND RUN AUTO-MIGRATION
    # --------------------------------------------------
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
