
from extensions import db
from auth_module.models import User
from email_module.models import Email


def send_email(sender, recipient_email, subject, body):
    recipient = User.query.filter_by(
        email=recipient_email.strip().lower(),
        is_active=True
    ).first()

    if not recipient:
        raise ValueError("Recipient account was not found.")

    if recipient.id == sender.id:
        raise ValueError("You cannot send an email to yourself.")

    inbox_email = Email(
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject=subject.strip(),
        body=body,
        folder="inbox",
        is_read=False
    )

    sent_email = Email(
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject=subject.strip(),
        body=body,
        folder="sent",
        is_read=True
    )

    db.session.add_all([inbox_email, sent_email])
    db.session.commit()

    return sent_email


def save_draft(sender, recipient_email, subject, body):
    draft = Email(
        sender_id=sender.id,
        recipient_id=sender.id,
        subject=subject.strip(),
        body=body,
        folder="drafts",
        is_read=True
    )

    db.session.add(draft)
    db.session.commit()

    return draft


def get_inbox(user_id):
    return Email.query.filter_by(
        recipient_id=user_id,
        folder="inbox"
    ).order_by(Email.created_at.desc()).all()


def get_sent(user_id):
    return Email.query.filter_by(
        sender_id=user_id,
        folder="sent"
    ).order_by(Email.created_at.desc()).all()


def get_drafts(user_id):
    return Email.query.filter_by(
        sender_id=user_id,
        folder="drafts"
    ).order_by(Email.created_at.desc()).all()
