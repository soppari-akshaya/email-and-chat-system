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

    # Test firebase config endpoint
    res = test_client.get("/auth/firebase-config")
    assert res.status_code == 200
    data = res.get_json()
    assert "apiKey" in data
    assert "projectId" in data

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
