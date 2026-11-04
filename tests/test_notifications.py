from notification_module.models import Notification
from chat_module.models import Conversation, ConversationMember, ChatMessage
from auth_module.models import User
from extensions import db


def test_notification_workflow(auth_client_a, app):
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()

        n1 = Notification(recipient_id=alice.id, sender_id=bob.id, message="Notice 1", is_read=False)
        n2 = Notification(recipient_id=alice.id, sender_id=bob.id, message="Notice 2", is_read=False)
        db.session.add_all([n1, n2])
        db.session.commit()
        n1_id = n1.id
        alice_id = alice.id

    # View notifications
    res = auth_client_a.get("/notifications/", follow_redirects=True)
    assert res.status_code == 200
    assert b"Notice 1" in res.data
    assert b"Notice 2" in res.data

    # Mark single read
    res_mark = auth_client_a.post(f"/notifications/read/{n1_id}", follow_redirects=True)
    assert res_mark.status_code == 200

    with app.app_context():
        notif = db.session.get(Notification, n1_id)
        assert notif.is_read is True

    # Mark all read
    res_all = auth_client_a.post("/notifications/read-all", follow_redirects=True)
    assert res_all.status_code == 200

    with app.app_context():
        unread_count = Notification.query.filter_by(recipient_id=alice_id, is_read=False).count()
        assert unread_count == 0


def test_notification_open_chat_private(auth_client_a, app):
    """Test clicking Open Chat on a private chat notification routes to 1-on-1 chat and marks read."""
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()

        # Create private conversation
        conv = Conversation(is_group=False)
        db.session.add(conv)
        db.session.flush()

        db.session.add_all([
            ConversationMember(conversation_id=conv.id, user_id=alice.id),
            ConversationMember(conversation_id=conv.id, user_id=bob.id)
        ])

        msg = ChatMessage(
            conversation_id=conv.id,
            sender_id=bob.id,
            content="Hello Alice, this is a private message from Bob"
        )
        db.session.add(msg)
        db.session.flush()

        notif = Notification(
            recipient_id=alice.id,
            sender_id=bob.id,
            conversation_id=conv.id,
            message="bob: Hello Alice, this is a private message from Bob",
            is_read=False
        )
        db.session.add(notif)
        db.session.commit()

        conv_id = conv.id
        notif_id = notif.id
        bob_id = bob.id

    # 1. Notifications page shows "Open Chat" linking to /chat/conversation/<conv_id>?notif_id=<notif_id>
    res_page = auth_client_a.get("/notifications/")
    assert res_page.status_code == 200
    expected_link = f"/chat/conversation/{conv_id}?notif_id={notif_id}"
    assert expected_link.encode() in res_page.data
    assert b"Open Chat" in res_page.data

    # 2. Clicking Open Chat resolves through view_conversation to private chat with Bob
    res_open = auth_client_a.get(expected_link, follow_redirects=True)
    assert res_open.status_code == 200
    assert b"Hello Alice, this is a private message from Bob" in res_open.data

    # 3. Notification is automatically marked as read
    with app.app_context():
        updated_notif = db.session.get(Notification, notif_id)
        assert updated_notif.is_read is True


def test_notification_open_chat_group(auth_client_a, app):
    """Test clicking Open Chat on a group chat notification routes to group chat."""
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()

        group = Conversation(is_group=True, name="Engineering Core")
        db.session.add(group)
        db.session.flush()

        db.session.add_all([
            ConversationMember(conversation_id=group.id, user_id=alice.id),
            ConversationMember(conversation_id=group.id, user_id=bob.id)
        ])

        msg = ChatMessage(
            conversation_id=group.id,
            sender_id=bob.id,
            content="Team sync today at 4 PM"
        )
        db.session.add(msg)
        db.session.flush()

        notif = Notification(
            recipient_id=alice.id,
            sender_id=bob.id,
            conversation_id=group.id,
            message="Engineering Core: Team sync today at 4 PM",
            is_read=False
        )
        db.session.add(notif)
        db.session.commit()

        group_id = group.id
        notif_id = notif.id

    res_open = auth_client_a.get(f"/chat/conversation/{group_id}?notif_id={notif_id}", follow_redirects=True)
    assert res_open.status_code == 200
    assert b"Engineering Core" in res_open.data
    assert b"Team sync today at 4 PM" in res_open.data

    with app.app_context():
        updated_notif = db.session.get(Notification, notif_id)
        assert updated_notif.is_read is True


def test_notification_graceful_error_handling(auth_client_a, admin_client, app):
    """Test deleted conversations and non-member access are handled gracefully without 500/404."""
    # 1. Non-existent conversation
    res_missing = auth_client_a.get("/chat/conversation/99999", follow_redirects=True)
    assert res_missing.status_code == 200
    assert b"This conversation is no longer available" in res_missing.data

    # 2. Unauthorized access (admin attempting to access private chat between Alice and Bob)
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()

        conv = Conversation(is_group=False)
        db.session.add(conv)
        db.session.flush()

        db.session.add_all([
            ConversationMember(conversation_id=conv.id, user_id=alice.id),
            ConversationMember(conversation_id=conv.id, user_id=bob.id)
        ])
        db.session.commit()
        conv_id = conv.id

    res_unauth = admin_client.get(f"/chat/conversation/{conv_id}", follow_redirects=True)
    assert res_unauth.status_code == 200
    assert b"You are not authorized to access this conversation" in res_unauth.data


def test_notification_email_link(auth_client_a, app):
    """Test email notification does not show Open Chat, but provides View Email to inbox."""
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()

        notif = Notification(
            recipient_id=alice.id,
            sender_id=bob.id,
            conversation_id=None,
            message="New email from bob: Quarterly Planning",
            is_read=False
        )
        db.session.add(notif)
        db.session.commit()

    res = auth_client_a.get("/notifications/")
    assert res.status_code == 200
    assert b"View Email" in res.data
    assert b"/email/inbox" in res.data
    assert b"Open Chat" not in res.data
