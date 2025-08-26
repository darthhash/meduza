import os
import re
from datetime import datetime
from html import unescape
from flask import Flask, render_template, abort
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

# --- DB config (Railway Postgres или локальный SQLite) ---
db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url or ("sqlite:///" + os.path.join(DATA_DIR, "news.db"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# --- Model ---
class Article(db.Model):
    __tablename__ = "articles"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(255), unique=True, index=True, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    # В БД храним ПОЛНЫЙ текст/HTML
    text = db.Column(db.Text, default="")
    section = db.Column(db.String(20), default="list")  # main | side | list
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

with app.app_context():
    db.create_all()

# --- helpers: делаем подводку из полного HTML ---
TAG_RE = re.compile(r"<[^>]+>")
WS_RE  = re.compile(r"\s+")

def strip_html(html: str) -> str:
    if not html:
        return ""
    # убираем теги
    s = TAG_RE.sub(" ", html)
    s = unescape(s)
    # схлопываем пробелы
    s = WS_RE.sub(" ", s).strip()
    return s

def make_teaser(html: str, max_len: int = 220) -> str:
    """Берём начало текста без тегов, аккуратно обрезаем по слову."""
    plain = strip_html(html)
    if len(plain) <= max_len:
        return plain
    cut = plain[:max_len].rsplit(" ", 1)[0]
    return cut + "…"

def build_news_dict():
    """Главная страница: вместо полного текста отдаём 'teaser'."""
    main_obj = Article.query.filter_by(section="main").order_by(Article.created_at.desc()).first()
    side_objs = Article.query.filter_by(section="side").order_by(Article.created_at.desc()).limit(6).all()
    list_objs = Article.query.filter(Article.section != "main").order_by(Article.created_at.desc()).all()

    news = {"main": None, "side": [], "list": []}
    if main_obj:
        news["main"] = {
            "slug":  main_obj.slug,
            "title": main_obj.title,
            "teaser": make_teaser(main_obj.text, 260),  # на герое можно подлиннее
        }
    for a in side_objs:
        news["side"].append({
            "slug": a.slug,
            "title": a.title,
            "teaser": make_teaser(a.text, 180),
        })
    for a in list_objs:
        if a.section == "main":
            continue
        news["list"].append({
            "slug": a.slug,
            "title": a.title,
            "teaser": make_teaser(a.text, 180),
        })
    return news

# --- routes ---
@app.route("/")
def index():
    # На главной показываем только подводки (без HTML)
    return render_template("index.html", news=build_news_dict())

@app.route("/news/<slug>")
def article(slug):
    # На странице статьи показываем ПОЛНЫЙ HTML
    a = Article.query.filter_by(slug=slug).first()
    if not a:
        abort(404)
    return render_template("article.html", article=a)

# gunicorn entry
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
