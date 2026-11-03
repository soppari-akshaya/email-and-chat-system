from auth_module.models import User
from email_module.models import Email
from chat_module.models import Conversation
from extensions import db


def test_admin_access_control(auth_client_a, admin_client):
    # Standard user Alice is denied access
    res_user = auth_client_a.get("/admin/", follow_redirects=True)
    assert b"Administrator access required." in res_user.data

    # Admin user is granted access
    res_admin = admin_client.get("/admin/", follow_redirects=True)
    assert res_admin.status_code == 200
    assert b"System Overview & Analytics" in res_admin.data or b"Admin Control Panel" in res_admin.data


def test_admin_user_management(admin_client, app):
    with app.app_context():
        bob = User.query.filter_by(username="bob").first()
        bob_id = bob.id

    # View users
    res_users = admin_client.get("/admin/users", follow_redirects=True)
    assert res_users.status_code == 200
    assert b"bob" in res_users.data

    # Toggle status (deactivate Bob)
    res_toggle = admin_client.post(f"/admin/users/{bob_id}/toggle-status", follow_redirects=True)
    assert res_toggle.status_code == 200

    with app.app_context():
        bob = db.session.get(User, bob_id)
        assert bob.is_active is False

    # Toggle role (promote Bob to admin)
    res_role = admin_client.post(f"/admin/users/{bob_id}/toggle-role", follow_redirects=True)
    assert res_role.status_code == 200

    with app.app_context():
        bob = db.session.get(User, bob_id)
        assert bob.role == "admin"


def test_admin_email_and_chat_oversight(admin_client, app):
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        email = Email(sender_id=alice.id, recipient_id=alice.id, subject="Audit This Mail", body="Audit content", folder="inbox")
        conv = Conversation(is_group=True, name="Audit Group")
        db.session.add_all([email, conv])
        db.session.commit()
        email_id = email.id
        conv_id = conv.id

    # Audit emails
    res_emails = admin_client.get("/admin/emails", follow_redirects=True)
    assert res_emails.status_code == 200
    assert b"Audit This Mail" in res_emails.data

    # Delete email
    res_del_email = admin_client.post(f"/admin/emails/{email_id}/delete", follow_redirects=True)
    assert res_del_email.status_code == 200

    with app.app_context():
        assert db.session.get(Email, email_id) is None

    # Audit chats
    res_chats = admin_client.get("/admin/chats", follow_redirects=True)
    assert res_chats.status_code == 200
    assert b"Audit Group" in res_chats.data

    # Delete chat
    res_del_chat = admin_client.post(f"/admin/chats/{conv_id}/delete", follow_redirects=True)
    assert res_del_chat.status_code == 200

    with app.app_context():
        assert db.session.get(Conversation, conv_id) is None
