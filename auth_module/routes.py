import os
import uuid
from urllib.parse import urlparse
from flask import render_template, redirect, url_for, flash, request, current_app, send_from_directory, abort, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_

from extensions import db
from auth_module import auth_bp
from auth_module.forms import RegisterForm, LoginForm, ProfileForm, ChangePasswordForm
from auth_module.models import User, UserProfile
from auth_module.services import register_user
from email_module.models import Email
from chat_module.models import ConversationMember, ChatMessage


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    form = RegisterForm()

    if form.validate_on_submit():
        try:
            new_user = register_user(
                username=form.username.data,
                email=form.email.data,
                password=form.password.data
            )

            try:
                from extensions import socketio
                socketio.emit(
                    "new_user_registered",
                    {
                        "id": new_user.id,
                        "username": new_user.username,
                        "email": new_user.email,
                        "online_status": "offline",
                        "profile_image": new_user.profile_image_url
                    }
                )
            except Exception:
                pass

            flash("Your account has been created. Please log in.", "success")
            return redirect(url_for("auth.login"))

        except Exception:
            db.session.rollback()
            flash("Unable to create your account. Please try again.", "danger")

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        ident = form.email.data.strip().lower()
        user = User.query.filter(
            or_(
                func.lower(func.trim(User.email)) == ident,
                func.lower(func.trim(User.username)) == ident
            )
        ).first()

        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("Your account is currently inactive. Contact administrator.", "danger")
                return render_template("auth/login.html", form=form)

            user.online_status = "online"
            user.last_seen = User.query.filter_by(id=user.id).first().last_seen or User.query.get(user.id).created_at
            from auth_module.models import utc_now
            user.last_seen = utc_now()
            db.session.commit()

            from extensions import socketio
            socketio.emit(
                "user_status",
                {
                    "user_id": user.id,
                    "username": user.username,
                    "status": "online"
                }
            )

            login_user(user, remember=True)
            flash(f"Welcome back, {user.username}!", "success")

            next_page = request.args.get("next")
            if next_page:
                parsed_url = urlparse(next_page)
                if not parsed_url.netloc and next_page.startswith("/"):
                    return redirect(next_page)

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    user_id = current_user.id
    username = current_user.username
    current_user.online_status = "offline"
    from auth_module.models import utc_now
    current_user.last_seen = utc_now()
    db.session.commit()

    from chat_module.events import active_users
    if user_id in active_users:
        del active_users[user_id]

    from extensions import socketio
    socketio.emit(
        "user_status",
        {
            "user_id": user_id,
            "username": username,
            "status": "offline"
        }
    )

    logout_user()
    flash("You have been logged out safely.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if not current_user.profile:
        current_user.profile = UserProfile(user_id=current_user.id, full_name=current_user.username)
        db.session.commit()

    form = ProfileForm(
        full_name=current_user.profile.full_name or "",
        username=current_user.username,
        phone=current_user.profile.phone or "",
        bio=current_user.profile.bio or ""
    )
    password_form = ChangePasswordForm()

    if form.validate_on_submit() and "submit" in request.form:
        new_username = form.username.data.strip()
        current_user.username = new_username
        current_user.profile.full_name = form.full_name.data.strip() if form.full_name.data else ""
        current_user.profile.phone = form.phone.data.strip() if form.phone.data else ""
        current_user.profile.bio = form.bio.data.strip() if form.bio.data else ""

        # Notification preferences
        prefs = request.form.getlist("notifications")
        current_user.profile.notification_preferences = ",".join(prefs) if prefs else "none"
        current_user.profile.desktop_notifications_enabled = "desktop" in prefs
        current_user.profile.email_notifications_enabled = "email" in prefs
        current_user.profile.private_chat_notifications_enabled = "chat" in prefs
        current_user.profile.group_chat_notifications_enabled = "group" in prefs or "chat" in prefs
        current_user.profile.sound_enabled = "sound" in prefs

        # Avatar upload
        image_updated = False
        if form.profile_image.data and hasattr(form.profile_image.data, "filename") and form.profile_image.data.filename:
            image_file = form.profile_image.data
            ext = secure_filename(image_file.filename).rsplit(".", 1)[-1].lower()
            if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
                # Remove previous image from disk if one exists
                if current_user.profile.profile_image:
                    old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], "profiles", current_user.profile.profile_image)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass

                filename = f"avatar_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
                upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "profiles")
                os.makedirs(upload_dir, exist_ok=True)
                image_file.save(os.path.join(upload_dir, filename))
                current_user.profile.profile_image = filename
                image_updated = True

        try:
            db.session.commit()

            if image_updated:
                from extensions import socketio
                socketio.emit(
                    "profile_updated",
                    {
                        "user_id": current_user.id,
                        "username": current_user.username,
                        "profile_image": current_user.profile.profile_image
                    }
                )

            flash("Profile updated successfully!", "success")
            return redirect(url_for("auth.profile"))
        except Exception:
            db.session.rollback()
            flash("Error updating profile. Please try again.", "danger")

    # Statistics for profile
    emails_sent_count = Email.query.filter_by(sender_id=current_user.id, folder="sent").count()
    emails_received_count = Email.query.filter_by(recipient_id=current_user.id, folder="inbox").count()
    conversations_count = ConversationMember.query.filter_by(user_id=current_user.id).count()
    messages_sent_count = ChatMessage.query.filter_by(sender_id=current_user.id, is_deleted=False).count()

    current_prefs = []
    if current_user.profile.wants_desktop_notifs():
        current_prefs.append("desktop")
    if current_user.profile.wants_email_notifs():
        current_prefs.append("email")
    if current_user.profile.wants_chat_notifs():
        current_prefs.append("chat")
    if current_user.profile.wants_group_notifs():
        current_prefs.append("group")
    if current_user.profile.wants_sound():
        current_prefs.append("sound")

    return render_template(
        "auth/profile.html",
        form=form,
        password_form=password_form,
        emails_sent_count=emails_sent_count,
        emails_received_count=emails_received_count,
        conversations_count=conversations_count,
        messages_sent_count=messages_sent_count,
        current_prefs=current_prefs
    )


