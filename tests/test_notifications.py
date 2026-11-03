from notification_module.models import Notification
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
