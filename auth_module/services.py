from extensions import db
from auth_module.models import User, UserProfile


def register_user(username, email, password):
    username = username.strip()
    email = email.strip().lower()

    user = User(
        username=username,
        email=email,
        role="user",
        is_active=True,
        is_verified=False,
        online_status="offline"
    )

    user.set_password(password)

    profile = UserProfile(
        full_name=username
    )

    user.profile = profile

    db.session.add(user)
    db.session.commit()

    return user