@auth_bp.route("/profile/remove-image", methods=["POST"])
@login_required
def remove_profile_image():
    import gc
    gc.collect()
    if current_user.profile and current_user.profile.profile_image:
        old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], "profiles", current_user.profile.profile_image)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        current_user.profile.profile_image = None
        db.session.commit()

        from extensions import socketio
        socketio.emit(
            "profile_updated",
            {
                "user_id": current_user.id,
                "username": current_user.username,
                "profile_image": None
            }
        )

        flash("Profile picture removed successfully.", "info")
    return redirect(url_for("auth.profile"))


@auth_bp.route("/user/<int:user_id>")
@login_required
def view_user(user_id):
    if user_id == current_user.id:
        return redirect(url_for("auth.profile"))

    target_user = User.query.filter_by(id=user_id, is_active=True).first_or_404()
    emails_sent_count = Email.query.filter_by(sender_id=target_user.id, folder="sent").count()
    conversations_count = ConversationMember.query.filter_by(user_id=target_user.id).count()

    from chat_module.events import active_users
    is_online = (target_user.id in active_users) or (target_user.online_status == "online")

    return render_template(
        "auth/view_user.html",
        target_user=target_user,
        is_online=is_online,
        emails_sent_count=emails_sent_count,
        conversations_count=conversations_count
    )



@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    password_form = ChangePasswordForm()

    if password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("auth.profile"))

        current_user.set_password(password_form.new_password.data)
        db.session.commit()
        flash("Your password has been changed successfully.", "success")
        return redirect(url_for("auth.profile"))

    for field, errors in password_form.errors.items():
        for error in errors:
            flash(f"Password error: {error}", "danger")

    return redirect(url_for("auth.profile"))


