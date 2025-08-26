import os
import json
import traceback
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, abort, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Flask & DB config ---
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

# Prefer Railway DATABASE_URL (Postgres); fallback to local SQLite
db_url = os.getenv("DATABASE_URL")
if db_url:
    # Allow postgres:// scheme
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(DATA_DIR, "news.db")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
from scripts.import_articles import import_articles
import_articles()

# --- Model ---
class Article(db.Model):
    __tablename__ = "articles"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(255), unique=True, index=True, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    text = db.Column(db.Text, default="")
    section = db.Column(db.String(20), default="list")  # main | side | list
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_card(self):
        return {"slug": self.slug, "title": self.title, "text": self.text}

# --- utils ---
TRANS = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ы':'y','э':'e','ю':'yu','я':'ya','ь':'','ъ':''
}
def slugify(value: str) -> str:
    s = value.lower().strip()
    s = "".join(TRANS.get(ch, ch) for ch in s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "article"

# --- init & import from data/news.json (one-time) ---
def init_db_and_import():
    db.create_all()
    # Check if empty DB; if yes, seed from data/news.json
    has_any = db.session.query(Article.id).first() is not None
    json_path = os.path.join(DATA_DIR, "news.json")
    if not has_any and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # main
            m = data.get("main")
            if m:
                title = m.get("title","").strip()
                text = m.get("text","").strip()
                if title:
                    a = Article(title=title, text=text, section="main", slug=slugify(title))
                    db.session.add(a)
            # side
            for item in data.get("side", []):
                title = (item.get("title") or "").strip()
                text = (item.get("text") or "").strip()
                if title:
                    a = Article(title=title, text=text, section="side", slug=slugify(title))
                    db.session.add(a)
            # list
            for item in data.get("list", []):
                title = (item.get("title") or "").strip()
                text = (item.get("text") or "").strip()
                if title:
                    a = Article(title=title, text=text, section="list", slug=slugify(title))
                    db.session.add(a)
            db.session.commit()
            print("Seeded DB from data/news.json")
        except Exception as e:
            print("ERROR importing data/news.json:", e)
            traceback.print_exc()

with app.app_context():
    init_db_and_import()

# --- Routes ---
@app.route("/")
def index():
    # Build dict "news" to match templates/index.html expectations
    main_obj = Article.query.filter_by(section="main").order_by(Article.created_at.desc()).first()
    side_objs = Article.query.filter_by(section="side").order_by(Article.created_at.desc()).limit(6).all()
    list_objs = Article.query.filter(Article.section != "main").order_by(Article.created_at.desc()).all()

    news = {"main": None, "side": [], "list": []}
    if main_obj:
        news["main"] = {"title": main_obj.title, "text": main_obj.text, "slug": main_obj.slug}
    news["side"] = [ {"title": a.title, "text": a.text, "slug": a.slug} for a in side_objs ]
    # list should exclude main; keep side and list combined like original "list"
    news["list"] = [ {"title": a.title, "text": a.text, "slug": a.slug}
                     for a in list_objs if a.section != "main" ]
    return render_template("index.html", news=news)

@app.route("/news/<slug>")
def article(slug):
    a = Article.query.filter_by(slug=slug).first()
    if not a:
        abort(404)
    return render_template("article.html", article=a)

# --- Admin (simple) ---
@app.route("/admin")
def admin():
    items = Article.query.order_by(Article.created_at.desc()).all()
    return render_template("admin.html", items=items)

@app.route("/admin/new", methods=["GET","POST"])
def admin_new():
    if request.method == "POST":
        title = request.form.get("title","").strip()
        text = request.form.get("text","").strip()
        section = request.form.get("section","list")
        slug = slugify(request.form.get("slug") or title)
        if not title:
            flash("Нужен title", "error")
            return redirect(url_for("admin_new"))
        a = Article(title=title, text=text, section=section, slug=slug)
        db.session.add(a)
        try:
            db.session.commit()
            flash("Создано", "success")
            return redirect(url_for("admin"))
        except IntegrityError:
            db.session.rollback()
            flash("Такой slug уже есть", "error")
    return render_template("admin_edit.html", article=None)

@app.route("/admin/<int:aid>/edit", methods=["GET","POST"])
def admin_edit(aid):
    a = Article.query.get_or_404(aid)
    if request.method == "POST":
        a.title = request.form.get("title","").strip() or a.title
        a.text = request.form.get("text","")
        a.section = request.form.get("section", a.section)
        slug = request.form.get("slug","").strip()
        if slug:
            a.slug = slugify(slug)
        try:
            db.session.commit()
            flash("Сохранено", "success")
            return redirect(url_for("admin"))
        except IntegrityError:
            db.session.rollback()
            flash("Slug уже используется", "error")
    return render_template("admin_edit.html", article=a)

@app.route("/admin/<int:aid>/delete", methods=["POST"])
def admin_delete(aid):
    a = Article.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    flash("Удалено", "success")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
