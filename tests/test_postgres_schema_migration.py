import os
import sqlite3
import pytest
from sqlalchemy import create_engine, inspect, text
from app import create_app, ensure_db_schema
from extensions import db
from auth_module.models import User, UserProfile
from email_module.models import Email
from chat_module.models import Conversation, ConversationMember, ChatMessage
from notification_module.models import PushSubscription
from flask_migrate import upgrade as flask_migrate_upgrade


def test_schema_migration_simulation(tmp_path):
    """
    Simulates an existing database lacking the new columns,
    runs ensure_db_schema and asserts that all columns are added and queryable.
    """
    db_file = tmp_path / "simulated_old.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    # Create old schema
    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'user' NOT NULL,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            is_verified BOOLEAN DEFAULT 0 NOT NULL,
            created_at DATETIME,
            last_seen DATETIME,
            online_status VARCHAR(20) DEFAULT 'offline' NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE user_profiles (
            id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL,
            full_name VARCHAR(100),
            bio VARCHAR(300),
            phone VARCHAR(20),
            profile_image VARCHAR(255),
            created_at DATETIME
        );
    """)
    cur.execute("""
        INSERT INTO users (id, username, email, password_hash, role, is_active, is_verified)
        VALUES (1, 'alice', 'alice@connecthub.com', 'hash123', 'user', 1, 1);
    """)
    cur.execute("""
        INSERT INTO user_profiles (id, user_id, full_name, bio, phone, profile_image)
        VALUES (1, 1, 'Alice Smith', 'Alice bio', '+123456789', 'avatar_1.jpg');
    """)
    conn.commit()
    conn.close()

    app = create_app(test_config={
        "TESTING": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-key"
    })

    with app.app_context():
        ensure_db_schema(app)

        insp = inspect(db.engine)
        cols_after = {c["name"] for c in insp.get_columns("user_profiles")}
        assert "desktop_notifications_enabled" in cols_after
        assert "email_notifications_enabled" in cols_after
        assert "private_chat_notifications_enabled" in cols_after
        assert "group_chat_notifications_enabled" in cols_after
        assert "sound_enabled" in cols_after
        assert "google_id" in cols_after
        assert "notification_preferences" in cols_after

        # Verify existing data preserved
        user = User.query.filter_by(username="alice").first()
        assert user is not None
        assert user.profile is not None
        assert user.profile.full_name == "Alice Smith"
        assert user.profile.profile_image == "avatar_1.jpg"
        assert user.profile.desktop_notifications_enabled is True
        assert user.profile.email_notifications_enabled is True
        assert user.profile.sound_enabled is True

        user.profile.desktop_notifications_enabled = False
        db.session.commit()

        reloaded = UserProfile.query.filter_by(user_id=1).first()
        assert reloaded.desktop_notifications_enabled is False
        assert reloaded.email_notifications_enabled is True


def test_alembic_upgrade_on_fresh_db(tmp_path):
    """
    Tests that Alembic migration head upgrades cleanly on a database.
    """
    db_file = tmp_path / "alembic_test.db"
    app = create_app(test_config={
        "TESTING": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-key"
    })

    with app.app_context():
        # Run Alembic upgrade to head
        flask_migrate_upgrade(revision="head")

        insp = inspect(db.engine)
        up_cols = {c["name"] for c in insp.get_columns("user_profiles")}
        assert "desktop_notifications_enabled" in up_cols
        assert "email_notifications_enabled" in up_cols
        assert "sound_enabled" in up_cols
        assert "google_id" in up_cols
        assert "push_subscriptions" in set(insp.get_table_names())
