from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required
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

        login_user(user)

        session["login_context"] = "student"

        flash("Login successful.", "success")

        if user.is_active_user:
            return redirect(url_for("student.dashboard"))

        return redirect(url_for("student.activate"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()

    flash("You have been logged out.", "success")
    return redirect(url_for("public.index"))
