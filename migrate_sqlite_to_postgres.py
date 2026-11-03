"""
ConnectHub Safe Migration Script: SQLite -> PostgreSQL
Migrates all existing registered users, profiles, emails, conversations, messages, and receipts
from local application.db to Render PostgreSQL without data loss.

Usage:
    python migrate_sqlite_to_postgres.py [POSTGRES_DATABASE_URL]
Or set the DATABASE_URL environment variable and run:
    python migrate_sqlite_to_postgres.py
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from extensions import db
from auth_module.models import User, UserProfile
from email_module.models import Email, EmailAttachment
from chat_module.models import Conversation, ConversationMember, ChatMessage, ChatMessageReceipt
from notification_module.models import Notification

def migrate(sqlite_db_path="application.db", pg_url=None):
    if not pg_url:
        pg_url = os.getenv("DATABASE_URL")
    if not pg_url:
        if len(sys.argv) > 1:
            pg_url = sys.argv[1]

    if not pg_url:
        print("ERROR: PostgreSQL database URL not provided.")
        print("Please provide it as an argument or set the DATABASE_URL environment variable:")
        print("    python migrate_sqlite_to_postgres.py postgresql://user:pass@host:port/dbname")
        sys.exit(1)

    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif pg_url.startswith("postgresql://") and not pg_url.startswith("postgresql+psycopg://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)

    if not os.path.exists(sqlite_db_path):
        print(f"ERROR: SQLite database file '{sqlite_db_path}' not found.")
        sys.exit(1)

    print(f"Source SQLite DB: {sqlite_db_path}")
    print(f"Target PostgreSQL DB: {pg_url.split('@')[-1] if '@' in pg_url else 'configured'}")

    # Connect to SQLite
    sqlite_engine = create_engine(f"sqlite:///{sqlite_db_path}")
    SqliteSession = sessionmaker(bind=sqlite_engine)
    sqlite_sess = SqliteSession()

    # Connect to PostgreSQL
    pg_engine = create_engine(pg_url)
    PgSession = sessionmaker(bind=pg_engine)
    pg_sess = PgSession()

    # Initialize tables on target
    print("\nEnsuring all tables exist on PostgreSQL target...")
    app = create_app(test_config={"SQLALCHEMY_DATABASE_URI": pg_url, "TESTING": False})
    with app.app_context():
        db.create_all()

    try:
        # 1. Users
        users = sqlite_sess.execute(select(User)).scalars().all()
        print(f"Migrating {len(users)} Users...")
        for u in users:
            existing = pg_sess.get(User, u.id)
            if not existing:
                pg_u = User(
                    id=u.id,
                    username=u.username,
                    email=u.email,
                    password_hash=u.password_hash,
                    role=u.role,
                    is_active=u.is_active,
                    created_at=u.created_at,
                    last_seen=u.last_seen,
                    online_status=u.online_status
                )
                pg_sess.add(pg_u)
        pg_sess.commit()

        # 2. User Profiles
        profiles = sqlite_sess.execute(select(UserProfile)).scalars().all()
        print(f"Migrating {len(profiles)} User Profiles...")
        for p in profiles:
            existing = pg_sess.get(UserProfile, p.id)
            if not existing:
                pg_p = UserProfile(
                    id=p.id,
                    user_id=p.user_id,
                    full_name=p.full_name,
                    bio=p.bio,
                    profile_image=p.profile_image,
                    notification_preferences=p.notification_preferences,
                    updated_at=p.updated_at
                )
                pg_sess.add(pg_p)
        pg_sess.commit()

        # 3. Conversations
        convs = sqlite_sess.execute(select(Conversation)).scalars().all()
        print(f"Migrating {len(convs)} Conversations...")
        for c in convs:
            existing = pg_sess.get(Conversation, c.id)
            if not existing:
                pg_c = Conversation(
                    id=c.id,
                    name=c.name,
                    is_group=c.is_group,
                    created_at=c.created_at,
                    last_message_at=c.last_message_at
                )
                pg_sess.add(pg_c)
        pg_sess.commit()

        # 4. Conversation Members
        members = sqlite_sess.execute(select(ConversationMember)).scalars().all()
        print(f"Migrating {len(members)} Conversation Members...")
        for m in members:
            existing = pg_sess.get(ConversationMember, m.id)
            if not existing:
                pg_m = ConversationMember(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    user_id=m.user_id,
                    joined_at=m.joined_at,
                    role=m.role
                )
                pg_sess.add(pg_m)
        pg_sess.commit()

        # 5. Chat Messages
        msgs = sqlite_sess.execute(select(ChatMessage)).scalars().all()
        print(f"Migrating {len(msgs)} Chat Messages...")
        for msg in msgs:
            existing = pg_sess.get(ChatMessage, msg.id)
            if not existing:
                pg_msg = ChatMessage(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    sender_id=msg.sender_id,
                    content=msg.content,
                    created_at=msg.created_at,
                    is_edited=msg.is_edited,
                    edited_at=msg.edited_at,
                    is_deleted=msg.is_deleted,
                    attachment_path=msg.attachment_path,
                    attachment_name=msg.attachment_name,
                    attachment_size=msg.attachment_size,
                    attachment_mimetype=msg.attachment_mimetype,
                    delivery_status=msg.delivery_status,
                    delivered_at=msg.delivered_at,
                    seen_at=msg.seen_at,
                    reply_to_id=msg.reply_to_id
                )
                pg_sess.add(pg_msg)
        pg_sess.commit()

        # 6. Chat Message Receipts
        receipts = sqlite_sess.execute(select(ChatMessageReceipt)).scalars().all()
        print(f"Migrating {len(receipts)} Message Receipts...")
        for r in receipts:
            existing = pg_sess.get(ChatMessageReceipt, r.id)
            if not existing:
                pg_r = ChatMessageReceipt(
                    id=r.id,
                    message_id=r.message_id,
                    recipient_id=r.recipient_id,
                    delivered_at=r.delivered_at,
                    read_at=r.read_at
                )
                pg_sess.add(pg_r)
        pg_sess.commit()

        # 7. Emails
        emails = sqlite_sess.execute(select(Email)).scalars().all()
        print(f"Migrating {len(emails)} Emails...")
        for e in emails:
            existing = pg_sess.get(Email, e.id)
            if not existing:
                pg_e = Email(
                    id=e.id,
                    sender_id=e.sender_id,
                    recipient_id=e.recipient_id,
                    subject=e.subject,
                    body=e.body,
                    is_read=e.is_read,
                    is_starred=e.is_starred,
                    is_important=e.is_important,
                    is_trash=e.is_trash,
                    folder=e.folder,
                    label=e.label,
                    created_at=e.created_at,
                    read_at=e.read_at,
                    trash_at=e.trash_at
                )
                pg_sess.add(pg_e)
        pg_sess.commit()

        # 8. Email Attachments
        e_attachments = sqlite_sess.execute(select(EmailAttachment)).scalars().all()
        print(f"Migrating {len(e_attachments)} Email Attachments...")
        for a in e_attachments:
            existing = pg_sess.get(EmailAttachment, a.id)
            if not existing:
                pg_a = EmailAttachment(
                    id=a.id,
                    email_id=a.email_id,
                    filename=a.filename,
                    filepath=a.filepath,
                    filesize=a.filesize,
                    mimetype=a.mimetype,
                    uploaded_at=a.uploaded_at
                )
                pg_sess.add(pg_a)
        pg_sess.commit()

        # 9. Notifications
        notifs = sqlite_sess.execute(select(Notification)).scalars().all()
        print(f"Migrating {len(notifs)} Notifications...")
        for n in notifs:
            existing = pg_sess.get(Notification, n.id)
            if not existing:
                pg_n = Notification(
                    id=n.id,
                    recipient_id=n.recipient_id,
                    sender_id=n.sender_id,
                    conversation_id=n.conversation_id,
                    message=n.message,
                    is_read=n.is_read,
                    created_at=n.created_at
                )
                pg_sess.add(pg_n)
        pg_sess.commit()

        # Reset PostgreSQL ID Sequences so future autoincrements work seamlessly
        print("\nResetting PostgreSQL primary key auto-increment sequences...")
        tables = [
            "users", "user_profiles", "conversations", "conversation_members",
            "chat_messages", "chat_message_receipts", "emails",
            "email_attachments", "notifications"
        ]
        with pg_engine.connect() as conn:
            for table in tables:
                try:
                    conn.execute(text(f"""
                        SELECT setval(
                            pg_get_serial_sequence('{table}', 'id'),
                            COALESCE((SELECT MAX(id) FROM {table}), 1)
                        );
                    """))
                    conn.commit()
                except Exception as seq_err:
                    pass

        print("\n[SUCCESS] Migration completed! All data migrated to PostgreSQL.")

    except Exception as err:
        pg_sess.rollback()
        print(f"\n[ERROR] Migration failed: {err}")
        raise err
    finally:
        sqlite_sess.close()
        pg_sess.close()

if __name__ == "__main__":
    migrate()
