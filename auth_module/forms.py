from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, BooleanField
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    EqualTo,
    ValidationError,
    Optional
)
from flask_login import current_user
from sqlalchemy import func
from auth_module.models import User


class RegisterForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=50)
        ]
    )

    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(),
            Length(max=120)
        ]
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=8, message="Password must contain at least 8 characters.")
        ]
    )

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match.")
        ]
    )

    submit = SubmitField("Create Account")

    def validate_username(self, field):
        username = field.data.strip()
        if User.query.filter(func.lower(func.trim(User.username)) == username.lower()).first():
            raise ValidationError("This username is already taken.")

    def validate_email(self, field):
        email = field.data.strip().lower()
        if User.query.filter(func.lower(func.trim(User.email)) == email).first():
            raise ValidationError("An account with this email already exists.")


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email()]
    )

    password = PasswordField(
        "Password",
        validators=[DataRequired()]
    )

    submit = SubmitField("Login")


class ProfileForm(FlaskForm):
    full_name = StringField("Full Name", validators=[Length(max=100)])
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=50)]
    )
    phone = StringField("Phone", validators=[Optional(), Length(max=20)])
    bio = TextAreaField("Bio", validators=[Optional(), Length(max=300)])
    profile_image = FileField(
        "Profile Picture",
        validators=[FileAllowed(["jpg", "jpeg", "png", "gif", "webp"], "Images only!")]
    )
    submit = SubmitField("Save Profile")

    def validate_username(self, field):
        username = field.data.strip()
        if username.lower() != current_user.username.lower():
            if User.query.filter(func.lower(func.trim(User.username)) == username.lower()).first():
                raise ValidationError("This username is already taken.")

    def validate_profile_image(self, field):
        if field.data and hasattr(field.data, "read"):
            field.data.seek(0, 2)
            size = field.data.tell()
            field.data.seek(0)
            if size > 5 * 1024 * 1024:
                raise ValidationError("Profile picture must be under 5MB.")



class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Current Password",
        validators=[DataRequired()]
    )
    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=8, message="New password must be at least 8 characters.")
        ]
    )
    confirm_new_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="New passwords must match.")
        ]
    )
    submit = SubmitField("Update Password")
