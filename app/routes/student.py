import random
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models import ActivationCode, Subject, Question, ExamAttempt, UserAnswer, ExamYear


student_bp = Blueprint("student", __name__)


def student_context_required():
    if session.get("login_context") != "student":
        flash("Please login as a student to continue.", "warning")
        return False

    return True


@student_bp.route("/activate", methods=["GET", "POST"])
@login_required
def activate():
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if current_user.is_active_user:
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        code = request.form.get("activation_code", "").strip().upper()

        activation_code = ActivationCode.query.filter_by(code=code).first()

        if not activation_code:
            flash("Invalid activation code.", "danger")
            return redirect(url_for("student.activate"))

        if activation_code.is_used:
            flash("This activation code has already been used.", "danger")
            return redirect(url_for("student.activate"))

        current_user.is_active_user = True
        activation_code.is_used = True
        activation_code.used_by_user_id = current_user.id
        activation_code.used_at = datetime.utcnow()

        db.session.commit()

        flash("Account activated successfully.", "success")
        return redirect(url_for("student.dashboard"))

    return render_template("activation.html")


@student_bp.route("/dashboard")
@login_required
def dashboard():
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    years = ExamYear.query.order_by(ExamYear.year.desc()).all()

    year_question_counts = {}

    for exam_year in years:
        year_question_counts[exam_year.id] = Question.query.filter_by(
            exam_year_id=exam_year.id,
            is_active=True
        ).count()

    total_attempts = ExamAttempt.query.filter_by(user_id=current_user.id).count()

    best_attempt = (
        ExamAttempt.query
        .filter_by(user_id=current_user.id)
        .order_by(ExamAttempt.percentage.desc())
        .first()
    )

    last_attempt = (
        ExamAttempt.query
        .filter_by(user_id=current_user.id)
        .order_by(ExamAttempt.started_at.desc())
        .first()
    )

    questions_practiced = (
        UserAnswer.query
        .join(ExamAttempt)
        .filter(ExamAttempt.user_id == current_user.id)
        .count()
    )

    return render_template(
        "dashboard.html",
        years=years,
        total_attempts=total_attempts,
        best_attempt=best_attempt,
        last_attempt=last_attempt,
        questions_practiced=questions_practiced,
        year_question_counts=year_question_counts
    )


@student_bp.route("/exam/<int:attempt_id>/submit", methods=["POST"])
@login_required
def submit_exam(attempt_id):
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    attempt = ExamAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        flash("You are not allowed to submit this exam.", "danger")
        return redirect(url_for("student.dashboard"))

    question_ids = request.form.getlist("question_ids")

    score = 0
    total_questions = len(question_ids)

    for question_id in question_ids:
        question = Question.query.get(int(question_id))
        selected_option = request.form.get(f"question_{question_id}")

        is_correct = selected_option == question.correct_option

        if is_correct:
            score += 1

        answer = UserAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            selected_option=selected_option,
            is_correct=is_correct
        )

        db.session.add(answer)

    percentage = (score / total_questions) * 100 if total_questions > 0 else 0

    attempt.score = score
    attempt.total_questions = total_questions
    attempt.percentage = percentage
    attempt.submitted_at = datetime.utcnow()

    db.session.commit()

    return redirect(url_for("student.result", attempt_id=attempt.id))


@student_bp.route("/result/<int:attempt_id>")
@login_required
def result(attempt_id):
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    attempt = ExamAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        flash("You are not allowed to view this result.", "danger")
        return redirect(url_for("student.dashboard"))

    answers = UserAnswer.query.filter_by(attempt_id=attempt.id).all()

    subject_breakdown = {}

    for answer in answers:
        subject_name = answer.question.subject.name

        if subject_name not in subject_breakdown:
            subject_breakdown[subject_name] = {
                "correct": 0,
                "total": 0,
                "percentage": 0
            }

        subject_breakdown[subject_name]["total"] += 1

        if answer.is_correct:
            subject_breakdown[subject_name]["correct"] += 1

    for subject_name, data in subject_breakdown.items():
        data["percentage"] = (data["correct"] / data["total"]) * 100 if data["total"] > 0 else 0

    correct_count = UserAnswer.query.filter_by(
        attempt_id=attempt.id,
        is_correct=True
    ).count()

    wrong_count = UserAnswer.query.filter_by(
        attempt_id=attempt.id,
        is_correct=False
    ).count()

    return render_template(
        "result.html",
        attempt=attempt,
        answers=answers,
        correct_count=correct_count,
        wrong_count=wrong_count,
        subject_breakdown=subject_breakdown
    )


