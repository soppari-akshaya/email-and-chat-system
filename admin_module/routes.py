import os
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from extensions import db
from auth_module.models import User
from email_module.models import Email
from chat_module.models import Conversation, ChatMessage
from admin_module import admin_bp
from admin_module.services import get_system_stats


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in first.", "warning")
            return redirect(url_for("auth.login"))
        if current_user.role != "admin":
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    stats = get_system_stats(current_app.config["UPLOAD_FOLDER"])
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_emails = Email.query.order_by(Email.created_at.desc()).limit(5).all()
    recent_messages = ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(5).all()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_users=recent_users,
        recent_emails=recent_emails,
        recent_messages=recent_messages
    )


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    search = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = User.query

    if search:
        query = query.filter(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    if role_filter:
        query = query.filter_by(role=role_filter)

    if status_filter == "active":
        query = query.filter_by(is_active=True)
    elif status_filter == "inactive":
        query = query.filter_by(is_active=False)

    users_list = query.order_by(User.created_at.desc()).all()

    return render_template(
        "admin/users.html",
        users=users_list,
        search=search,
        role_filter=role_filter,
        status_filter=status_filter
    )


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@login_required
@admin_required
def toggle_user_status(user_id):
    if user_id == current_user.id:
        flash("You cannot deactivate your own admin account.", "warning")
        return redirect(url_for("admin.users"))

    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    user.is_active = not user.is_active
    db.session.commit()
    flash(f"User {user.username} is now {'Active' if user.is_active else 'Deactivated'}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle-role", methods=["POST"])
@login_required
@admin_required
def toggle_user_role(user_id):
    if user_id == current_user.id:
        flash("You cannot change your own admin role.", "warning")
        return redirect(url_for("admin.users"))

    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    user.role = "admin" if user.role == "user" else "user"
    db.session.commit()
    flash(f"User {user.username} role changed to {user.role.upper()}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.users"))

    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"User {username} and associated records have been permanently deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/emails")
@login_required
@admin_required
def emails():
    search = request.args.get("q", "").strip()
    folder_filter = request.args.get("folder", "").strip()

    query = Email.query

    if search:
        query = query.filter(
            or_(
                Email.subject.ilike(f"%{search}%"),
                Email.body.ilike(f"%{search}%")
            )
        )

    if folder_filter:
        query = query.filter_by(folder=folder_filter)

    emails_list = query.order_by(Email.created_at.desc()).limit(100).all()

    return render_template(
        "admin/emails.html",
        emails=emails_list,
        search=search,
        folder_filter=folder_filter
    )


@admin_bp.route("/emails/<int:email_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_email(email_id):
    email = db.session.get(Email, email_id)
    if not email:
        abort(404)

    db.session.delete(email)
    db.session.commit()
    flash("Email deleted by administrator.", "success")
    return redirect(url_for("admin.emails"))


@admin_bp.route("/chats")
@login_required
@admin_required
def chats():
    conversations = Conversation.query.order_by(Conversation.created_at.desc()).all()
    return render_template("admin/chats.html", conversations=conversations)


@admin_bp.route("/chats/<int:conversation_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_chat(conversation_id):
    conversation = db.session.get(Conversation, conversation_id)
    if not conversation:
        abort(404)

    db.session.delete(conversation)
    db.session.commit()
    flash("Conversation deleted by administrator.", "success")
    return redirect(url_for("admin.chats"))

