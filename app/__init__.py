# app/__init__.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    # БД: Railway DATABASE_URL или локально SQLite
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///local.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # JSON ровно в UTF-8
    app.config["JSON_AS_ASCII"] = False
    try:
        app.json.ensure_ascii = False  # Flask 3.x
    except Exception:
        pass

    db.init_app(app)
    migrate.init_app(app, db)

    # Модель Article — используем твою, если есть; иначе минимальный фолбэк
    try:
        from .models import Article  # type: ignore
    except Exception:
        from sqlalchemy import func
        class Article(db.Model):  # type: ignore
            __tablename__ = "articles"
            id = db.Column(db.Integer, primary_key=True)
            title = db.Column(db.String(255), nullable=False)
            slug = db.Column(db.String(255), nullable=False)
            section = db.Column(db.String(32), default="list")
            tags = db.Column(db.String(1024))
            text = db.Column(db.Text, nullable=False)
            created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())

        # экспорт фолбэк-модели, чтобы scripts могли импортировать
        globals()["Article"] = Article

    # экспорт app/db для скриптов (from app import app, db, Article)
    globals()["app"] = app
    globals()["db"] = db

    # Регистрируем блюпринт генератора
    try:
        from .newsgen import newsgen_bp
        app.register_blueprint(newsgen_bp)
    except Exception as e:
        print("[warn] newsgen blueprint not loaded:", e)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