@student_bp.route("/attempt/<int:attempt_id>/review")
@login_required
def review_attempt(attempt_id):
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    attempt = ExamAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        flash("You are not allowed to review this attempt.", "danger")
        return redirect(url_for("student.dashboard"))

    answers = (
        UserAnswer.query
        .filter_by(attempt_id=attempt.id)
        .all()
    )

    return render_template(
        "review_attempt.html",
        attempt=attempt,
        answers=answers
    )


@student_bp.route("/attempts")
@login_required
def attempts():
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    attempts = (
        ExamAttempt.query
        .filter_by(user_id=current_user.id)
        .order_by(ExamAttempt.started_at.desc())
        .all()
    )

    return render_template("attempts.html", attempts=attempts)


@student_bp.route("/full-mock/setup", methods=["GET", "POST"])
@login_required
def full_mock_setup():
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    years = ExamYear.query.order_by(ExamYear.year.desc()).all()

    year_question_counts = {}

    for exam_year in years:
        year_question_counts[exam_year.id] = Question.query.filter_by(
            exam_year_id=exam_year.id,
            is_active=True
        ).count()

    if request.method == "POST":
        year_id = request.form.get("year_id", type=int)
        question_count = request.form.get("question_count", type=int)
        duration = request.form.get("duration", type=int)

        if not year_id or not question_count or not duration:
            flash("Please select practice set, number of questions, and duration.", "danger")
            return redirect(url_for("student.full_mock_setup"))

        exam_year = ExamYear.query.get_or_404(year_id)

        total_active_questions = Question.query.filter_by(
            exam_year_id=exam_year.id,
            is_active=True
        ).count()

        if total_active_questions == 0:
            flash("This practice set has no active questions.", "danger")
            return redirect(url_for("student.full_mock_setup"))

        if question_count > total_active_questions:
            flash("Selected number of questions is more than the active questions available.", "danger")
            return redirect(url_for("student.full_mock_setup"))

        return redirect(url_for(
            "student.start_full_mock",
            year_id=exam_year.id,
            question_count=question_count,
            duration=duration
        ))

    return render_template(
        "full_mock_setup.html",
        years=years,
        year_question_counts=year_question_counts
    )


@student_bp.route("/full-mock/start")
@login_required
def start_full_mock():
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    year_id = request.args.get("year_id", type=int)
    question_count = request.args.get("question_count", type=int)
    duration = request.args.get("duration", type=int)

    if not year_id or not question_count or not duration:
        flash("Invalid full mock setup.", "danger")
        return redirect(url_for("student.full_mock_setup"))

    exam_year = ExamYear.query.get_or_404(year_id)

    subjects = (
        Subject.query
        .join(Question)
        .filter(
            Question.exam_year_id == exam_year.id,
            Question.is_active == True
        )
        .distinct()
        .all()
    )

    if not subjects:
        flash("No active subjects found for this practice set.", "danger")
        return redirect(url_for("student.full_mock_setup"))

    total_active_questions = Question.query.filter_by(
        exam_year_id=exam_year.id,
        is_active=True
    ).count()

    if total_active_questions < question_count:
        flash("Not enough active questions available for this full mock exam.", "danger")
        return redirect(url_for("student.full_mock_setup"))

    subject_count = len(subjects)
    base_count = question_count // subject_count
    remainder = question_count % subject_count

    selected_questions = []

    for index, subject in enumerate(subjects):
        questions_needed = base_count

        if index < remainder:
            questions_needed += 1

        subject_questions = Question.query.filter_by(
            exam_year_id=exam_year.id,
            subject_id=subject.id,
            is_active=True
        ).all()

        if len(subject_questions) <= questions_needed:
            selected_questions.extend(subject_questions)
        else:
            selected_questions.extend(random.sample(subject_questions, questions_needed))

    # If some subjects had fewer questions than needed, fill the gap from remaining active questions.
    if len(selected_questions) < question_count:
        selected_ids = {question.id for question in selected_questions}

        remaining_questions = (
            Question.query
            .filter(
                Question.exam_year_id == exam_year.id,
                Question.is_active == True,
                ~Question.id.in_(selected_ids)
            )
            .all()
        )

        gap = question_count - len(selected_questions)

        if len(remaining_questions) >= gap:
            selected_questions.extend(random.sample(remaining_questions, gap))
        else:
            selected_questions.extend(remaining_questions)

    selected_questions = selected_questions[:question_count]
    random.shuffle(selected_questions)

    attempt = ExamAttempt(
        user_id=current_user.id,
        mode="full_mock",
        subject_id=None,
        total_questions=len(selected_questions),
        started_at=datetime.utcnow()
    )

    db.session.add(attempt)
    db.session.commit()

    return render_template(
        "exam.html",
        attempt=attempt,
        subject=None,
        exam_year=exam_year,
        questions=selected_questions,
        duration=duration,
        exam_title="Full Mock Exam"
    )


