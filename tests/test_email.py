import io
from email_module.models import Email, EmailAttachment
from auth_module.models import User
from extensions import db


def test_send_and_receive_email(auth_client_a, auth_client_b, app):
    # Alice sends email to Bob
    res = auth_client_a.post("/email/compose", data={
        "action": "send",
        "recipient": "bob@example.com",
        "subject": "Project Kickoff Meeting",
        "body": "Hi Bob, let's meet tomorrow at 10 AM to discuss the new roadmap.",
        "label": "Work"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Email sent successfully!" in res.data

    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        bob = User.query.filter_by(username="bob").first()

        sent_mail = Email.query.filter_by(sender_id=alice.id, folder="sent").first()
        assert sent_mail is not None
        assert sent_mail.subject == "Project Kickoff Meeting"
        assert sent_mail.label == "Work"

        inbox_mail = Email.query.filter_by(recipient_id=bob.id, folder="inbox").first()
        assert inbox_mail is not None
        assert inbox_mail.subject == "Project Kickoff Meeting"
        assert inbox_mail.is_read is False
        inbox_id = inbox_mail.id

    # Bob checks inbox
    res_inbox = auth_client_b.get("/email/", follow_redirects=True)
    assert res_inbox.status_code == 200
    assert b"Project Kickoff Meeting" in res_inbox.data

    # Bob views email -> marks as read
    res_view = auth_client_b.get(f"/email/view/{inbox_id}", follow_redirects=True)
    assert res_view.status_code == 200
    assert b"Project Kickoff Meeting" in res_view.data

    with app.app_context():
        viewed_mail = db.session.get(Email, inbox_id)
        assert viewed_mail.is_read is True


def test_draft_saving(auth_client_a, app):
    # Save draft
    res = auth_client_a.post("/email/compose", data={
        "action": "draft",
        "recipient": "bob@example.com",
        "subject": "Draft Subject Note",
        "body": "Initial thoughts on the feature.",
        "label": "Personal"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Draft saved successfully." in res.data

    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        draft = Email.query.filter_by(sender_id=alice.id, folder="drafts").first()
        assert draft is not None
        assert draft.subject == "Draft Subject Note"


def test_star_and_important(auth_client_a, app):
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        email = Email(
            sender_id=alice.id,
            recipient_id=alice.id,
            subject="Test Star & Important",
            body="Content",
            folder="inbox"
        )
        db.session.add(email)
        db.session.commit()
        email_id = email.id

    # Toggle Star
    res_star = auth_client_a.post(f"/email/star/{email_id}", follow_redirects=True)
    assert res_star.status_code == 200

    with app.app_context():
        email = db.session.get(Email, email_id)
        assert email.is_starred is True

    # Toggle Important
    res_imp = auth_client_a.post(f"/email/important/{email_id}", follow_redirects=True)
    assert res_imp.status_code == 200

    with app.app_context():
        email = db.session.get(Email, email_id)
        assert email.is_important is True


def test_trash_restore_and_delete(auth_client_a, app):
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        email = Email(
            sender_id=alice.id,
            recipient_id=alice.id,
            subject="Delete Me",
            body="Body",
            folder="inbox"
        )
        db.session.add(email)
        db.session.commit()
        email_id = email.id

    # Move to trash
    res_trash = auth_client_a.post(f"/email/delete/{email_id}", follow_redirects=True)
    assert res_trash.status_code == 200

    with app.app_context():
        email = db.session.get(Email, email_id)
        assert email.folder == "trash"

    # Restore
    res_restore = auth_client_a.post(f"/email/restore/{email_id}", follow_redirects=True)
    assert res_restore.status_code == 200

    with app.app_context():
        email = db.session.get(Email, email_id)
        assert email.folder in ["inbox", "sent", "drafts"]

    # Move to trash again and permanently delete
    auth_client_a.post(f"/email/delete/{email_id}")
    res_perm = auth_client_a.post(f"/email/permanent-delete/{email_id}", follow_redirects=True)
    assert res_perm.status_code == 200

    with app.app_context():
        email = db.session.get(Email, email_id)
        assert email is None


def test_email_with_attachment(auth_client_a, auth_client_b, app):
    test_file = (io.BytesIO(b"Hello world attachment content"), "test_document.txt")

    res = auth_client_a.post("/email/compose", data={
        "action": "send",
        "recipient": "bob@example.com",
        "subject": "With Attachment",
        "body": "See attached file.",
        "attachments": [test_file]
    }, content_type="multipart/form-data", follow_redirects=True)

    assert res.status_code == 200

    with app.app_context():
        bob = User.query.filter_by(username="bob").first()
        inbox_mail = Email.query.filter_by(recipient_id=bob.id, subject="With Attachment").first()
        assert inbox_mail is not None
        assert len(inbox_mail.attachments) > 0
        att_id = inbox_mail.attachments[0].id

    # Bob downloads attachment
    res_dl = auth_client_b.get(f"/email/attachment/{att_id}/download")
    assert res_dl.status_code == 200
    assert res_dl.data == b"Hello world attachment content"
