 
import os

from flask import Flask, redirect, url_for
from flask_login import current_user

from config import Config
from extensions import (
    db,
    login_manager,
    socketio,
    csrf,
    migrate,
    limiter
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Create upload directories
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    for folder in [
        "email_attachments",
        "chat_attachments",
        "profiles"
    ]:
        os.makedirs(
            os.path.join(app.config["UPLOAD_FOLDER"], folder),
            exist_ok=True
        )

    # Initialize Flask extensions
    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in first."
    login_manager.login_message_category = "warning"

    # Import authentication models
    from auth_module.models import User, UserProfile

    # Import email models
    from email_module.models import Email, EmailAttachment

    # Import chat models
    from chat_module.models import (
        Conversation,
        ConversationMember,
        ChatMessage
    )

    # Import notification models
    from notification_module.models import Notification

    # Register authentication module
    from auth_module import auth_bp
    app.register_blueprint(auth_bp)

    # Register email module
    from email_module import email_bp
    app.register_blueprint(email_bp)

    # Register chat module
    from chat_module import chat_bp
    app.register_blueprint(chat_bp)

    # Register notification module
    from notification_module import notification_bp
    app.register_blueprint(notification_bp)

    # Register real-time Socket.IO events
    import chat_module.events

    # Home page
    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        return redirect(url_for("auth.login"))

    # Dashboard
    @app.route("/dashboard")
    def dashboard():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        # Get unread notification count
        unread_notifications = Notification.query.filter_by(
            recipient_id=current_user.id,
            is_read=False
        ).count()

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">

            <title>ConnectHub Dashboard</title>

            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
                  rel="stylesheet">

            <style>
                body {{
                    background: #f1f5f9;
                    font-family: Arial, sans-serif;
                }}

                .dashboard-card {{
                    background: white;
                    border-radius: 15px;
                    padding: 30px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.06);
                }}

                .section-title {{
                    font-weight: 600;
                    margin-bottom: 15px;
                }}

                .feature-button {{
                    min-width: 130px;
                }}

                .notification-button {{
                    position: relative;
                }}

                .notification-badge {{
                    position: absolute;
                    top: -10px;
                    right: -10px;
                    background: #dc3545;
                    color: white;
                    border-radius: 50px;
                    min-width: 23px;
                    height: 23px;
                    padding: 2px 6px;
                    font-size: 12px;
                    font-weight: bold;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
            </style>
        </head>

        <body>

            <div class="container py-5">

                <div class="dashboard-card">

                    <h1>Welcome to ConnectHub, {current_user.username}!</h1>

                    <p class="text-muted">
                        Your Email and Real-Time Chat Application
                    </p>

                    <hr>

                    <h5 class="section-title">Email Management</h5>

                    <div class="d-flex flex-wrap gap-2 mb-4">

                        <a href="/email/"
                           class="btn btn-primary feature-button">
                            Inbox
                        </a>

                        <a href="/email/sent"
                           class="btn btn-secondary feature-button">
                            Sent
                        </a>

                        <a href="/email/drafts"
                           class="btn btn-info feature-button">
                            Drafts
                        </a>

                        <a href="/email/compose"
                           class="btn btn-success feature-button">
                            Compose Email
                        </a>

                        <a href="/email/trash"
                           class="btn btn-danger feature-button">
                            Trash
                        </a>

                        <a href="/email/starred"
                           class="btn btn-warning feature-button">
                            Starred
                        </a>

                        <a href="/email/important"
                           class="btn btn-dark feature-button">
                            Important
                        </a>

                    </div>

                    <hr>

                    <h5 class="section-title">Chat Management</h5>

                    <div class="d-flex flex-wrap gap-2 mb-4">

                        <a href="/chat/"
                           class="btn btn-dark feature-button">
                            Open Chat
                        </a>

                    </div>

                    <hr>

                    <h5 class="section-title">Notifications</h5>

                    <div class="d-flex flex-wrap gap-2 mb-4">

                        <a href="/notifications/"
                           class="btn btn-warning feature-button notification-button">
                            <span>Notifications</span>

                            {f'<span class="notification-badge">{unread_notifications}</span>' if unread_notifications > 0 else ''}

                        </a>

                    </div>

                    <hr>

                    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">

                        <span class="text-muted">
                            Logged in as {current_user.email}
                        </span>

                        <a href="/auth/logout"
                           class="btn btn-outline-danger">
                            Logout
                        </a>

                    </div>

                </div>

            </div>

        </body>
        </html>
        """

    # Create database tables
    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True
    )
