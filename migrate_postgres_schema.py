"""
ConnectHub Safe PostgreSQL Database Schema Migration Script
Applies all missing columns and tables to Render PostgreSQL without data loss.

Usage:
    python migrate_postgres_schema.py
Or with a specific connection string:
    python migrate_postgres_schema.py "postgresql://user:pass@host:port/dbname"
"""

import sys
import os
from sqlalchemy import create_engine, inspect, text


def run_migration(pg_url=None):
    if not pg_url:
        pg_url = os.getenv("DATABASE_URL")
    if not pg_url and len(sys.argv) > 1:
        pg_url = sys.argv[1]

    if not pg_url:
        print("[ERROR] No DATABASE_URL provided.")
        print("Please set DATABASE_URL or pass it as an argument:")
        print("    python migrate_postgres_schema.py \"postgresql://...\"")
        sys.exit(1)

    # Normalize driver for psycopg 3
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif pg_url.startswith("postgresql://") and not pg_url.startswith("postgresql+psycopg://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)

    safe_url = pg_url.split("@")[-1] if "@" in pg_url else "configured host"
    print("=" * 70)
    print("CONNECTHUB POSTGRESQL SCHEMA MIGRATION")
    print(f"Target Database: {safe_url}")
    print("=" * 70)

    engine = create_engine(pg_url)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    print("\nExisting Tables Found:", ", ".join(sorted(existing_tables)))

    with engine.begin() as conn:
        # 1. user_profiles
        if "user_profiles" in existing_tables:
            print("\n[1/5] Checking and migrating 'user_profiles'...")
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS desktop_notifications_enabled BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS email_notifications_enabled BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS private_chat_notifications_enabled BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS group_chat_notifications_enabled BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS sound_enabled BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS google_id VARCHAR(128);"))
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS notification_preferences VARCHAR(255) DEFAULT 'email,chat,sound';"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_profiles_google_id ON user_profiles (google_id);"))
            print("      [OK] 'user_profiles' columns verified/added.")

        # 2. emails
        if "emails" in existing_tables:
            print("\n[2/5] Checking and migrating 'emails'...")
            conn.execute(text("ALTER TABLE emails ADD COLUMN IF NOT EXISTS label VARCHAR(50);"))
            print("      [OK] 'emails.label' verified/added.")

        # 3. chat_messages
        if "chat_messages" in existing_tables:
            print("\n[3/5] Checking and migrating 'chat_messages'...")
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reply_to_id INTEGER;"))
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_name VARCHAR(255);"))
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_path VARCHAR(500);"))
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_mimetype VARCHAR(150);"))
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_size INTEGER;"))
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP WITH TIME ZONE;"))
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;"))
            print("      [OK] 'chat_messages' columns verified/added.")

        # 4. email_attachments
        if "email_attachments" in existing_tables:
            print("\n[4/5] Checking and migrating 'email_attachments'...")
            conn.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS mimetype VARCHAR(150) DEFAULT 'application/octet-stream';"))
            print("      [OK] 'email_attachments.mimetype' verified/added.")

        # 5. push_subscriptions
        print("\n[5/5] Checking and creating 'push_subscriptions'...")
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
        print("      [OK] 'push_subscriptions' table verified/created.")

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETED SUCCESSFULLY WITHOUT ANY DATA LOSS!")
    print("=" * 70)


if __name__ == "__main__":
    run_migration()

