import os
import math
from flask import render_template, request, redirect, url_for, flash, current_app, send_file, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from extensions import db
from auth_module.models import User
from email_module import email_bp
from email_module.models import Email, EmailAttachment
from email_module.services import send_email, save_draft


PER_PAGE = 15


def get_email_counts():
    """Returns counts for sidebar badge indicators."""
    inbox_unread = Email.query.filter_by(recipient_id=current_user.id, folder="inbox", is_read=False).count()
    starred_count = Email.query.filter(
        Email.is_starred == True,
        Email.folder != "trash",
        or_(
            and_(Email.recipient_id == current_user.id, Email.folder == "inbox"),
            and_(Email.sender_id == current_user.id, Email.folder == "sent")
        )
    ).count()
    drafts_count = Email.query.filter_by(sender_id=current_user.id, folder="drafts").count()
    important_count = Email.query.filter(
        Email.is_important == True,
        Email.folder != "trash",
        or_(
            and_(Email.recipient_id == current_user.id, Email.folder == "inbox"),
            and_(Email.sender_id == current_user.id, Email.folder == "sent")
        )
    ).count()
    trash_count = Email.query.filter(
        Email.folder == "trash",
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).count()

    return {
        "inbox_unread": inbox_unread,
        "starred": starred_count,
        "drafts": drafts_count,
        "important": important_count,
        "trash": trash_count
    }


def paginate_query(query, page, per_page=PER_PAGE):
    total = query.count()
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total, total_pages, page


@email_bp.route("/")
@login_required
def inbox():
    search = request.args.get("q", "").strip()
    label_filter = request.args.get("label", "").strip()
    unread_only = request.args.get("unread") == "1"
    page = request.args.get("page", 1, type=int)

    query = Email.query.filter_by(recipient_id=current_user.id, folder="inbox")

    if unread_only:
        query = query.filter_by(is_read=False)

    if label_filter:
        query = query.filter_by(label=label_filter)

    if search:
        query = query.join(User, Email.sender_id == User.id).filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Email.created_at.desc())
    emails, total, total_pages, page = paginate_query(query, page)

    return render_template(
        "email/inbox.html",
        emails=emails,
        total=total,
        total_pages=total_pages,
        page=page,
        search=search,
        current_label=label_filter,
        unread_only=unread_only,
        counts=get_email_counts()
    )


@email_bp.route("/sent")
@login_required
def sent():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Email.query.filter_by(sender_id=current_user.id, folder="sent")

    if search:
        query = query.join(User, Email.recipient_id == User.id).filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Email.created_at.desc())
    emails, total, total_pages, page = paginate_query(query, page)

    return render_template(
        "email/sent.html",
        emails=emails,
        total=total,
        total_pages=total_pages,
        page=page,
        search=search,
        counts=get_email_counts()
    )


@email_bp.route("/drafts")
@login_required
def drafts():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Email.query.filter_by(sender_id=current_user.id, folder="drafts")

    if search:
        query = query.filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Email.created_at.desc())
    emails, total, total_pages, page = paginate_query(query, page)

    return render_template(
        "email/drafts.html",
        emails=emails,
        total=total,
        total_pages=total_pages,
        page=page,
        search=search,
        counts=get_email_counts()
    )


@email_bp.route("/trash")
@login_required
def trash():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Email.query.filter(
        Email.folder == "trash",
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    )

    if search:
        query = query.filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Email.created_at.desc())
    emails, total, total_pages, page = paginate_query(query, page)

    return render_template(
        "email/trash.html",
        emails=emails,
        total=total,
        total_pages=total_pages,
        page=page,
        search=search,
        counts=get_email_counts()
    )


@email_bp.route("/starred")
@login_required
def starred():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Email.query.filter(
        Email.is_starred == True,
        Email.folder != "trash",
        or_(
            and_(Email.recipient_id == current_user.id, Email.folder == "inbox"),
            and_(Email.sender_id == current_user.id, Email.folder == "sent")
        )
    )

    if search:
        query = query.filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Email.created_at.desc())
    emails, total, total_pages, page = paginate_query(query, page)

    return render_template(
        "email/starred.html",
        emails=emails,
        total=total,
        total_pages=total_pages,
        page=page,
        search=search,
        counts=get_email_counts()
    )