@student_bp.route("/year/<int:year_id>/subjects")
@login_required
def year_subjects(year_id):
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    exam_year = ExamYear.query.get_or_404(year_id)

    subjects = (
        Subject.query
        .join(Question)
        .filter(
            Question.exam_year_id == exam_year.id,
            Question.is_active == True
        )
        .distinct()
        .order_by(Subject.name.asc())
        .all()
    )

    subject_counts = {}

    for subject in subjects:
        subject_counts[subject.id] = Question.query.filter_by(
            exam_year_id=exam_year.id,
            subject_id=subject.id,
            is_active=True
        ).count()

    return render_template(
        "year_subjects.html",
        exam_year=exam_year,
        subjects=subjects,
        subject_counts=subject_counts
    )


@student_bp.route("/practice/year/<int:year_id>/subject/<int:subject_id>", methods=["GET", "POST"])
@login_required
def practice_setup(year_id, subject_id):
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    exam_year = ExamYear.query.get_or_404(year_id)
    subject = Subject.query.get_or_404(subject_id)

    total_questions = Question.query.filter_by(
        exam_year_id=exam_year.id,
        subject_id=subject.id,
        is_active=True
    ).count()

    if request.method == "POST":
        question_count = request.form.get("question_count", type=int)
        duration = request.form.get("duration", type=int)

        if not question_count or not duration:
            flash("Please select number of questions and duration.", "danger")
            return redirect(url_for(
                "student.practice_setup",
                year_id=exam_year.id,
                subject_id=subject.id
            ))

        if question_count > total_questions:
            flash("Selected number of questions is more than available questions.", "danger")
            return redirect(url_for(
                "student.practice_setup",
                year_id=exam_year.id,
                subject_id=subject.id
            ))

        return redirect(url_for(
            "student.start_subject_practice",
            year_id=exam_year.id,
            subject_id=subject.id,
            question_count=question_count,
            duration=duration
        ))

    return render_template(
        "practice_setup.html",
        exam_year=exam_year,
        subject=subject,
        total_questions=total_questions
    )


@student_bp.route("/practice/year/<int:year_id>/subject/<int:subject_id>/start")
@login_required
def start_subject_practice(year_id, subject_id):
    if not student_context_required():
        return redirect(url_for("auth.login"))

    if not current_user.is_active_user:
        return redirect(url_for("student.activate"))

    question_count = request.args.get("question_count", type=int)
    duration = request.args.get("duration", type=int)

    if not question_count or not duration:
        flash("Invalid practice setup.", "danger")
        return redirect(url_for(
            "student.practice_setup",
            year_id=year_id,
            subject_id=subject_id
        ))

    exam_year = ExamYear.query.get_or_404(year_id)
    subject = Subject.query.get_or_404(subject_id)

    available_questions = Question.query.filter_by(
        exam_year_id=exam_year.id,
        subject_id=subject.id,
        is_active=True
    ).all()

    if len(available_questions) < question_count:
        flash("Not enough questions available for this practice.", "danger")
        return redirect(url_for(
            "student.practice_setup",
            year_id=exam_year.id,
            subject_id=subject.id
        ))

    selected_questions = random.sample(available_questions, question_count)

    attempt = ExamAttempt(
        user_id=current_user.id,
        mode="subject_practice",
        subject_id=subject.id,
        total_questions=question_count,
        started_at=datetime.utcnow()
    )

    db.session.add(attempt)
    db.session.commit()

    return render_template(
        "exam.html",
        attempt=attempt,
        subject=subject,
        exam_year=exam_year,
        questions=selected_questions,
        duration=duration,
        exam_title="Subject Practice"
    )