import pytest
from app import create_app
from extensions import db
from auth_module.models import User, UserProfile
from notification_module.models import PushSubscription, Notification
from email_module.models import Email

@pytest.fixture
def test_client():
    app = create_app(test_config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret"
    })
    with app.app_context():
        db.create_all()
        yield app.test_client()

def test_routes_exist(test_client):
    # Test forgot password GET
    res = test_client.get("/auth/forgot-password")
    assert res.status_code == 200
    assert b"Reset Password" in res.data or b"Forgot Password" in res.data

    # Test firebase config endpoint with user credentials
    res = test_client.get("/auth/firebase-config")
    assert res.status_code == 200
    data = res.get_json()
    assert data["apiKey"] == "AIzaSyCkBsSv7BacOOHT7d68Zsh7t2GgizziHvk"
    assert data["authDomain"] == "email-and-chat-system.firebaseapp.com"
    assert data["projectId"] == "email-and-chat-system"
    assert data["storageBucket"] == "email-and-chat-system.firebasestorage.app"
    assert data["messagingSenderId"] == "511432167350"
    assert data["appId"] == "1:511432167350:web:1d4cfe1ae26f7ee9133b17"
    assert data["measurementId"] == "G-3V04PXS0Y6"

    # Verify theme-switching controls are removed from login, register, and forgot password pages
    res_login = test_client.get("/auth/login")
    assert res_login.status_code == 200
    assert b"themeToggleBtn" not in res_login.data
    assert b"theme.js" not in res_login.data

    res_reg = test_client.get("/auth/register")
    assert res_reg.status_code == 200
    assert b"themeToggleBtn" not in res_reg.data
    assert b"theme.js" not in res_reg.data

    res_forgot = test_client.get("/auth/forgot-password")
    assert res_forgot.status_code == 200
    assert b"themeToggleBtn" not in res_forgot.data
    assert b"theme.js" not in res_forgot.data

    # Test vapid public key endpoint
    res = test_client.get("/notifications/vapid-public-key")
    assert res.status_code == 200
    vapid_data = res.get_json()
    assert "publicKey" in vapid_data

    # Test Service Worker route
    res = test_client.get("/sw.js")
    assert res.status_code == 200
    assert b"ConnectHub Service Worker" in res.data
    assert res.headers.get("Service-Worker-Allowed") == "/"