@email_bp.route("/important")
@login_required
def important():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Email.query.filter(
        Email.is_important == True,
        Email.folder != "trash",
        or_(
            and_(Email.recipient_id == current_user.id, Email.folder == "inbox"),
            and_(Email.sender_id == current_user.id, Email.folder == "sent")
        )
    )

    if search:
        query = query.filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%")
            )
        )

    query = query.order_by(Email.created_at.desc())
    emails, total, total_pages, page = paginate_query(query, page)

    return render_template(
        "email/important.html",
        emails=emails,
        total=total,
        total_pages=total_pages,
        page=page,
        search=search,
        counts=get_email_counts()
    )


@email_bp.route("/compose", methods=["GET", "POST"])
@login_required
def compose():
    # Check query params for reply, forward, draft, or direct recipient
    reply_id = request.args.get("reply_to", type=int)
    forward_id = request.args.get("forward", type=int)
    draft_id = request.args.get("draft_id", type=int)
    direct_to = request.args.get("to", "").strip()

    prefill = {
        "recipient": direct_to,
        "subject": "",
        "body": "",
        "label": "",
        "draft_id": None
    }

    if draft_id:
        draft = Email.query.filter_by(id=draft_id, sender_id=current_user.id, folder="drafts").first()
        if draft:
            recipient_user = User.query.get(draft.recipient_id) if draft.recipient_id != current_user.id else None
            prefill["recipient"] = recipient_user.email if recipient_user else ""
            prefill["subject"] = draft.subject
            prefill["body"] = draft.body
            prefill["label"] = draft.label or ""
            prefill["draft_id"] = draft.id

    elif reply_id:
        orig = Email.query.filter(
            Email.id == reply_id,
            or_(Email.sender_id == current_user.id, Email.recipient_id == current_user.id)
        ).first()
        if orig:
            reply_target = orig.sender if orig.sender_id != current_user.id else orig.recipient
            prefill["recipient"] = reply_target.email if reply_target else ""
            prefill["subject"] = f"Re: {orig.subject}" if not orig.subject.startswith("Re:") else orig.subject
            prefill["body"] = f"\n\n\n--- On {orig.created_at.strftime('%d %b %Y at %I:%M %p')}, {orig.sender.username} wrote: ---\n> {orig.body.replace(chr(10), chr(10) + '> ')}"

    elif forward_id:
        orig = Email.query.filter(
            Email.id == forward_id,
            or_(Email.sender_id == current_user.id, Email.recipient_id == current_user.id)
        ).first()
        if orig:
            prefill["subject"] = f"Fwd: {orig.subject}" if not orig.subject.startswith("Fwd:") else orig.subject
            prefill["body"] = f"\n\n\n--- Forwarded Message ---\nFrom: {orig.sender.email}\nDate: {orig.created_at.strftime('%d %b %Y %I:%M %p')}\nSubject: {orig.subject}\n\n{orig.body}"

    if request.method == "POST":
        action = request.form.get("action", "send")
        recipient = request.form.get("recipient", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "")
        label = request.form.get("label", "").strip() or None
        existing_draft_id = request.form.get("draft_id", type=int)
        attachments = request.files.getlist("attachments")

        if action == "draft":
            save_draft(current_user, recipient, subject, body, draft_id=existing_draft_id, label=label, attachment_files=attachments)
            flash("Draft saved successfully.", "success")
            return redirect(url_for("email.drafts"))

        if not recipient:
            flash("Please specify a recipient email.", "warning")
            prefill.update({"recipient": recipient, "subject": subject, "body": body, "label": label or ""})
            return render_template("email/compose.html", prefill=prefill, counts=get_email_counts(), registered_users=User.query.filter(User.id != current_user.id, or_(User.is_active.is_(True), User.is_active == 1)).order_by(User.username).all())

        try:
            send_email(current_user, recipient, subject, body, attachment_files=attachments, label=label)
            # Delete existing draft if this was sent from a draft
            if existing_draft_id:
                draft = Email.query.filter_by(id=existing_draft_id, sender_id=current_user.id, folder="drafts").first()
                if draft:
                    db.session.delete(draft)
                    db.session.commit()

            flash("Email sent successfully!", "success")
            return redirect(url_for("email.sent"))

        except ValueError as error:
            flash(str(error), "danger")
            prefill.update({"recipient": recipient, "subject": subject, "body": body, "label": label or ""})

    registered_users = User.query.filter(User.id != current_user.id, or_(User.is_active.is_(True), User.is_active == 1)).order_by(User.username).all()

    return render_template(
        "email/compose.html",
        prefill=prefill,
        counts=get_email_counts(),
        registered_users=registered_users
    )


