from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from notification_module import notification_bp
from notification_module.models import Notification, PushSubscription
from notification_module.webpush_service import get_vapid_public_key, send_web_push


@notification_bp.route("/")
@login_required
def index():
    notifications = Notification.query.filter_by(
        recipient_id=current_user.id
    ).order_by(
        Notification.created_at.desc()
    ).all()

    unread_count = Notification.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).count()

    return render_template(
        "notifications/index.html",
        notifications=notifications,
        unread_count=unread_count
    )


@notification_bp.route("/read/<int:notification_id>", methods=["POST"])
@login_required
def mark_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id,
        recipient_id=current_user.id
    ).first_or_404()

    notification.is_read = True
    db.session.commit()

    flash("Notification marked as read.", "success")
    return redirect(url_for("notification.index"))


@notification_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    Notification.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).update({"is_read": True})

    db.session.commit()

    flash("All notifications marked as read.", "success")
    return redirect(url_for("notification.index"))



# WEB PUSH & DESKTOP NOTIFICATION ENDPOINTS


@notification_bp.route("/vapid-public-key", methods=["GET"])
def vapid_public_key():
    """Return the VAPID public key needed by browser to subscribe to push notifications."""
    return jsonify({
        "publicKey": get_vapid_public_key()
    })


@notification_bp.route("/subscribe", methods=["POST"])
@login_required
def subscribe_push():
    """Save or update browser Web Push subscription for the authenticated user."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"success": False, "error": "Incomplete subscription parameters"}), 400

    try:
        # Check if this endpoint already exists
        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if existing:
            existing.user_id = current_user.id
            existing.p256dh = p256dh
            existing.auth = auth
        else:
            sub = PushSubscription(
                user_id=current_user.id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth
            )
            db.session.add(sub)
        db.session.commit()
        return jsonify({"success": True, "message": "Subscribed to Web Push notifications."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@notification_bp.route("/unsubscribe", methods=["POST"])
@login_required
def unsubscribe_push():
    """Remove browser Web Push subscription for the authenticated user."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")

    if not endpoint:
        return jsonify({"success": False, "error": "Endpoint is required"}), 400

    try:
        PushSubscription.query.filter_by(
            user_id=current_user.id,
            endpoint=endpoint
        ).delete()
        db.session.commit()
        return jsonify({"success": True, "message": "Unsubscribed successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@notification_bp.route("/test-desktop", methods=["POST"])
@login_required
def test_desktop_notification():
    """Trigger an immediate real test notification via Web Push and Socket.IO."""
    title = "🔔 ConnectHub Desktop Notification"
    body = f"Hello, {current_user.username}! Real Windows Desktop Notifications are active and connected."
    link = url_for("dashboard")

    # Send background push
    push_sent = send_web_push(current_user.id, title, body, link, tag="test_notification")

    # Also emit Socket.IO notification for instant active tab display
    try:
        from extensions import socketio
        socketio.emit(
            "new_notification",
            {
                "type": "system",
                "message": body,
                "link": link
            },
            to=f"user_{current_user.id}"
        )
    except Exception:
        pass

    return jsonify({
        "success": True,
        "push_sent": push_sent,
        "message": "Test notification triggered. You should see a native Windows notification now!"
    })


@notification_bp.route("/settings", methods=["GET", "POST"])
@login_required
def notification_settings():
    """View and update persistent user notification preferences."""
    profile = current_user.profile
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form

        profile.desktop_notifications_enabled = bool(data.get("desktop_notifications_enabled") in (True, "true", "1", "on"))
        profile.email_notifications_enabled = bool(data.get("email_notifications_enabled") in (True, "true", "1", "on"))
        profile.private_chat_notifications_enabled = bool(data.get("private_chat_notifications_enabled") in (True, "true", "1", "on"))
        profile.group_chat_notifications_enabled = bool(data.get("group_chat_notifications_enabled") in (True, "true", "1", "on"))
        profile.sound_enabled = bool(data.get("sound_enabled") in (True, "true", "1", "on"))

        # Keep legacy string in sync
        prefs = []
        if profile.email_notifications_enabled:
            prefs.append("email")
        if profile.private_chat_notifications_enabled or profile.group_chat_notifications_enabled:
            prefs.append("chat")
        if profile.sound_enabled:
            prefs.append("sound")
        profile.notification_preferences = ",".join(prefs) or "none"

        db.session.commit()
        if request.is_json:
            return jsonify({"success": True, "message": "Notification preferences updated."})
        flash("Notification settings updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    return jsonify({
        "desktop_notifications_enabled": profile.wants_desktop_notifs(),
        "email_notifications_enabled": profile.wants_email_notifs(),
        "private_chat_notifications_enabled": profile.wants_chat_notifs(),
        "group_chat_notifications_enabled": profile.wants_group_notifs(),
        "sound_enabled": profile.wants_sound()
    })
