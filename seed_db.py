import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from extensions import db
from auth_module.models import User, UserProfile
from email_module.models import Email
from chat_module.models import Conversation, ConversationMember, ChatMessage, ChatMessageReceipt

def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        if User.query.filter_by(username="admin").first():
            print("Database already seeded.")
            return

        print("Seeding database with initial users and demo communications...")

        # 1. Admin
        admin = User(username="admin", email="admin@connecthub.com", role="admin")
        admin.set_password("AdminPass123!")
        admin.profile = UserProfile(full_name="System Administrator", bio="ConnectHub Platform Administrator")

        # 2. Alice
        alice = User(username="alice", email="alice@connecthub.com", role="user")
        alice.set_password("AlicePass123!")
        alice.profile = UserProfile(full_name="Alice Smith", bio="Product Designer & Strategist")

        # 3. Bob
        bob = User(username="bob", email="bob@connecthub.com", role="user")
        bob.set_password("BobPass123!")
        bob.profile = UserProfile(full_name="Bob Jones", bio="Lead Frontend Engineer")

        db.session.add_all([admin, alice, bob])
        db.session.commit()

        # Seed initial welcome email from admin to Alice and Bob
        welcome_alice = Email(
            sender_id=admin.id,
            recipient_id=alice.id,
            subject="Welcome to ConnectHub!",
            body="Hi Alice,\n\nWelcome to ConnectHub! You can compose rich emails, send attachments, and chat in real-time.\n\nBest regards,\nConnectHub Team",
            folder="inbox",
            label="Work"
        )
        welcome_bob = Email(
            sender_id=admin.id,
            recipient_id=bob.id,
            subject="Welcome to ConnectHub!",
            body="Hi Bob,\n\nWelcome to ConnectHub! Let us know if you need assistance testing real-time messaging or attachments.\n\nBest regards,\nConnectHub Team",
            folder="inbox",
            label="Work"
        )
        db.session.add_all([welcome_alice, welcome_bob])

        # Seed 1-to-1 conversation between Alice and Bob
        conv = Conversation(is_group=False)
        db.session.add(conv)
        db.session.commit()

        m1 = ConversationMember(conversation_id=conv.id, user_id=alice.id)
        m2 = ConversationMember(conversation_id=conv.id, user_id=bob.id)
        db.session.add_all([m1, m2])
        db.session.commit()

        msg1 = ChatMessage(
            conversation_id=conv.id,
            sender_id=alice.id,
            content="Hi Bob! Welcome to ConnectHub chat."
        )
        msg2 = ChatMessage(
            conversation_id=conv.id,
            sender_id=bob.id,
            content="Hey Alice! Everything looks super clean and fast."
        )
        db.session.add_all([msg1, msg2])
        db.session.commit()

        r1 = ChatMessageReceipt(message_id=msg1.id, recipient_id=bob.id, delivered_at=msg1.created_at, read_at=msg1.created_at)
        r2 = ChatMessageReceipt(message_id=msg2.id, recipient_id=alice.id, delivered_at=msg2.created_at, read_at=msg2.created_at)
        db.session.add_all([r1, r2])
        db.session.commit()

        print("Database seeding completed successfully!")
        print("Initial Accounts:")
        print("  - Admin:  admin@connecthub.com  / AdminPass123! (Role: admin)")
        print("  - Alice:  alice@connecthub.com  / AlicePass123! (Role: user)")
        print("  - Bob:    bob@connecthub.com    / BobPass123!   (Role: user)")

if __name__ == "__main__":
    seed()