@email_bp.route("/save-draft", methods=["POST"])
@login_required
def save_email_draft():
    recipient = request.form.get("recipient", "").strip()
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "")
    label = request.form.get("label", "").strip() or None
    draft_id = request.form.get("draft_id", type=int)

    draft = save_draft(current_user, recipient, subject, body, draft_id=draft_id, label=label)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"status": "success", "draft_id": draft.id})

    flash("Draft saved successfully.", "success")
    return redirect(url_for("email.drafts"))


@email_bp.route("/view/<int:email_id>")
@login_required
def view_email(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).first_or_404()

    # If recipient views unread email, mark as read
    if email.recipient_id == current_user.id and not email.is_read:
        email.is_read = True
        db.session.commit()

    return render_template(
        "email/view_email.html",
        email=email,
        counts=get_email_counts()
    )


@email_bp.route("/sent/view/<int:email_id>")
@login_required
def view_sent_email(email_id):
    return redirect(url_for("email.view_email", email_id=email_id))


@email_bp.route("/attachment/<int:attachment_id>/download")
@login_required
def download_attachment(attachment_id):
    attachment = EmailAttachment.query.get_or_404(attachment_id)
    email = attachment.email

    if email.sender_id != current_user.id and email.recipient_id != current_user.id:
        abort(403)

    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "email_attachments")
    file_path = os.path.join(folder, attachment.stored_filename)

    if not os.path.isfile(file_path):
        abort(404)

    inline = request.args.get("inline") == "1" and attachment.mimetype and attachment.mimetype.startswith("image/")

    return send_file(
        file_path,
        as_attachment=not inline,
        download_name=attachment.original_filename,
        mimetype=attachment.mimetype or "application/octet-stream"
    )


@email_bp.route("/delete/<int:email_id>", methods=["POST"])
@login_required
def delete_email(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).first_or_404()

    if email.folder == "trash":
        flash("Email is already in Trash.", "warning")
    else:
        email.folder = "trash"
        db.session.commit()
        flash("Email moved to Trash.", "success")

    return redirect(request.referrer or url_for("email.inbox"))


@email_bp.route("/restore/<int:email_id>", methods=["POST"])
@login_required
def restore_email(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        Email.folder == "trash",
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).first_or_404()

    if email.sender_id == current_user.id and email.recipient_id == current_user.id:
        email.folder = "drafts"
    elif email.sender_id == current_user.id:
        email.folder = "sent"
    else:
        email.folder = "inbox"

    db.session.commit()
    flash("Email restored successfully.", "success")
    return redirect(url_for("email.trash"))


@email_bp.route("/permanent-delete/<int:email_id>", methods=["POST"])
@login_required
def permanent_delete_email(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        Email.folder == "trash",
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).first_or_404()

    db.session.delete(email)
    db.session.commit()
    flash("Email permanently deleted.", "success")
    return redirect(url_for("email.trash"))


@email_bp.route("/star/<int:email_id>", methods=["POST"])
@login_required
def toggle_star(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).first_or_404()

    if email.folder == "trash":
        flash("Emails in Trash cannot be starred.", "warning")
    else:
        email.is_starred = not email.is_starred
        db.session.commit()
        flash("Email star status updated.", "success")

    return redirect(request.referrer or url_for("email.inbox"))


@email_bp.route("/important/<int:email_id>", methods=["POST"])
@login_required
def toggle_important(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).first_or_404()

    if email.folder == "trash":
        flash("Emails in Trash cannot be marked important.", "warning")
    else:
        email.is_important = not email.is_important
        db.session.commit()
        flash("Email importance updated.", "success")

    return redirect(request.referrer or url_for("email.inbox"))


@email_bp.route("/read-toggle/<int:email_id>", methods=["POST"])
@login_required
def toggle_read(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        Email.recipient_id == current_user.id
    ).first_or_404()

    email.is_read = not email.is_read
    db.session.commit()
    flash("Email status updated.", "success")
    return redirect(request.referrer or url_for("email.inbox"))


@email_bp.route("/set-label/<int:email_id>", methods=["POST"])
@login_required
def set_label(email_id):
    email = Email.query.filter(
        Email.id == email_id,
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    ).first_or_404()

    new_label = request.form.get("label", "").strip() or None
    email.label = new_label
    db.session.commit()
    flash(f"Label updated to {new_label if new_label else 'None'}.", "success")
    return redirect(request.referrer or url_for("email.inbox"))
