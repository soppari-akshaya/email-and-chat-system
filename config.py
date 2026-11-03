
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

database_url = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "application.db")
)

# Use the installed psycopg 3 driver for PostgreSQL.
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql+psycopg://", 1
    )
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )


class Config:
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "development-secret-change-before-deployment"
    )

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (
        os.getenv("COOKIE_SECURE", "false").lower() == "true"
    )

    WTF_CSRF_TIME_LIMIT = 3600
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
