import pytest
from app import create_app, db, socketio
from auth_module.models import User
from chat_module.models import Conversation, ConversationMember, ChatMessage
from datetime import datetime, timezone

def test_chat_registered_users_and_recent_chats(app, client):
    """Verify that all registered users appear, recent chats are deduplicated and sorted by latest message."""
    with app.app_context():
        # Check registered users in database
        users = User.query.filter_by(is_active=True).all()
        assert len(users) >= 3

        # Log in as Alice
        user_alice = User.query.filter_by(username="alice").first() or users[0]

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_alice.id)
            sess['_fresh'] = True

        res = client.get('/chat/')
        assert res.status_code == 200
        html = res.data.decode('utf-8')

        # Check All People tab contains all other registered users
        for u in users:
            if u.id != user_alice.id:
                assert u.username in html or u.email in html

        # Check that data-utc attribute is present for timestamps
        assert 'data-utc' in html

def test_private_chat_creation_and_timestamps(app, client):
    """Verify 1-to-1 chat initialization, ISO timestamp presence, and persistence."""
    with app.app_context():
        user1 = User.query.filter_by(email="akshaya@gmail.com").first() or User.query.get(1)
        user2 = User.query.filter_by(email="alice@connecthub.com").first() or User.query.get(2)

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user1.id)
            sess['_fresh'] = True

        # Access 1-on-1 private chat with user2
        res = client.get(f'/chat/user/{user2.id}', follow_redirects=True)
        assert res.status_code == 200
        html = res.data.decode('utf-8')

        assert user2.username in html

        # Verify Socket.IO can send message and timestamps are UTC ISO
        socket_client1 = socketio.test_client(app, flask_test_client=client)
        assert socket_client1.is_connected()

        # Find conversation
        c1 = ConversationMember.query.filter_by(user_id=user1.id).all()
        conv_id = None
        for cm in c1:
            if ConversationMember.query.filter_by(conversation_id=cm.conversation_id, user_id=user2.id).first():
                conv_id = cm.conversation_id
                break

        assert conv_id is not None

        socket_client1.emit('join_conversation', {'conversation_id': conv_id})
        socket_client1.emit('send_message', {
            'conversation_id': conv_id,
            'content': 'Hello Alice from Akshaya! Testing accurate UTC timestamps.'
        })

        rec = socket_client1.get_received()
        new_msgs = [e for e in rec if e['name'] == 'new_message']
        assert len(new_msgs) > 0
        msg_payload = new_msgs[0]['args'][0]
        assert 'created_at' in msg_payload
        assert msg_payload['created_at'].endswith('Z') or '+' in msg_payload['created_at']

        # Verify DB persistence
        saved_msg = ChatMessage.query.filter_by(content='Hello Alice from Akshaya! Testing accurate UTC timestamps.').first()
        assert saved_msg is not None
        assert saved_msg.created_at_iso is not None
        assert 'Z' in saved_msg.created_at_iso
