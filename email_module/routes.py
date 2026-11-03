
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from extensions import db
from email_module import email_bp
from email_module.models import Email
from email_module.services import send_email, save_draft


def user_email_query():
    return Email.query.filter(
        or_(
            Email.sender_id == current_user.id,
            Email.recipient_id == current_user.id
        )
    )


@email_bp.route("/")
@login_required
def inbox():
    search = request.args.get("q", "").strip()

    query = Email.query.filter_by(
        recipient_id=current_user.id,
        folder="inbox"
    )

    if search:
        query = query.filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%")
            )
        )

    emails = query.order_by(Email.created_at.desc()).all()
    return render_template("email/inbox.html", emails=emails, search=search)


@email_bp.route("/sent")
@login_required
def sent():
    emails = Email.query.filter_by(
        sender_id=current_user.id,
        folder="sent"
    ).order_by(Email.created_at.desc()).all()

    return render_template("email/sent.html", emails=emails)


@email_bp.route("/drafts")
@login_required
def drafts():
    emails = Email.query.filter_by(
        sender_id=current_user.id,
        folder="drafts"
    ).order_by(Email.created_at.desc()).all()

    return render_template("email/drafts.html", emails=emails)


@email_bp.route("/trash")
@login_required
def trash():
    emails = user_email_query().filter_by(
        folder="trash"
    ).order_by(Email.created_at.desc()).all()

    return render_template("email/trash.html", emails=emails)


@email_bp.route("/compose", methods=["GET", "POST"])
@login_required
def compose():
    if request.method == "POST":
        recipient = request.form.get("recipient", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "")

        if not recipient or not body.strip():
            flash("Please enter a recipient and message.", "warning")
            return render_template("email/compose.html")

        try:
            send_email(current_user, recipient, subject, body)
            flash("Email sent successfully!", "success")
            return redirect(url_for("email.sent"))
        except ValueError as error:
            flash(str(error), "danger")

    return render_template("email/compose.html")


@email_bp.route("/save-draft", methods=["POST"])
@login_required
def save_email_draft():
    recipient = request.form.get("recipient", "").strip()
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "")

    save_draft(current_user, recipient, subject, body)

    flash("Draft saved successfully.", "success")
    return redirect(url_for("email.drafts"))


@email_bp.route("/view/<int:email_id>")
@login_required
def view_email(email_id):
    email = Email.query.filter_by(
        id=email_id,
        recipient_id=current_user.id,
        folder="inbox"
    ).first_or_404()

    email.is_read = True
    db.session.commit()

    return render_template("email/view.html", email=email)


@email_bp.route("/sent/view/<int:email_id>")
@login_required
def view_sent_email(email_id):
    email = Email.query.filter_by(
        id=email_id,
        sender_id=current_user.id,
        folder="sent"
    ).first_or_404()

    return render_template("email/view.html", email=email)


@email_bp.route("/delete/<int:email_id>", methods=["POST"])
@login_required
def delete_email(email_id):
    email = user_email_query().filter_by(id=email_id).first_or_404()

    if email.folder == "trash":
        flash("This email is already in Trash.", "warning")
    else:
        email.folder = "trash"
        db.session.commit()
        flash("Email moved to Trash.", "success")

    return redirect(request.referrer or url_for("email.inbox"))


@email_bp.route("/restore/<int:email_id>", methods=["POST"])
@login_required
def restore_email(email_id):
    email = user_email_query().filter_by(
        id=email_id,
        folder="trash"
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
    email = user_email_query().filter_by(
        id=email_id,
        folder="trash"
    ).first_or_404()

    db.session.delete(email)
    db.session.commit()

    flash("Email permanently deleted.", "success")
    return redirect(url_for("email.trash"))


@email_bp.route("/star/<int:email_id>", methods=["POST"])
@login_required
def toggle_star(email_id):
    email = user_email_query().filter_by(id=email_id).first_or_404()

    email.is_starred = not email.is_starred
    db.session.commit()

    flash("Star status updated.", "success")
    return redirect(request.referrer or url_for("email.inbox"))


@email_bp.route("/important/<int:email_id>", methods=["POST"])
@login_required
def toggle_important(email_id):
    email = user_email_query().filter_by(id=email_id).first_or_404()

    email.is_important = not email.is_important
    db.session.commit()

    flash("Important status updated.", "success")
    return redirect(request.referrer or url_for("email.inbox"))


@email_bp.route("/starred")
@login_required
def starred():
    emails = user_email_query().filter_by(
        is_starred=True
    ).filter(
        Email.folder != "trash"
    ).order_by(Email.created_at.desc()).all()

    return render_template("email/starred.html", emails=emails)


@email_bp.route("/important")
@login_required
def important():
    emails = user_email_query().filter_by(
        is_important=True
    ).filter(
        Email.folder != "trash"
    ).order_by(Email.created_at.desc()).all()

    return render_template("email/important.html", emails=emails)
