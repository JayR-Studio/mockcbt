import secrets
import hashlib
from datetime import datetime, timedelta

from flask_mail import Message
from app.extensions import db, mail
from app.models import User, PasswordResetRequest

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

from app.extensions import db
from app.models import User


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        phone_number = request.form.get("phone_number")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.register"))

        existing_user = User.query.filter(
            (User.email == email) | (User.phone_number == phone_number)
        ).first()

        if existing_user:
            flash("Email or phone number already exists.", "danger")
            return redirect(url_for("auth.register"))

        user = User(
            full_name=full_name,
            email=email,
            phone_number=phone_number,
            password_hash=generate_password_hash(password)
        )

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully. Please login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.email == identifier) | (User.phone_number == identifier)
        ).first()

        if user and user.locked_until and user.locked_until > datetime.utcnow():
            remaining_minutes = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
            flash(f"Too many failed attempts. Please try again in {remaining_minutes} minute(s).", "danger")
            return redirect(url_for("auth.login"))

        if not user or not check_password_hash(user.password_hash, password):
            if user:
                user.failed_login_attempts += 1

                if user.failed_login_attempts >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=10)
                    flash("Too many failed attempts. Your account is locked for 10 minutes.", "danger")
                else:
                    remaining_attempts = 5 - user.failed_login_attempts
                    flash(f"Invalid login details. {remaining_attempts} attempt(s) remaining.", "danger")

                db.session.commit()
            else:
                flash("Invalid login details.", "danger")

            return redirect(url_for("auth.login"))

        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()

        if user.is_admin:
            flash("Admins should login from the admin login page.", "warning")
            return redirect(url_for("admin.admin_login"))

        session_token = secrets.token_urlsafe(32)

        user.active_session_token = session_token
        db.session.commit()

        login_user(user)

        session["login_context"] = "student"
        session["session_token"] = session_token

        flash("Login successful.", "success")

        if user.is_active_user:
            return redirect(url_for("student.dashboard"))

        return redirect(url_for("student.activate"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    current_user.active_session_token = None
    db.session.commit()

    logout_user()
    session.pop("session_token", None)
    session.clear()

    flash("You have been logged out.", "success")
    return redirect(url_for("public.index"))


# ------------------------------------------------------------------------------------------------------------
#                                        Forgot password
# ------------------------------------------------------------------------------------------------------------


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()

        user = User.query.filter(
            (User.email == identifier) | (User.phone_number == identifier)
        ).first()

        if not user:
            flash("No account was found with those details.", "danger")
            return redirect(url_for("auth.forgot_password"))

        if not user.email:
            flash("This account does not have an email address attached. Please contact support.", "danger")
            return redirect(url_for("auth.forgot_password"))

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        reset_request = PasswordResetRequest(
            user_id=user.id,
            identifier_used=identifier,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            status="pending"
        )

        db.session.add(reset_request)
        db.session.commit()

        reset_link = url_for("auth.reset_password", token=raw_token, _external=True)

        message = Message(
            subject="MockCBT Password Reset Request",
            recipients=[user.email],
            body=f"""Hello {user.full_name},

        We received a request to reset the password for your MockCBT account.

        Click the secure link below to create a new password:

        {reset_link}

        This link will expire in 1 hour.

        If you did not request this password reset, you can safely ignore this email. Your password will remain unchanged.

        MockCBT Support
        """
        )

        try:
            mail.send(message)
            flash("Password reset link has been sent to your email.", "success")
            return redirect(url_for("auth.login"))

        except Exception:
            db.session.rollback()
            flash("Unable to send reset email right now. Please try again later.", "danger")
            return redirect(url_for("auth.forgot_password"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    reset_request = PasswordResetRequest.query.filter_by(
        token_hash=token_hash,
        status="pending"
    ).first()

    if not reset_request:
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for("auth.login"))

    if reset_request.used_at:
        flash("This reset link has already been used.", "danger")
        return redirect(url_for("auth.login"))

    if not reset_request.expires_at or reset_request.expires_at < datetime.utcnow():
        reset_request.status = "expired"
        db.session.commit()

        flash("This reset link has expired. Please request another one.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("auth.reset_password", token=token))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.reset_password", token=token))

        user = reset_request.user

        user.password_hash = generate_password_hash(password)
        user.failed_login_attempts = 0
        user.locked_until = None

        if hasattr(user, "active_session_token"):
            user.active_session_token = None

        reset_request.status = "resolved"
        reset_request.used_at = datetime.utcnow()
        reset_request.resolved_at = datetime.utcnow()

        db.session.commit()

        flash("Password reset successful. You can now login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)