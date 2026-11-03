import os
import sys
import shutil
import pytest
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from extensions import db
from auth_module.models import User, UserProfile


@pytest.fixture
def app():
    test_upload_folder = os.path.join(os.path.dirname(__file__), "test_uploads")
    os.makedirs(test_upload_folder, exist_ok=True)

    test_config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool
        },
        "UPLOAD_FOLDER": test_upload_folder
    }

    app = create_app(test_config=test_config)

    with app.app_context():
        db.create_all()

        # 1. Admin
        admin = User(username="adminuser", email="admin@example.com", role="admin")
        admin.set_password("AdminPass123!")
        admin.profile = UserProfile(full_name="Admin User")

        # 2. User A (Alice)
        user_a = User(username="alice", email="alice@example.com", role="user")
        user_a.set_password("AlicePass123!")
        user_a.profile = UserProfile(full_name="Alice Smith")

        # 3. User B (Bob)
        user_b = User(username="bob", email="bob@example.com", role="user")
        user_b.set_password("BobPass123!")
        user_b.profile = UserProfile(full_name="Bob Jones")

        db.session.add_all([admin, user_a, user_b])
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

    if os.path.exists(test_upload_folder):
        shutil.rmtree(test_upload_folder, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client_a(app):
    c = app.test_client()
    res = c.post("/auth/login", data={"email": "alice@example.com", "password": "AlicePass123!"})
    assert res.status_code == 302, f"Alice login failed: {res.status_code}"
    return c


@pytest.fixture
def auth_client_b(app):
    c = app.test_client()
    res = c.post("/auth/login", data={"email": "bob@example.com", "password": "BobPass123!"})
    assert res.status_code == 302, f"Bob login failed: {res.status_code}"
    return c


@pytest.fixture
def admin_client(app):
    c = app.test_client()
    res = c.post("/auth/login", data={"email": "admin@example.com", "password": "AdminPass123!"})
    assert res.status_code == 302, f"Admin login failed: {res.status_code}"
    return c
