from auth_module.models import User


def test_register_user(client, app):
    response = client.post("/auth/register", data={
        "username": "charlie",
        "email": "charlie@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!"
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username="charlie").first()
        assert user is not None
        assert user.email == "charlie@example.com"
        assert user.check_password("Password123!")


def test_login_logout(client):
    # Success login
    res = client.post("/auth/login", data={
        "email": "alice@example.com",
        "password": "AlicePass123!"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Welcome back, alice!" in res.data or b"alice" in res.data

    # Logout
    res_logout = client.get("/auth/logout", follow_redirects=True)
    assert res_logout.status_code == 200
    assert b"logged out" in res_logout.data.lower()


def test_invalid_login(client):
    res = client.post("/auth/login", data={
        "email": "alice@example.com",
        "password": "WrongPassword!"
    }, follow_redirects=True)
    assert b"Invalid email or password." in res.data


def test_profile_update(auth_client_a, app):
    res = auth_client_a.post("/auth/profile", data={
        "submit": "1",
        "username": "alice",
        "full_name": "Alice M. Smith",
        "phone": "+1987654321",
        "bio": "Software developer and designer.",
        "notifications": ["email", "chat"]
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Profile updated successfully!" in res.data

    with app.app_context():
        user = User.query.filter_by(username="alice").first()
        assert user.profile.full_name == "Alice M. Smith"
        assert user.profile.phone == "+1987654321"
        assert "email,chat" in user.profile.notification_preferences


def test_change_password(auth_client_a, app):
    res = auth_client_a.post("/auth/change-password", data={
        "current_password": "AlicePass123!",
        "new_password": "NewSecretPassword123!",
        "confirm_new_password": "NewSecretPassword123!"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"password has been changed successfully" in res.data

    with app.app_context():
        user = User.query.filter_by(username="alice").first()
        assert user.check_password("NewSecretPassword123!")

