import os
import re
import uuid
from flask import current_app
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_
from extensions import db
from auth_module.models import User
from email_module.models import Email, EmailAttachment
from notification_module.models import Notification


ALLOWED_ATTACHMENT_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp",
    "pdf", "doc", "docx", "txt",
    "xls", "xlsx", "ppt", "pptx", "csv", "zip"
}


def allowed_attachment(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS


def save_uploaded_attachment(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return None

    orig_name = secure_filename(uploaded_file.filename)
    if not orig_name or not allowed_attachment(orig_name):
        return None

    ext = orig_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"

    upload_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "email_attachments")
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, stored_name)

    uploaded_file.seek(0, os.SEEK_END)
    file_size = uploaded_file.tell()
    uploaded_file.seek(0)

    uploaded_file.save(file_path)

    mimetype = getattr(uploaded_file, "mimetype", "application/octet-stream") or "application/octet-stream"

    return {
        "original_filename": orig_name,
        "stored_filename": stored_name,
        "file_size": file_size,
        "mimetype": mimetype
    }


def find_user_by_email_or_username(input_str):
    """
    Robust recipient lookup:
    1. Extracts pure email if formatted as 'Name <email@domain>' or 'Name (email@domain)'
    2. Case-insensitive matching on User.email with trimming
    3. Fallback to case-insensitive matching on User.username if input has no '@' or is a username
    4. Ensures user is active
    """
    if not input_str:
        return None

    raw = str(input_str).strip()
    if not raw:
        return None

    # Extract bracketed/parenthesized email if present
    bracket_match = re.search(r'<([^>]+)>|\(([^)]+)\)', raw)
    extracted = None
    if bracket_match:
        extracted = (bracket_match.group(1) or bracket_match.group(2) or "").strip()

    pattern_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw)
    candidate_email = extracted or (pattern_match.group(0) if pattern_match else raw)
    clean_email = candidate_email.strip().lower()

    # 1. Primary check: Case-insensitive email match
    user = User.query.filter(
        func.lower(func.trim(User.email)) == clean_email,
        User.is_active.is_(True)
    ).first()
    if user:
        return user

    # 2. Check full raw input as email
    raw_lower = raw.lower()
    user = User.query.filter(
        func.lower(func.trim(User.email)) == raw_lower,
        User.is_active.is_(True)
    ).first()
    if user:
        return user

    # 3. Check username match
    user = User.query.filter(
        func.lower(func.trim(User.username)) == raw_lower,
        User.is_active.is_(True)
    ).first()
    if user:
        return user

    # 4. Check name prefix if input was "username (email)" or "username <email>"
    name_prefix = re.split(r'[(<]', raw)[0].strip().lower()
    if name_prefix:
        user = User.query.filter(
            func.lower(func.trim(User.username)) == name_prefix,
            User.is_active.is_(True)
        ).first()
        if user:
            return user

    return None


