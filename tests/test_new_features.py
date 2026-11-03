import os
import io
import pytest
from extensions import db, socketio
from auth_module.models import User
from chat_module.models import Conversation, ConversationMember, ChatMessage
from chat_module.events import active_users


def test_online_offline_status_and_db(app):
    """Test 1: Online/Offline status updating in SQLite and memory."""
    client_a = app.test_client()
    res_a = client_a.post("/auth/login", data={"email": "alice@example.com", "password": "AlicePass123!"})
    assert res_a.status_code == 302

    client_b = app.test_client()
    res_b = client_b.post("/auth/login", data={"email": "bob@example.com", "password": "BobPass123!"})
    assert res_b.status_code == 302

    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()
        alice_id = alice.id
        bob_id = bob.id

    # 1. Connect Alice via Socket.IO
    sock_a = socketio.test_client(app, flask_test_client=client_a)
    assert sock_a.is_connected()

    with app.app_context():
        alice_fresh = db.session.get(User, alice_id)
        assert alice_fresh.online_status == "online"
        assert alice_id in active_users

    # 2. Connect Bob via Socket.IO
    sock_b = socketio.test_client(app, flask_test_client=client_b)
    assert sock_b.is_connected()

    # Bob requests online users
    sock_b.emit("request_online_users")
    received_b = sock_b.get_received()
    online_event = next((e for e in received_b if e["name"] == "online_users"), None)
    assert online_event is not None
    assert alice_id in online_event["args"][0]["user_ids"]

    # 3. Disconnect Alice
    sock_a.disconnect()

    with app.app_context():
        alice_after = db.session.get(User, alice_id)
        assert alice_after.online_status == "offline"
        assert alice_id not in active_users

    # Bob receives real-time user_status offline event
    received_b2 = sock_b.get_received()
    status_events = [e for e in received_b2 if e["name"] == "user_status"]
    assert any(e["args"][0]["user_id"] == alice_id and e["args"][0]["status"] == "offline" for e in status_events)

    sock_b.disconnect()


def test_profile_image_upload_and_remove(app):
    """Test 2: Profile image upload, serving, and removal."""
    client_a = app.test_client()
    res_a = client_a.post("/auth/login", data={"email": "alice@example.com", "password": "AlicePass123!"})
    assert res_a.status_code == 302

    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        alice_id = alice.id
        bob = User.query.filter_by(username="bob").first()
        bob_id = bob.id

    # Create dummy PNG image bytes
    dummy_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    # 1. Upload valid profile image
    data = {
        "username": "alice",
        "full_name": "Alice Wonderland",
        "bio": "Exploring real-time chat",
        "phone": "+123456789",
        "profile_image": (io.BytesIO(dummy_png), "avatar.png"),
        "submit": "Save Profile"
    }
    res = client_a.post("/auth/profile", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        alice_fresh = db.session.get(User, alice_id)
        assert alice_fresh.profile.profile_image is not None
        saved_filename = alice_fresh.profile.profile_image
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], "profiles", saved_filename)
        assert os.path.exists(file_path)

    # 2. Retrieve image via route
    img_res = client_a.get(f"/auth/profile-image/{alice_id}")
    assert img_res.status_code == 200
    assert img_res.data == dummy_png

    # 3. View another user's profile card
    view_self = client_a.get(f"/auth/user/{alice_id}")
    assert view_self.status_code == 302  # redirects to /auth/profile

    view_bob = client_a.get(f"/auth/user/{bob_id}")
    assert view_bob.status_code == 200
    assert b"User Profile" in view_bob.data

    # 4. Remove Profile Picture
    remove_res = client_a.post("/auth/profile/remove-image", follow_redirects=True)
    assert remove_res.status_code == 200

    with app.app_context():
        alice_no_img = db.session.get(User, alice_id)
        assert alice_no_img.profile.profile_image is None
        assert not os.path.exists(file_path)


def test_whatsapp_message_status_pipeline(app):
    """Test 3: WhatsApp-like ticks: Sent (✓) -> Delivered (✓✓) -> Seen (✓✓ in blue)."""
    client_a = app.test_client()
    client_a.post("/auth/login", data={"email": "alice@example.com", "password": "AlicePass123!"})

    client_b = app.test_client()
    client_b.post("/auth/login", data={"email": "bob@example.com", "password": "BobPass123!"})

    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()
        alice_id = alice.id
        bob_id = bob.id

        conv = Conversation.query.filter_by(is_group=False).first()
        if not conv:
            conv = Conversation(is_group=False)
            db.session.add(conv)
            db.session.flush()
            db.session.add_all([
                ConversationMember(conversation_id=conv.id, user_id=alice_id),
                ConversationMember(conversation_id=conv.id, user_id=bob_id)
            ])
            db.session.commit()
        conv_id = conv.id

        # Make sure Bob is OFFLINE initially
        active_users.pop(bob_id, None)
        bob.online_status = "offline"
        db.session.commit()

    # 1. Alice connects via Socket.IO
    sock_a = socketio.test_client(app, flask_test_client=client_a)
    assert sock_a.is_connected()
    sock_a.emit("join_conversation", {"conversation_id": conv_id})
    sock_a.get_received()  # flush

    # 2. Alice sends a message to offline Bob -> Should be SENT (1 tick)
    sock_a.emit("send_message", {
        "conversation_id": conv_id,
        "content": "Hello Bob, testing WhatsApp-like message status ticks!"
    })

    received_a = sock_a.get_received()
    msg_event = next((e for e in received_a if e["name"] == "new_message"), None)
    assert msg_event is not None
    msg_data = msg_event["args"][0]
    msg_id = msg_data["id"]

    # Initial status is SENT (1 tick)
    assert msg_data["status"] == "sent"

    with app.app_context():
        db_msg = db.session.get(ChatMessage, msg_id)
        assert db_msg.delivery_status == "sent"
        assert db_msg.delivered_at is None
        assert db_msg.seen_at is None

    # 3. Bob connects / logs in -> Message should automatically become DELIVERED (2 ticks)
    sock_b = socketio.test_client(app, flask_test_client=client_b)
    assert sock_b.is_connected()

    # Alice receives real-time receipt_update event with status: delivered
    received_a2 = sock_a.get_received()
    deliv_event = next((e for e in received_a2 if e["name"] == "receipt_update" and e["args"][0]["message_id"] == msg_id), None)
    assert deliv_event is not None
    assert deliv_event["args"][0]["status"] == "delivered"

    with app.app_context():
        db_msg = db.session.get(ChatMessage, msg_id)
        assert db_msg.delivered_at is not None
        assert db_msg.delivery_status == "delivered"

    # 4. Bob joins conversation and reads messages -> Should become READ / SEEN (2 blue ticks)
    sock_b.emit("join_conversation", {"conversation_id": conv_id})
    sock_b.emit("mark_messages_read", {"conversation_id": conv_id})

    # Alice receives real-time receipt_update event with status: read (seen)
    received_a3 = sock_a.get_received()
    read_event = next((e for e in received_a3 if e["name"] == "receipt_update" and e["args"][0]["message_id"] == msg_id), None)
    assert read_event is not None
    assert read_event["args"][0]["status"] == "read"

    with app.app_context():
        db_msg = db.session.get(ChatMessage, msg_id)
        assert db_msg.seen_at is not None
        assert db_msg.delivery_status == "seen"
        assert db_msg.get_status_for_sender() == "read"

    sock_a.disconnect()
    sock_b.disconnect()

