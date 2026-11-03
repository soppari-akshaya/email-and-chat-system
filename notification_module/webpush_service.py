import json
import logging
from flask import current_app
from extensions import db
from notification_module.models import PushSubscription

logger = logging.getLogger(__name__)


def get_vapid_public_key():
    """Retrieve the application's VAPID public key for Web Push."""
    try:
        return current_app.config.get(
            "VAPID_PUBLIC_KEY",
            "BHHyoMW8ErugleGfWh1e3l7Qhc3koZBWHk17Irb6XyCRv6Ylw3UpUI8k6j0z-grzWOQcT87G1gV8yIrfxZylA7Y"
        )
    except RuntimeError:
        return "BHHyoMW8ErugleGfWh1e3l7Qhc3koZBWHk17Irb6XyCRv6Ylw3UpUI8k6j0z-grzWOQcT87G1gV8yIrfxZylA7Y"


def get_vapid_private_key():
    """Retrieve the application's VAPID private key."""
    try:
        return current_app.config.get(
            "VAPID_PRIVATE_KEY",
            "m5_PA4iJi-JDO3-RVL-GbTo8fnOVe7YjGJucangq52g"
        )
    except RuntimeError:
        return "m5_PA4iJi-JDO3-RVL-GbTo8fnOVe7YjGJucangq52g"


def send_web_push(user_id, title, body, url="/", tag=None):
    """
    Deliver a background Web Push notification to all active browser push subscriptions for a user.
    Automatically purges expired or invalidated subscriptions (HTTP 404 / 410).
    """
    try:
        import pywebpush
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush is not installed; background web push skipped.")
        return False

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        return False

    private_key = get_vapid_private_key()
    public_key = get_vapid_public_key()
    try:
        claim_email = current_app.config.get("VAPID_CLAIM_EMAIL", "mailto:admin@connecthub.com")
    except RuntimeError:
        claim_email = "mailto:admin@connecthub.com"

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag or "connecthub-notif",
        "icon": "/static/icons/icon-192.png",
        "badge": "/static/icons/badge-72.png"
    })

    sent_any = False
    to_delete = []

    for sub in subscriptions:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth": sub.auth
            }
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": claim_email}
            )
            sent_any = True
        except WebPushException as ex:
            # 404 Not Found or 410 Gone indicates the browser has unsubscribed or subscription expired
            response = getattr(ex, "response", None)
            status_code = getattr(response, "status_code", None) if response else None
            if status_code in (404, 410):
                logger.info(f"Removing expired push subscription {sub.id} (status {status_code}).")
                to_delete.append(sub)
            else:
                logger.warning(f"Web push delivery failed for subscription {sub.id}: {ex}")
        except Exception as e:
            logger.warning(f"Unexpected web push exception for user {user_id}: {e}")

    if to_delete:
        try:
            for s in to_delete:
                db.session.delete(s)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Error purging expired subscriptions: {e}")

    return sent_any

