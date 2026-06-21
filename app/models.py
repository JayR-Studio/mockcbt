from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    is_active_user = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)

    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    active_session_token = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)

    attempts = db.relationship("ExamAttempt", backref="user", lazy=True)
    activation_codes = db.relationship("ActivationCode", backref="used_by", lazy=True)


class ExamYear(db.Model):
    __tablename__ = "exam_years"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(100), unique=True, nullable=False)
    label = db.Column(db.String(150), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship("Question", backref="exam_year", lazy=True)


class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    questions = db.relationship("Question", backref="subject", lazy=True)


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)

    exam_year_id = db.Column(db.Integer, db.ForeignKey("exam_years.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)

    question_text = db.Column(db.Text, nullable=False)

    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False)
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)

    correct_option = db.Column(db.String(1), nullable=False)
    explanation = db.Column(db.Text, nullable=True)

    difficulty = db.Column(db.String(50), default="normal")
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.now)

    answers = db.relationship("UserAnswer", backref="question", lazy=True)


class ActivationCode(db.Model):
    __tablename__ = "activation_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)

    is_used = db.Column(db.Boolean, default=False)
    used_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at = db.Column(db.DateTime, nullable=True)


class ExamAttempt(db.Model):
    __tablename__ = "exam_attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    mode = db.Column(db.String(50), nullable=False)

    exam_year_id = db.Column(db.Integer, db.ForeignKey("exam_years.id"), nullable=True)
    exam_year = db.relationship("ExamYear", backref="attempts")

    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=True)

    subject = db.relationship("Subject", backref="attempts")

    score = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0)

    duration_minutes = db.Column(db.Integer, nullable=True)

    started_at = db.Column(db.DateTime, default=datetime.now)
    submitted_at = db.Column(db.DateTime, nullable=True)

    answers = db.relationship("UserAnswer", backref="attempt", lazy=True)


class UserAnswer(db.Model):
    __tablename__ = "user_answers"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("exam_attempts.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)

    selected_option = db.Column(db.String(1), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)

    answered_at = db.Column(db.DateTime, default=datetime.now)


class PasswordResetRequest(db.Model):
    __tablename__ = "password_reset_requests"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", backref="password_reset_requests")

    identifier_used = db.Column(db.String(120), nullable=False)

    token_hash = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(30), default="pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", backref="payment_transactions")

    reference = db.Column(db.String(120), unique=True, nullable=False)
    amount_kobo = db.Column(db.Integer, nullable=False)

    status = db.Column(db.String(30), default="initialized")
    provider = db.Column(db.String(30), default="paystack")

    authorization_url = db.Column(db.Text, nullable=True)
    gateway_response = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime, nullable=True)
