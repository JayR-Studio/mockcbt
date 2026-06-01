import secrets
import string
import os
import csv
from io import TextIOWrapper
from dotenv import load_dotenv

load_dotenv()
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user
from werkzeug.security import generate_password_hash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, ActivationCode, Subject, Question, ExamYear


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required():
    if not current_user.is_authenticated:
        flash("Please login as admin.", "warning")
        return False

    if session.get("login_context") != "admin":
        flash("Please login through the admin login page.", "warning")
        return False

    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return False

    return True


def generate_code(length=10):
    characters = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(characters) for _ in range(length))


@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("identifier", "").strip().lower()
        password = request.form.get("password", "")

        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")

        if not admin_email or not admin_password:
            flash("Admin credentials are not configured.", "danger")
            return redirect(url_for("admin.admin_login"))

        if email != admin_email or password != admin_password:
            flash("Invalid admin login details.", "danger")
            return redirect(url_for("admin.admin_login"))

        user = User.query.filter_by(email=email).first()

        if not user:
            user = User(
                full_name="Admin",
                email=email,
                phone_number="admin",
                password_hash=generate_password_hash(password),
                is_admin=True,
                is_active_user=True
            )
            db.session.add(user)
        else:
            user.is_admin = True
            user.is_active_user = True
            user.password_hash = generate_password_hash(password)

        db.session.commit()

        logout_user()
        session.clear()

        login_user(user)
        session["login_context"] = "admin"

        flash("Admin login successful.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin_login.html")


@admin_bp.route("/")
@login_required
def dashboard():
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    total_users = User.query.count()
    active_users = User.query.filter_by(is_active_user=True).count()
    total_codes = ActivationCode.query.count()
    unused_codes = ActivationCode.query.filter_by(is_used=False).count()

    codes = ActivationCode.query.order_by(ActivationCode.created_at.desc()).limit(20).all()

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        active_users=active_users,
        total_codes=total_codes,
        unused_codes=unused_codes,
        codes=codes
    )


@admin_bp.route("/generate-codes", methods=["POST"])
@login_required
def generate_codes():
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    quantity = int(request.form.get("quantity", 1))

    for _ in range(quantity):
        code = generate_code()

        while ActivationCode.query.filter_by(code=code).first():
            code = generate_code()

        activation_code = ActivationCode(code=code)
        db.session.add(activation_code)

    db.session.commit()

    flash(f"{quantity} activation code(s) generated successfully.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/questions")
