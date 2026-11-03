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
            cert_path = app.config.get("FIREBASE_SERVICE_ACCOUNT_KEY")
        else:
            try:
                cert_path = current_app.config.get("FIREBASE_SERVICE_ACCOUNT_KEY")
            except Exception:
                cert_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

        cert_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

        project_id = None
        if app and "FIREBASE_PROJECT_ID" in app.config:
            project_id = app.config.get("FIREBASE_PROJECT_ID")
        else:
            try:
                project_id = current_app.config.get("FIREBASE_PROJECT_ID")
            except Exception:
                project_id = os.getenv("FIREBASE_PROJECT_ID", "email-and-chat-system")
        if not project_id:
            project_id = "email-and-chat-system"

        if cert_path and os.path.exists(cert_path):
            cred = credentials.Certificate(cert_path)
            firebase_admin.initialize_app(cred, options={"projectId": project_id})
            _firebase_initialized = True
            logger.info("Firebase Admin SDK initialized successfully via certificate file.")
            return True
        elif cert_json:
            cred_dict = json.loads(cert_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, options={"projectId": project_id})
            _firebase_initialized = True
            logger.info("Firebase Admin SDK initialized successfully via JSON credentials.")
            return True
        else:
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
    Uses a multi-layered verification strategy:
    1. Firebase Admin SDK verify_id_token()
    2. Google Identity Toolkit REST API accounts:lookup (official Firebase Auth endpoint)
    3. Direct RS256 JWT signature verification using Google's public certificates
    Returns decoded user dictionary or None.
    """
    if not id_token or not isinstance(id_token, str):
        return None

    id_token = id_token.strip()
    if not id_token:
        return None

    project_id = "email-and-chat-system"
    try:
        project_id = current_app.config.get("FIREBASE_PROJECT_ID") or project_id
    except Exception:
        project_id = os.getenv("FIREBASE_PROJECT_ID", project_id)

    # 1. Try Firebase Admin SDK verification
    try:
        initialize_firebase_admin()
        import firebase_admin
        from firebase_admin import auth as fb_auth

        if firebase_admin._apps:
            decoded = fb_auth.verify_id_token(id_token, clock_skew_seconds=10)
            if decoded and decoded.get("email"):
                return {
                    "uid": decoded.get("uid") or decoded.get("sub"),
                    "email": decoded.get("email").strip().lower(),
                    "name": decoded.get("name") or decoded.get("email").split("@")[0],
                    "picture": decoded.get("picture"),
                    "email_verified": decoded.get("email_verified", True)
                }
    except Exception as e:
        logger.info(f"Firebase Admin SDK verification attempt: {e}; trying Google Identity Toolkit lookup...")

    # 2. Google Identity Toolkit REST API verification (accounts:lookup)
    api_key = "AIzaSyCkBsSv7BacOOHT7d68Zsh7t2GgizziHvk"
    try:
        api_key = current_app.config.get("FIREBASE_API_KEY") or api_key
    except Exception:
        api_key = os.getenv("FIREBASE_API_KEY", api_key)

    if api_key:
        try:
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={urllib.parse.quote(api_key)}"
            req_data = json.dumps({"idToken": id_token}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ConnectHub-Auth/1.0"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.getcode() == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    users = data.get("users") or []
                    if users and len(users) > 0:
                        u = users[0]
                        email = (u.get("email") or "").strip().lower()
                        if email:
                            return {
                                "uid": u.get("localId"),
                                "email": email,
                                "name": u.get("displayName") or email.split("@")[0],
                                "picture": u.get("photoUrl"),
                                "email_verified": u.get("emailVerified", True)
                            }
        except Exception as e:
            logger.info(f"Google Identity Toolkit accounts:lookup attempt: {e}; trying public cert verification...")

    # 3. Cryptographic RS256 JWT verification using Google public x509 certificates
    try:
        import jwt
        unverified_header = jwt.get_unverified_header(id_token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg")
        if alg == "RS256" and kid:
            certs_url = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
            creq = urllib.request.Request(certs_url, headers={"User-Agent": "ConnectHub-Auth/1.0"})
            with urllib.request.urlopen(creq, timeout=10) as cresp:
                if cresp.getcode() == 200:
                    public_certs = json.loads(cresp.read().decode("utf-8"))
                    cert_pem = public_certs.get(kid)
                    if cert_pem:
                        expected_aud = project_id or "email-and-chat-system"
                        expected_iss = f"https://securetoken.google.com/{expected_aud}"
                        decoded = jwt.decode(
                            id_token,
                            cert_pem,
                            algorithms=["RS256"],
                            audience=expected_aud,
                            issuer=expected_iss,
                            options={"verify_exp": True}
                        )
                        email = (decoded.get("email") or "").strip().lower()
                        if email:
                            return {
                                "uid": decoded.get("user_id") or decoded.get("sub"),
                                "email": email,
                                "name": decoded.get("name") or email.split("@")[0],
                                "picture": decoded.get("picture"),
                                "email_verified": decoded.get("email_verified", True)
                            }
    except Exception as e:
        logger.warning(f"Public cert JWT token verification failed: {e}")

    return None


def get_firebase_client_config():
    """Retrieve public Firebase configuration for client-side JavaScript SDK."""
    default_api_key = "AIzaSyCkBsSv7BacOOHT7d68Zsh7t2GgizziHvk"
    default_auth_domain = "email-and-chat-system.firebaseapp.com"
    default_project_id = "email-and-chat-system"
    default_storage_bucket = "email-and-chat-system.firebasestorage.app"
    default_messaging_sender_id = "511432167350"
    default_app_id = "1:511432167350:web:1d4cfe1ae26f7ee9133b17"
    default_measurement_id = "G-3V04PXS0Y6"

    try:
        return {
            "apiKey": current_app.config.get("FIREBASE_API_KEY") or default_api_key,
            "authDomain": current_app.config.get("FIREBASE_AUTH_DOMAIN") or default_auth_domain,
            "projectId": current_app.config.get("FIREBASE_PROJECT_ID") or default_project_id,
            "storageBucket": current_app.config.get("FIREBASE_STORAGE_BUCKET") or default_storage_bucket,
            "messagingSenderId": current_app.config.get("FIREBASE_MESSAGING_SENDER_ID") or default_messaging_sender_id,
            "appId": current_app.config.get("FIREBASE_APP_ID") or default_app_id,
            "measurementId": current_app.config.get("FIREBASE_MEASUREMENT_ID") or default_measurement_id
        }
    except RuntimeError:
        return {
            "apiKey": os.getenv("FIREBASE_API_KEY", default_api_key),
            "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", default_auth_domain),
            "projectId": os.getenv("FIREBASE_PROJECT_ID", default_project_id),
            "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", default_storage_bucket),
            "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", default_messaging_sender_id),
            "appId": os.getenv("FIREBASE_APP_ID", default_app_id),
            "measurementId": os.getenv("FIREBASE_MEASUREMENT_ID", default_measurement_id)
        }