@auth_bp.route("/profile-image/<int:user_id>")
def profile_image(user_id):
    user = db.session.get(User, user_id)
    if not user or not user.profile or not user.profile.profile_image:
        abort(404)

    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "profiles")
    file_path = os.path.join(upload_dir, user.profile.profile_image)
    if not os.path.exists(file_path):
        abort(404)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    from io import BytesIO
    from flask import send_file
    ext = user.profile.profile_image.rsplit(".", 1)[-1].lower() if "." in user.profile.profile_image else "png"
    mime = f"image/{ext}" if ext in ["png", "jpg", "jpeg", "gif", "webp"] else "application/octet-stream"
    return send_file(BytesIO(file_bytes), mimetype=mime)



# FIREBASE AUTHENTICATION (FORGOT PASSWORD & GOOGLE SIGN-IN)


@auth_bp.route("/firebase-config", methods=["GET"])
def firebase_config():
    """Return public Firebase web configuration for client-side JavaScript SDK."""
    from auth_module.firebase_service import get_firebase_client_config
    return jsonify(get_firebase_client_config())


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Handle password reset requests via Firebase Authentication."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email or "@" not in email:
            flash("Please provide a valid registered email address.", "danger")
            return render_template("auth/forgot_password.html")

        # Security best practice: generic confirmation prevents user enumeration
        flash("If an account with that email exists, password reset instructions have been sent. Please check your inbox and spam folders.", "success")
        return render_template("auth/forgot_password.html", email_sent=True)

    return render_template("auth/forgot_password.html")


@auth_bp.route("/google-login", methods=["POST"])
def google_login():
    """
    Authenticate or register users via Google Sign-In using Firebase Authentication.
    Verifies the Firebase ID token cryptographically on the Flask backend.
    """
    data = request.get_json(silent=True) or {}
    id_token = data.get("id_token") or data.get("idToken") or data.get("token")
    if not id_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            id_token = auth_header[7:].strip()

    if not id_token:
        current_app.logger.warning("Google login attempted without ID token in request body or headers.")
        return jsonify({"success": False, "error": "Missing Firebase ID token."}), 400

    from auth_module.firebase_service import verify_firebase_id_token
    user_info = verify_firebase_id_token(id_token)
    if not user_info:
        current_app.logger.warning("Google login ID token verification rejected.")
        return jsonify({"success": False, "error": "Unable to verify Google credentials. Please try again."}), 401

    email = user_info.get("email", "").strip().lower()
    if not email:
        return jsonify({"success": False, "error": "No verified email associated with this Google account."}), 400

    user = User.query.filter(func.lower(func.trim(User.email)) == email).first()

    if not user:
        # Create a new user account linked with Google Authentication
        import re
        import secrets

        raw_name = (user_info.get("name") or email.split("@")[0]).strip()
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "", raw_name) or "user"
        username = cleaned
        counter = 1
        while User.query.filter(func.lower(User.username) == username.lower()).first():
            username = f"{cleaned}{counter}"
            counter += 1

        user = User(
            username=username,
            email=email,
            role="user",
            is_active=True,
            is_verified=True,
            online_status="online"
        )
        user.set_password(secrets.token_urlsafe(32))
        user.profile = UserProfile(
            full_name=user_info.get("name") or username,
            bio="Joined via Google Authentication",
            google_id=user_info.get("uid")
        )
        db.session.add(user)
        db.session.commit()

        # Notify active sessions of new registered user
        try:
            from extensions import socketio
            socketio.emit(
                "new_user_registered",
                {
                    "id": user.id,
                    "user_id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "online_status": "online",
                    "avatar_url": user_info.get("picture")
                }
            )
        except Exception:
            pass
    else:
        if not user.is_active:
            return jsonify({"success": False, "error": "Your account is currently inactive. Contact administrator."}), 403

        user.online_status = "online"
        from auth_module.models import utc_now
        user.last_seen = utc_now()
        if not user.profile:
            user.profile = UserProfile(user_id=user.id, full_name=user.username)
        if user_info.get("uid") and not user.profile.google_id:
            user.profile.google_id = user_info.get("uid")
        db.session.commit()

    from extensions import socketio
    socketio.emit(
        "user_status",
        {
            "user_id": user.id,
            "username": user.username,
            "status": "online"
        }
    )

    login_user(user, remember=True)
    flash(f"Welcome back, {user.username}!", "success")
    return jsonify({"success": True, "redirect_url": url_for("dashboard")})