@login_required
def questions():
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    year_id = request.args.get("year_id", type=int)
    subject_id = request.args.get("subject_id", type=int)
    status = request.args.get("status", "")
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Question.query

    if year_id:
        query = query.filter_by(exam_year_id=year_id)

    if subject_id:
        query = query.filter_by(subject_id=subject_id)

    if status == "active":
        query = query.filter_by(is_active=True)

    elif status == "disabled":
        query = query.filter_by(is_active=False)

    if search:
        query = query.filter(Question.question_text.ilike(f"%{search}%"))

    pagination = (
        query
        .order_by(Question.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )

    questions = pagination.items

    subjects = Subject.query.order_by(Subject.name.asc()).all()
    years = ExamYear.query.order_by(ExamYear.year.desc()).all()

    return render_template(
        "admin_questions.html",
        questions=questions,
        pagination=pagination,
        subjects=subjects,
        years=years,
        selected_year_id=year_id,
        selected_subject_id=subject_id,
        selected_status=status,
        search=search
    )


@admin_bp.route("/questions/<int:question_id>/delete", methods=["POST"])
@login_required
def delete_question(question_id):
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    question = Question.query.get_or_404(question_id)

    question.is_active = False
    db.session.commit()

    flash("Question disabled successfully. It will no longer appear in exams.", "success")
    return redirect(url_for("admin.questions"))


@admin_bp.route("/questions/<int:question_id>/restore", methods=["POST"])
@login_required
def restore_question(question_id):
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    question = Question.query.get_or_404(question_id)

    question.is_active = True
    db.session.commit()

    flash("Question restored successfully. It can now appear in exams again.", "success")
    return redirect(url_for("admin.questions"))


@admin_bp.route("/questions/<int:question_id>")
@login_required
def question_detail(question_id):
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    question = Question.query.get_or_404(question_id)

    return render_template("admin_question_detail.html", question=question)


@admin_bp.route("/questions/upload", methods=["GET", "POST"])
@login_required
def upload_questions():
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        file = request.files.get("csv_file")

        if not file:
            flash("Please upload a CSV file.", "danger")
            return redirect(url_for("admin.upload_questions"))

        if not file.filename.lower().endswith(".csv"):
            flash("Only CSV files are allowed.", "danger")
            return redirect(url_for("admin.upload_questions"))

        try:
            csv_file = TextIOWrapper(file, encoding="utf-8-sig")
            reader = csv.DictReader(csv_file)

            required_columns = [
                "exam_year",
                "subject",
                "question_text",
                "option_a",
                "option_b",
                "option_c",
                "option_d",
                "correct_option",
            ]

            if not reader.fieldnames:
                flash("CSV file appears to be empty or invalid.", "danger")
                return redirect(url_for("admin.upload_questions"))

            normalized_headers = [header.strip() for header in reader.fieldnames]

            for column in required_columns:
                if column not in normalized_headers:
                    flash(f"Missing required column: {column}", "danger")
                    return redirect(url_for("admin.upload_questions"))

            rows = []
            skipped_count = 0

            for row in reader:
                cleaned_row = {
                    "exam_year": row.get("exam_year", "").strip(),
                    "subject": row.get("subject", "").strip(),
                    "question_text": row.get("question_text", "").strip(),
                    "option_a": row.get("option_a", "").strip(),
                    "option_b": row.get("option_b", "").strip(),
                    "option_c": row.get("option_c", "").strip(),
                    "option_d": row.get("option_d", "").strip(),
                    "correct_option": row.get("correct_option", "").strip().upper(),
                    "explanation": row.get("explanation", "").strip(),
                    "difficulty": row.get("difficulty", "normal").strip().lower() or "normal",
                }

                if (
                    not cleaned_row["exam_year"]
                    or not cleaned_row["subject"]
                    or not cleaned_row["question_text"]
                    or not cleaned_row["option_a"]
                    or not cleaned_row["option_b"]
                    or not cleaned_row["option_c"]
                    or not cleaned_row["option_d"]
                    or cleaned_row["correct_option"] not in ["A", "B", "C", "D"]
                ):
                    skipped_count += 1
                    continue

                rows.append(cleaned_row)

            if not rows:
                flash("No valid questions found in CSV.", "danger")
                return redirect(url_for("admin.upload_questions"))

            # Load existing years once
            existing_years = {
                year.year: year
                for year in ExamYear.query.all()
            }

            # Create missing years
            needed_year_names = {row["exam_year"] for row in rows}

            for year_name in needed_year_names:
                if year_name not in existing_years:
                    new_year = ExamYear(year=year_name, label=year_name)
                    db.session.add(new_year)
                    existing_years[year_name] = new_year

            db.session.flush()

            # Load existing subjects once
            existing_subjects = {
                subject.name: subject
                for subject in Subject.query.all()
            }

            # Create missing subjects
            needed_subject_names = {row["subject"] for row in rows}

            for subject_name in needed_subject_names:
                if subject_name not in existing_subjects:
                    new_subject = Subject(name=subject_name)
                    db.session.add(new_subject)
                    existing_subjects[subject_name] = new_subject

            db.session.flush()

            # Load existing questions once
            existing_questions = set()

            all_existing_questions = Question.query.with_entities(
                Question.exam_year_id,
                Question.subject_id,
                Question.question_text,
                Question.option_a,
                Question.option_b,
                Question.option_c,
                Question.option_d,
            ).all()

            for item in all_existing_questions:
                existing_questions.add((
                    item.exam_year_id,
                    item.subject_id,
                    item.question_text,
                    item.option_a,
                    item.option_b,
                    item.option_c,
                    item.option_d,
                ))

            new_questions = []
            uploaded_count = 0

            for row in rows:
                exam_year = existing_years[row["exam_year"]]
                subject = existing_subjects[row["subject"]]

                question_key = (
                    exam_year.id,
                    subject.id,
                    row["question_text"],
                    row["option_a"],
                    row["option_b"],
                    row["option_c"],
                    row["option_d"],
                )

                if question_key in existing_questions:
                    skipped_count += 1
                    continue

                existing_questions.add(question_key)

                new_questions.append(
                    Question(
                        exam_year_id=exam_year.id,
                        subject_id=subject.id,
                        question_text=row["question_text"],
                        option_a=row["option_a"],
                        option_b=row["option_b"],
                        option_c=row["option_c"],
                        option_d=row["option_d"],
                        correct_option=row["correct_option"],
                        explanation=row["explanation"],
                        difficulty=row["difficulty"],
                        is_active=True,
                    )
                )

                uploaded_count += 1

            db.session.add_all(new_questions)
            db.session.commit()

            flash(
                f"Upload complete. {uploaded_count} question(s) added. {skipped_count} duplicate/invalid row(s) skipped.",
                "success"
            )
            return redirect(url_for("admin.questions"))

        except Exception as e:
            db.session.rollback()
            flash(f"Upload failed: {str(e)}", "danger")
            return redirect(url_for("admin.upload_questions"))

    return render_template("upload_questions.html")


@admin_bp.route("/questions/disable-set", methods=["POST"])
@login_required
def disable_question_set():
    if not admin_required():
        return redirect(url_for("student.dashboard"))

    year_id = request.form.get("year_id", type=int)

    if not year_id:
        flash("Please select a practice set to disable.", "danger")
        return redirect(url_for("admin.questions"))

    exam_year = ExamYear.query.get_or_404(year_id)

    questions = Question.query.filter_by(
        exam_year_id=exam_year.id,
        is_active=True
    ).all()

    if not questions:
        flash("No active questions found for this practice set.", "warning")
        return redirect(url_for("admin.questions"))

    for question in questions:
        question.is_active = False

    db.session.commit()

    flash(
        f"All active questions under {exam_year.label or exam_year.year} have been disabled.",
        "success"
    )
    return redirect(url_for("admin.questions"))
