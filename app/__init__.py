from flask import Flask
from config import Config
from app.extensions import db, login_manager, csrf, mail


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    from app.routes.public import public_bp
    app.register_blueprint(public_bp)

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.routes.student import student_bp
    app.register_blueprint(student_bp)

    from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    return app