def send_email(sender, recipient_email, subject, body, attachment_files=None, label=None):
    recipient = find_user_by_email_or_username(recipient_email)

    if not recipient:
        raise ValueError("Recipient account was not found. Please verify the email address.")

    if recipient.id == sender.id:
        raise ValueError("You cannot send an email to yourself.")

    inbox_email = Email(
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject=subject.strip() or "(No subject)",
        body=body,
        folder="inbox",
        is_read=False,
        label=label
    )

    sent_email = Email(
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject=subject.strip() or "(No subject)",
        body=body,
        folder="sent",
        is_read=True,
        label=label
    )

    db.session.add_all([inbox_email, sent_email])
    db.session.flush()

    # Process attachments
    if attachment_files:
        for file in attachment_files:
            file_meta = save_uploaded_attachment(file)
            if file_meta:
                # Add attachment to inbox email
                att_inbox = EmailAttachment(
                    email_id=inbox_email.id,
                    original_filename=file_meta["original_filename"],
                    stored_filename=file_meta["stored_filename"],
                    file_size=file_meta["file_size"],
                    mimetype=file_meta["mimetype"]
                )
                # Add attachment to sent email
                att_sent = EmailAttachment(
                    email_id=sent_email.id,
                    original_filename=file_meta["original_filename"],
                    stored_filename=file_meta["stored_filename"],
                    file_size=file_meta["file_size"],
                    mimetype=file_meta["mimetype"]
                )
                db.session.add_all([att_inbox, att_sent])

    # Send in-app notification to recipient
    notif = Notification(
        recipient_id=recipient.id,
        sender_id=sender.id,
        message=f"New email from {sender.username}: {subject[:50]}"
    )
    db.session.add(notif)

    db.session.commit()

    # Real-time WebSocket delivery to recipient across Cloudflare Tunnel & different networks
    try:
        from extensions import socketio
        socketio.emit(
            "new_email",
            {
                "id": inbox_email.id,
                "sender_name": sender.username,
                "sender_email": sender.email,
                "subject": inbox_email.subject,
                "body_preview": (inbox_email.body or "")[:80],
                "label": inbox_email.label,
                "created_at": inbox_email.created_at_iso or (inbox_email.created_at.strftime("%I:%M %p") if inbox_email.created_at else "Just now"),
                "created_at_iso": inbox_email.created_at_iso,
                "has_attachments": bool(attachment_files)
            },
            to=f"user_{recipient.id}"
        )

        socketio.emit(
            "new_notification",
            {
                "id": notif.id,
                "type": "email",
                "message": notif.message,
                "link": f"/email/view/{inbox_email.id}"
            },
            to=f"user_{recipient.id}"
        )

        # Update live unread badges
        unread_emails = Email.query.filter_by(recipient_id=recipient.id, folder="inbox", is_read=False).count()
        unread_notifs = Notification.query.filter_by(recipient_id=recipient.id, is_read=False).count()
        socketio.emit(
            "update_unread_counts",
            {
                "unread_emails": unread_emails,
                "unread_notifications": unread_notifs
            },
            to=f"user_{recipient.id}"
        )

        # Trigger Web Push for background delivery
        try:
            from notification_module.webpush_service import send_web_push
            user_profile = getattr(recipient, "profile", None)
            if user_profile is None or (user_profile.desktop_notifications_enabled and user_profile.email_notifications_enabled):
                send_web_push(
                    user_id=recipient.id,
                    title=f"New Email: {subject[:50]}",
                    body=f"From {sender.username}: {(inbox_email.body or '')[:80]}",
                    url=f"/email/view/{inbox_email.id}",
                    tag=f"email-{inbox_email.id}"
                )
        except Exception as push_err:
            current_app.logger.warning(f"WebPush email notification notice: {push_err}")
    except Exception as e:
        current_app.logger.warning(f"Real-time email socket emission error: {e}")

    return sent_email


def save_draft(sender, recipient_email, subject, body, draft_id=None, label=None, attachment_files=None):
    recipient = None
    if recipient_email:
        recipient = find_user_by_email_or_username(recipient_email)

    recipient_id = recipient.id if recipient else sender.id

    if draft_id:
        draft = Email.query.filter_by(
            id=draft_id,
            sender_id=sender.id,
            folder="drafts"
        ).first()

        if draft:
            draft.recipient_id = recipient_id
            draft.subject = subject.strip()
            draft.body = body
            draft.label = label
            db.session.commit()
            return draft

    draft = Email(
        sender_id=sender.id,
        recipient_id=recipient_id,
        subject=subject.strip(),
        body=body,
        folder="drafts",
        is_read=True,
        label=label
    )

    db.session.add(draft)
    db.session.flush()

    if attachment_files:
        for file in attachment_files:
            file_meta = save_uploaded_attachment(file)
            if file_meta:
                att = EmailAttachment(
                    email_id=draft.id,
                    original_filename=file_meta["original_filename"],
                    stored_filename=file_meta["stored_filename"],
                    file_size=file_meta["file_size"],
                    mimetype=file_meta["mimetype"]
                )
                db.session.add(att)

    db.session.commit()
    return draft
