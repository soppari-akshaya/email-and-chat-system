
from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from notification_module import notification_bp
from notification_module.models import Notification


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
