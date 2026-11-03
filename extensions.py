from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import os

db = SQLAlchemy()

login_manager = LoginManager()

# Production SocketIO configuration with optional Redis message queue
socketio_kwargs = {
    "async_mode": os.getenv("SOCKETIO_ASYNC_MODE", "threading"),
    "cors_allowed_origins": "*",
}
redis_url = os.getenv("REDIS_URL")
if redis_url:
    socketio_kwargs["message_queue"] = redis_url

socketio = SocketIO(**socketio_kwargs)

csrf = CSRFProtect()

migrate = Migrate()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[]
)