def test_google_login_flow(test_client, monkeypatch):
    # 1. Missing token
    res = test_client.post("/auth/google-login", json={})
    assert res.status_code == 400
    assert res.get_json()["success"] is False

    # 2. Invalid token
    monkeypatch.setattr("auth_module.firebase_service.verify_firebase_id_token", lambda tok: None)
    res = test_client.post("/auth/google-login", json={"id_token": "invalid-token-123"})
    assert res.status_code == 401
    assert res.get_json()["success"] is False

    # 3. Valid token for a new Google user
    mock_user_info = {
        "uid": "google-uid-test-12345",
        "email": "testgoogleuser@gmail.com",
        "name": "Test Google User",
        "picture": "https://lh3.googleusercontent.com/test",
        "email_verified": True
    }
    monkeypatch.setattr("auth_module.firebase_service.verify_firebase_id_token", lambda tok: mock_user_info)

    res = test_client.post("/auth/google-login", json={"id_token": "valid-google-id-token"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["redirect_url"] == "/dashboard"

    # Verify user exists in database
    user = User.query.filter_by(email="testgoogleuser@gmail.com").first()
    assert user is not None
    assert user.is_active is True
    assert user.profile.google_id == "google-uid-test-12345"

    # 4. Existing Google user login (should not create duplicate user)
    res_existing = test_client.post("/auth/google-login", json={"idToken": "valid-google-id-token"})
    assert res_existing.status_code == 200
    assert res_existing.get_json()["success"] is True

    # Count of users with this email must still be 1
    users = User.query.filter_by(email="testgoogleuser@gmail.com").all()
    assert len(users) == 1

    # 5. Root /google-login endpoint works identically
    res_root = test_client.post("/google-login", json={"id_token": "valid-google-id-token"})
    assert res_root.status_code == 200
    assert res_root.get_json()["success"] is True

    # 6. Authorization header format
    res_auth_header = test_client.post("/auth/google-login", headers={"Authorization": "Bearer valid-google-id-token"})
    assert res_auth_header.status_code == 200
    assert res_auth_header.get_json()["success"] is True

    # 7. Check Cross-Origin-Opener-Policy response header
    res_login_page = test_client.get("/auth/login")
    assert res_login_page.headers.get("Cross-Origin-Opener-Policy") == "same-origin-allow-popups"

    # 8. Inactive user rejection
    user = User.query.filter_by(email="testgoogleuser@gmail.com").first()
    user.is_active = False
    db.session.commit()

    res_inactive = test_client.post("/auth/google-login", json={"id_token": "valid-google-id-token"})
    assert res_inactive.status_code == 403
    assert res_inactive.get_json()["success"] is False

def test_push_subscription_model():
    sub = PushSubscription(
        user_id=1,
        endpoint="https://fcm.googleapis.com/fcm/send/test123",
        p256dh="testp256dhkey",
        auth="testauthkey"
    )
    assert sub.endpoint == "https://fcm.googleapis.com/fcm/send/test123"
    assert sub.p256dh == "testp256dhkey"
    assert sub.auth == "testauthkey"

def test_user_profile_notification_flags():
    profile = UserProfile(
        desktop_notifications_enabled=True,
        email_notifications_enabled=True,
        private_chat_notifications_enabled=True,
        group_chat_notifications_enabled=False,
        sound_enabled=True
    )
    prefs = profile.get_notification_preferences_list()
    assert "desktop" in prefs
    assert "email" in prefs
    assert "private_chat" in prefs
    assert "sound" in prefs
    assert "group_chat" not in prefs

    profile.set_notification_preferences(["desktop", "group_chat"])
    assert profile.desktop_notifications_enabled is True
    assert profile.group_chat_notifications_enabled is True
    assert profile.email_notifications_enabled is False
    assert profile.sound_enabled is False

def test_theme_toggle_single_top_header(test_client):
    # 1. theme.js asset is served
    res_js = test_client.get("/static/js/theme.js")
    assert res_js.status_code == 200
    assert b"connecthub_theme" in res_js.data
    assert b"themeToggleBtn" in res_js.data

    # 2. Login as user and access dashboard
    user = User(username="themeuser", email="themeuser@test.com", is_active=True)
    user.set_password("SecurePassword123!")
    profile = UserProfile(user=user)
    db.session.add(user)
    db.session.add(profile)
    db.session.commit()

    login_res = test_client.post("/auth/login", data={"email": "themeuser@test.com", "password": "SecurePassword123!"}, follow_redirects=True)
    assert login_res.status_code == 200

    res_dash = test_client.get("/dashboard")
    assert res_dash.status_code == 200

    dash_html = res_dash.data.decode("utf-8")

    # Exactly one theme toggle button in the entire page, positioned in the top header
    assert dash_html.count('id="themeToggleBtn"') == 1
    assert "theme-icon-dark" in dash_html
    assert "theme-icon-light" in dash_html

    # Ensure duplicate toggles are NOT in the sidebar or dropdown
    assert "sidebarThemeToggle" not in dash_html
    assert "dropdownThemeToggle" not in dash_html

    # Ensure unauthenticated pages (login, register, forgot-password) do NOT have theme toggle
    res_login = test_client.get("/auth/login")
    assert b"themeToggleBtn" not in res_login.data
    res_register = test_client.get("/auth/register")
    assert b"themeToggleBtn" not in res_register.data
    res_forgot = test_client.get("/auth/forgot-password")
    assert b"themeToggleBtn" not in res_forgot.data

def test_redesigned_login_split_card_layout(test_client):
    res = test_client.get("/auth/login")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    # Single card split into two halves
    assert "login-split-card" in html
    assert "login-intro-half" in html
    assert "login-form-half" in html

    # Branding & Main Heading
    assert "ConnectHub" in html
    assert "One Platform. All Your Conversations." in html
    assert "ConnectHub brings email communication and real-time messaging together" in html

    # 4 Feature highlights
    assert "Smart Email Management" in html
    assert "Real-Time Messaging" in html
    assert "Seamless Collaboration" in html
    assert "Secure User Access" in html

    # Right half: Login Form Elements
    assert "Welcome Back!" in html
    assert "Sign in to continue to your ConnectHub workspace." in html
    assert 'name="email"' in html
    assert 'name="password"' in html
    assert "togglePasswordVisibility" in html
    assert 'id="togglePasswordBtn"' in html
    assert 'name="remember"' in html
    assert "Forgot Password?" in html
    assert "btnGoogleAuth" in html
    assert "Continue with Google" in html
    assert "Create an account" in html

    # Test login submission with valid user
    user = User.query.filter_by(email="themeuser@test.com").first()
    if not user:
        user = User(username="splituser", email="splituser@test.com", is_active=True)
        user.set_password("SecurePassword123!")
        profile = UserProfile(user=user)
        db.session.add(user)
        db.session.add(profile)
        db.session.commit()

    login_res = test_client.post("/auth/login", data={"email": user.email, "password": "SecurePassword123!"}, follow_redirects=True)
    assert login_res.status_code == 200
    assert b"Dashboard" in login_res.data or b"ConnectHub" in login_res.data

def test_theme_consistency_css_and_pages(test_client):
    # CSS rules verification
    res_css = test_client.get("/static/css/style.css")
    assert res_css.status_code == 200
    css_text = res_css.data.decode("utf-8")

    # Dark mode global overrides exist
    assert '[data-theme="dark"]' in css_text
    assert '[data-theme="dark"] .text-dark' in css_text
    assert '[data-theme="dark"] .chat-inbox-wrapper' in css_text
    assert '[data-theme="dark"] .chat-sidebar-pane' in css_text
    assert '[data-theme="dark"] .chat-main-pane' in css_text
    assert '[data-theme="dark"] .msg-bubble.theirs' in css_text
    assert '[data-theme="dark"] .list-group-item' in css_text

    # Log in and verify chat, notifications, sent emails, inbox, profile
    user = User(username="consistentuser", email="consistentuser@test.com", is_active=True)
    user.set_password("SecurePassword123!")
    profile = UserProfile(user=user)
    db.session.add(user)
    db.session.add(profile)
    db.session.commit()

    test_client.post("/auth/login", data={"email": "consistentuser@test.com", "password": "SecurePassword123!"}, follow_redirects=True)

    for path in ["/chat/", "/notifications/", "/email/sent", "/email/inbox", "/auth/profile"]:
        res_page = test_client.get(path)
        assert res_page.status_code == 200, f"Page {path} returned {res_page.status_code}"

def test_exact_email_timestamps(test_client):
    # 1. time.js asset is served
    res_time_js = test_client.get("/static/js/time.js")
    assert res_time_js.status_code == 200
    assert b"ConnectHubTime" in res_time_js.data
    assert b"formatMailListTime" in res_time_js.data

    # 2. Create users and an email to test ISO property and template data-utc attributes
    u1 = User(username="senderuser", email="senderuser@test.com", is_active=True)
    u1.set_password("SecurePassword123!")
    p1 = UserProfile(user=u1)

    u2 = User(username="recipientuser", email="recipientuser@test.com", is_active=True)
    u2.set_password("SecurePassword123!")
    p2 = UserProfile(user=u2)

    db.session.add_all([u1, p1, u2, p2])
    db.session.commit()

    mail = Email(
        sender_id=u1.id,
        recipient_id=u2.id,
        subject="Exact Time Check",
        body="Checking accurate timezone representation.",
        folder="inbox"
    )
    db.session.add(mail)
    db.session.commit()

    # 3. Model property returns non-empty ISO format
    assert mail.created_at_iso != ""
    assert "T" in mail.created_at_iso
    assert mail.sent_at_iso != ""

    # 4. Recipient views inbox -> contains data-utc
    test_client.post("/auth/login", data={"email": "recipientuser@test.com", "password": "SecurePassword123!"}, follow_redirects=True)
    res_inbox = test_client.get("/email/inbox")
    assert res_inbox.status_code == 200
    inbox_html = res_inbox.data.decode("utf-8")
    assert 'class="mail-time"' in inbox_html
    assert f'data-utc="{mail.created_at_iso}"' in inbox_html

    # 5. View email detail page -> contains mail-detail-time and data-utc
    res_view = test_client.get(f"/email/view/{mail.id}")
    assert res_view.status_code == 200
    view_html = res_view.data.decode("utf-8")
    assert 'class="mail-detail-time"' in view_html
    assert 'data-utc=' in view_html



