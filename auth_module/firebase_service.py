import os
import json
import logging
import urllib.request
import urllib.parse
from flask import current_app

logger = logging.getLogger(__name__)

_firebase_initialized = False


def initialize_firebase_admin(app=None):
    """Safely initialize Firebase Admin SDK if credentials or project ID are provided."""
    global _firebase_initialized
    if _firebase_initialized:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_initialized = True
            return True

        cert_path = None
        if app and "FIREBASE_SERVICE_ACCOUNT_KEY" in app.config:
            cert_path = app.config["FIREBASE_SERVICE_ACCOUNT_KEY"]
        else:
            cert_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

        cert_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

        if cert_path and os.path.exists(cert_path):
            cred = credentials.Certificate(cert_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("Firebase Admin SDK initialized successfully via certificate file.")
            return True
        elif cert_json:
            cred_dict = json.loads(cert_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("Firebase Admin SDK initialized successfully via JSON credentials.")
            return True
        else:
            project_id = (app.config.get("FIREBASE_PROJECT_ID") if app else None) or os.getenv("FIREBASE_PROJECT_ID")
            if project_id:
                try:
                    firebase_admin.initialize_app(options={"projectId": project_id})
                    _firebase_initialized = True
                    logger.info(f"Firebase Admin SDK initialized with projectId '{project_id}'.")
                    return True
                except Exception as ex:
                    logger.warning(f"Firebase default app init warning: {ex}")
    except Exception as e:
        logger.warning(f"Firebase Admin SDK initialization skipped or encountered: {e}")

    return False


def verify_firebase_id_token(id_token):
    """
    Verify an incoming Firebase ID token from Google Sign-In.
    Uses Firebase Admin SDK with automatic fallback to Google tokeninfo API.
    Returns decoded user dictionary or None.
    """
    if not id_token or not isinstance(id_token, str):
        return None

    id_token = id_token.strip()
    if not id_token:
        return None

    # 1. Try Firebase Admin SDK verification
    try:
        initialize_firebase_admin()
        import firebase_admin
        from firebase_admin import auth as fb_auth

        if firebase_admin._apps:
            decoded = fb_auth.verify_id_token(id_token)
            if decoded and decoded.get("email"):
                return {
                    "uid": decoded.get("uid"),
                    "email": decoded.get("email").strip().lower(),
                    "name": decoded.get("name") or decoded.get("email").split("@")[0],
                    "picture": decoded.get("picture"),
                    "email_verified": decoded.get("email_verified", True)
                }
    except Exception as e:
        logger.info(f"Firebase Admin SDK verification attempt: {e}; trying Google tokeninfo fallback...")

    # 2. Resilient Fallback: Google Tokeninfo Endpoint verification
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
        req = urllib.request.Request(url, headers={"User-Agent": "ConnectHub-Auth/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.getcode() == 200:
                data = json.loads(resp.read().decode("utf-8"))
                email = data.get("email")
                if email:
                    # Validate that email is verified by Google
                    email_verified = data.get("email_verified")
                    if str(email_verified).lower() in ("true", "1", "yes"):
                        return {
                            "uid": data.get("sub") or data.get("user_id"),
                            "email": email.strip().lower(),
                            "name": data.get("name") or email.split("@")[0],
                            "picture": data.get("picture"),
                            "email_verified": True
                        }
    except Exception as e:
        logger.warning(f"Google tokeninfo endpoint token verification failed: {e}")

    return None


def get_firebase_client_config():
    """Retrieve public Firebase configuration for client-side JavaScript SDK."""
    try:
        return {
            "apiKey": current_app.config.get("FIREBASE_API_KEY", ""),
            "authDomain": current_app.config.get("FIREBASE_AUTH_DOMAIN", ""),
            "projectId": current_app.config.get("FIREBASE_PROJECT_ID", ""),
            "storageBucket": current_app.config.get("FIREBASE_STORAGE_BUCKET", ""),
            "messagingSenderId": current_app.config.get("FIREBASE_MESSAGING_SENDER_ID", ""),
            "appId": current_app.config.get("FIREBASE_APP_ID", "")
        }
    except RuntimeError:
        return {
            "apiKey": os.getenv("FIREBASE_API_KEY", ""),
            "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
            "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
            "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
            "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
            "appId": os.getenv("FIREBASE_APP_ID", "")
        }

