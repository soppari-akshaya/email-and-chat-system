
import os

from flask import Flask, redirect, url_for, render_template
from flask_login import current_user,login_required

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

    # --------------------------------------------------
    # CREATE UPLOAD DIRECTORIES
    # --------------------------------------------------

    os.makedirs(
        app.config["UPLOAD_FOLDER"],
        exist_ok=True
    )

    for folder in [
        "email_attachments",
        "chat_attachments",
        "profiles"
    ]:
        os.makedirs(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                folder
            ),
            exist_ok=True
        )

    # --------------------------------------------------
    # INITIALIZE FLASK EXTENSIONS
    # --------------------------------------------------

    db.init_app(app)
    login_manager.init_app(app)
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

    from email_module.models import (
        Email,
        EmailAttachment
    )

    from chat_module.models import (
        Conversation,
        ConversationMember,
        ChatMessage
    )

    from notification_module.models import Notification

    # --------------------------------------------------
    # REGISTER BLUEPRINTS
    # --------------------------------------------------

    # Authentication
    from auth_module import auth_bp
    app.register_blueprint(auth_bp)

    # Email
    from email_module import email_bp
    app.register_blueprint(email_bp)

    # Chat
    from chat_module import chat_bp
    app.register_blueprint(chat_bp)

    # Notifications
    from notification_module import notification_bp
    app.register_blueprint(notification_bp)

    # --------------------------------------------------
    # REGISTER SOCKET.IO EVENTS
    # --------------------------------------------------

    import chat_module.events

    # --------------------------------------------------
    # HOME PAGE
    # --------------------------------------------------

    @app.route("/")
    def home():

        if current_user.is_authenticated:
            return redirect(
                url_for("dashboard")
            )

        return redirect(
            url_for("auth.login")
        )

    # --------------------------------------------------
    # DASHBOARD
    # --------------------------------------------------

    
    # Dashboard
    @app.route("/dashboard")
    @login_required
    def dashboard():

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

            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">

            <style>
                * {{
                    box-sizing: border-box;
                }}

                body {{
                    margin: 0;
                    background: #f7f6fd;
                    font-family: "Segoe UI", Arial, sans-serif;
                    color: #302b50;
                }}

                .main-container {{
                    max-width: 1250px;
                    margin: auto;
                    padding: 25px 35px;
                }}

                .topbar {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 35px;
                }}

                .brand {{
                    font-size: 25px;
                    font-weight: 750;
                    color: #302b50;
                }}

                .profile-area {{
                    display: flex;
                    align-items: center;
                    gap: 18px;
                }}

                .notification-link {{
                    position: relative;
                    color: #6254c7;
                    font-size: 23px;
                    text-decoration: none;
                    padding: 8px;
                }}

                .notification-badge {{
                    position: absolute;
                    top: 0;
                    right: -2px;
                    background: #ef476f;
                    color: white;
                    font-size: 10px;
                    min-width: 18px;
                    height: 18px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}

                .profile {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    background: white;
                    border: 1px solid #eeecf5;
                    border-radius: 30px;
                    padding: 9px 16px;
                    color: #6254a3;
                    font-size: 13px;
                }}

                .profile-icon {{
                    width: 34px;
                    height: 34px;
                    border-radius: 50%;
                    background: #7969dc;
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                }}

                .welcome {{
                    background: linear-gradient(110deg, #7665d9, #9989ed);
                    color: white;
                    padding: 38px;
                    border-radius: 22px;
                    margin-bottom: 35px;
                    box-shadow: 0 10px 25px rgba(100, 80, 190, 0.12);
                }}

                .welcome h1 {{
                    font-size: 30px;
                    font-weight: 750;
                    margin-bottom: 10px;
                }}

                .welcome p {{
                    margin: 0;
                    font-size: 14px;
                    opacity: 0.95;
                }}

                .section-heading {{
                    font-size: 19px;
                    font-weight: 700;
                    margin-bottom: 18px;
                }}

                .workspace-card {{
                    background: white;
                    border: 1px solid #eeecf5;
                    border-radius: 20px;
                    padding: 28px;
                    min-height: 205px;
                    height: 100%;
                    text-decoration: none;
                    color: inherit;
                    display: block;
                    transition: 0.2s ease;
                }}

                .workspace-card:hover {{
                    transform: translateY(-4px);
                    border-color: #c9bfff;
                    box-shadow: 0 10px 25px rgba(80, 65, 140, 0.09);
                    color: inherit;
                }}

                .workspace-icon {{
                    width: 55px;
                    height: 55px;
                    border-radius: 16px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 25px;
                    margin-bottom: 20px;
                }}

                .email-icon {{
                    background: #efedff;
                    color: #7665d9;
                }}

                .chat-icon {{
                    background: #e5f7f2;
                    color: #229d82;
                }}

                .workspace-card h5 {{
                    font-weight: 700;
                    font-size: 17px;
                    margin-bottom: 9px;
                }}

                .workspace-card p {{
                    color: #89869f;
                    font-size: 13px;
                    line-height: 1.7;
                    margin-bottom: 0;
                }}

                .footer {{
                    text-align: center;
                    color: #9994b0;
                    font-size: 12px;
                    margin-top: 50px;
                }}

                .logout-link {{
                    color: #7665d9;
                    text-decoration: none;
                    font-size: 13px;
                    margin-left: 12px;
                }}

                @media (max-width: 600px) {{
                    .main-container {{
                        padding: 18px;
                    }}

                    .welcome {{
                        padding: 27px 22px;
                    }}

                    .welcome h1 {{
                        font-size: 24px;
                    }}

                    .profile {{
                        padding: 7px;
                    }}

                    .profile-email {{
                        display: none;
                    }}

                    .topbar {{
                        margin-bottom: 25px;
                    }}
                }}
            </style>
        </head>

        <body>

            <div class="main-container">

                <header class="topbar">

                    <div class="brand">
                        <i class="bi bi-chat-square-heart-fill me-2"
                           style="color:#7665d9;"></i>
                        ConnectHub
                    </div>

                    <div class="profile-area">

                        <a href="/notifications/"
                           class="notification-link"
                           title="Notifications">

                            <i class="bi bi-bell-fill"></i>

                            {f'<span class="notification-badge">{unread_notifications}</span>' if unread_notifications > 0 else ''}

                        </a>

                        <div class="profile">

                            <div class="profile-icon">
                                {current_user.username[0].upper()}
                            </div>

                            <span class="profile-email">
                                {current_user.email}
                            </span>

                        </div>

                        <a href="/auth/logout"
                           class="logout-link"
                           title="Logout">
                            <i class="bi bi-box-arrow-right"></i>
                        </a>

                    </div>

                </header>

                <section class="welcome">

                    <h1>Welcome back, {current_user.username}!</h1>

                    <p>
                        Your Email and Real-Time Chat Application.
                        Stay connected with everyone in one place.
                    </p>

                </section>

                <h5 class="section-heading">Your Workspaces</h5>

                <div class="row g-4">

                    <div class="col-md-6">

                        <a href="/email/" class="workspace-card">

                            <div class="workspace-icon email-icon">
                                <i class="bi bi-envelope-fill"></i>
                            </div>

                            <h5>Email Management</h5>

                            <p>
                                Send and receive emails, manage your inbox,
                                organize drafts and access important messages.
                            </p>

                        </a>

                    </div>

                    <div class="col-md-6">

                        <a href="/chat/" class="workspace-card">

                            <div class="workspace-icon chat-icon">
                                <i class="bi bi-chat-dots-fill"></i>
                            </div>

                            <h5>Real-Time Chat</h5>

                            <p>
                                Start private conversations, create groups,
                                share files and communicate in real time.
                            </p>

                        </a>

                    </div>

                </div>

                <div class="footer">
                    ConnectHub · Your communication workspace
                </div>

            </div>

        </body>
        </html>
        """



    # --------------------------------------------------
    # CREATE DATABASE TABLES
    # --------------------------------------------------

    with app.app_context():
        db.create_all()

    return app


# --------------------------------------------------
# CREATE FLASK APPLICATION
# --------------------------------------------------

app = create_app()


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True
    )
