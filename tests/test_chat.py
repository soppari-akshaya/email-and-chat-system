from chat_module.models import Conversation, ConversationMember, ChatMessage
from auth_module.models import User
from extensions import db


def test_private_chat_flow(auth_client_a, app):
    with app.app_context():
        bob = User.query.filter_by(username="bob").first()
        bob_id = bob.id

    # Alice opens private chat with Bob
    res = auth_client_a.get(f"/chat/user/{bob_id}", follow_redirects=True)
    assert res.status_code == 200
    assert b"bob" in res.data.lower()

    with app.app_context():
        conv = Conversation.query.filter_by(is_group=False).first()
        assert conv is not None
        assert len(conv.members) == 2


def test_group_chat_and_members(auth_client_a, app):
    with app.app_context():
        bob = User.query.filter_by(username="bob").first()
        admin = User.query.filter_by(username="adminuser").first()
        bob_id = bob.id
        admin_id = admin.id

    # Create Group
    res = auth_client_a.post("/chat/create-group", data={
        "group_name": "Product Design Squad",
        "members": [str(bob_id)]
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Product Design Squad" in res.data

    with app.app_context():
        group = Conversation.query.filter_by(name="Product Design Squad").first()
        assert group is not None
        assert group.is_group is True
        assert len(group.members) == 2
        group_id = group.id

    # Add admin to group
    res_add = auth_client_a.post(f"/chat/group/{group_id}/add-member", data={
        "user_id": admin_id
    }, follow_redirects=True)
    assert res_add.status_code == 200

    with app.app_context():
        group = db.session.get(Conversation, group_id)
        assert len(group.members) == 3

    # Remove admin from group
    res_rem = auth_client_a.post(f"/chat/group/{group_id}/remove-member", data={
        "user_id": admin_id
    }, follow_redirects=True)
    assert res_rem.status_code == 200

    with app.app_context():
        group = db.session.get(Conversation, group_id)
        assert len(group.members) == 2


def test_chat_transcript_download(auth_client_a, app):
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()

        conv = Conversation(is_group=False)
        db.session.add(conv)
        db.session.flush()

        db.session.add_all([
            ConversationMember(conversation_id=conv.id, user_id=alice.id),
            ConversationMember(conversation_id=conv.id, user_id=bob.id),
            ChatMessage(conversation_id=conv.id, sender_id=alice.id, content="First test transcript message.")
        ])
        db.session.commit()
        conv_id = conv.id

    res = auth_client_a.get(f"/chat/conversation/{conv_id}/download")
    assert res.status_code == 200
    assert b"First test transcript message." in res.data
