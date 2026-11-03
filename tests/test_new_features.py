import pytest
from app import create_app
from extensions import db
from auth_module.models import User, UserProfile
from notification_module.models import PushSubscription, Notification

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

