# app/__init__.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    # ВАЖНО: создаём app здесь (у тебя раньше этого не было в одном из вариантов)
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    # БД (Railway DATABASE_URL или локально SQLite)
    db_url = os.getenv("DATABASE_URL", "sqlite:///local.db")
    # Нормализация старого префикса
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # JSON ровно в UTF-8
    app.config["JSON_AS_ASCII"] = False
    try:
        app.json.ensure_ascii = False  # Flask 3.x
    except Exception:
        pass

    db.init_app(app)
    migrate.init_app(app, db)

    # Модель Article — берём твою, иначе фолбэк
    try:
        from .models import Article  # type: ignore
        globals()["Article"] = Article
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
        globals()["Article"] = Article

    # Роуты: newsgen (если модуль есть)
    try:
        from .newsgen import newsgen_bp  # type: ignore
        app.register_blueprint(newsgen_bp)
    except Exception as e:
        print("[warn] newsgen blueprint not loaded:", e)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # Экспорт для скриптов (from app import app, db, Article)
    globals()["app"] = app
    globals()["db"] = db
    return app
