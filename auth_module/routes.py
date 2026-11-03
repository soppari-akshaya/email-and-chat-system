from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required
from urllib.parse import urlparse

from auth_module import auth_bp
from auth_module.forms import RegisterForm, LoginForm
from auth_module.models import User
from auth_module.services import register_user


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        try:
            register_user(
                username=form.username.data,
                email=form.email.data,
                password=form.password.data
            )

            flash("Your account has been created. Please log in.", "success")
            return redirect(url_for("auth.login"))

        except Exception:
            from extensions import db
            db.session.rollback()
            flash("Unable to create your account. Please try again.", "danger")

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("Your account is currently inactive.", "danger")
                return render_template("auth/login.html", form=form)

            login_user(user, remember=True)

            flash("Login successful.", "success")

            next_page = request.args.get("next")

            if next_page:
                parsed_url = urlparse(next_page)

                if not parsed_url.netloc and next_page.startswith("/"):
                    return redirect(next_page)

            return redirect("/dashboard")

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))