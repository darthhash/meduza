import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, abort, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
import re

BASE_DIR = os.path.dirname(__file__)
DATA_JSON = os.path.join(BASE_DIR, "data", "news.json")
DB_PATH = os.path.join(BASE_DIR, "data", "news.db")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")  # можно сменить в prod

# SQLite DB
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# модель статьи
class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    title = db.Column(db.String(400), nullable=False)
    text = db.Column(db.Text, nullable=False)
    section = db.Column(db.String(50), nullable=False, default="list")  # main, side, list
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "text": self.text,
            "section": self.section,
            "created_at": self.created_at.isoformat(),
        }

# утилита slug
def slugify(value):
    value = value.lower().strip()
    # заменить кириллицу удобно: просто транслитерация упрощённая — но для простоты оставляем латинские и цифры
    # сделаем простую транслитерацию для кириллицы
    trans_map = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i',
        'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
        'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ы':'y','э':'e','ю':'yu','я':'ya','ь':'','ъ':''
    }
    out_chars = []
    for ch in value:
        if ch in trans_map:
            out_chars.append(trans_map[ch])
        else:
            out_chars.append(ch)
    value = "".join(out_chars)
    # replace non-word with dash
    value = re.sub(r'[^a-z0-9]+', '-', value)
    value = re.sub(r'-{2,}', '-', value).strip('-')
    if not value:
        value = "article"
    return value

# при первом запуске создадим БД и импортируем JSON (если БД ещё не создана)
def init_db_and_import():
    need_import = not os.path.exists(DB_PATH)
    db.create_all()
    if need_import and os.path.exists(DATA_JSON):
        with open(DATA_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        # импорт main
        def save_article(title, text, section):
            slug_base = slugify(title)
            slug = slug_base
            i = 1
            # обеспечить уникальность slug
            while Article.query.filter_by(slug=slug).first():
                i += 1
                slug = f"{slug_base}-{i}"
            a = Article(title=title, text=text, section=section, slug=slug)
            db.session.add(a)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()

        if "main" in data:
            m = data["main"]
            save_article(m.get("title","Главная новость"), m.get("text",""), "main")
        if "side" in data:
            for item in data["side"]:
                save_article(item.get("title",""), item.get("text",""), "side")
        if "list" in data:
            for item in data["list"]:
                save_article(item.get("title",""), item.get("text",""), "list")

# старт
with app.app_context():
    init_db_and_import()

# роуты
@app.route("/")
def index():
    # main: section 'main' (возьмём самый свежий)
    main = Article.query.filter_by(section="main").order_by(Article.created_at.desc()).first()
    side = Article.query.filter_by(section="side").order_by(Article.created_at.desc()).limit(6).all()
    lst = Article.query.filter(Article.section!="main").order_by(Article.created_at.desc()).all()
    return render_template("index.html", main=main, side=side, list_articles=lst)

@app.route("/article/<slug>")
def article_view(slug):
    a = Article.query.filter_by(slug=slug).first_or_404()
    return render_template("article.html", article=a)

# админка: добавление
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        section = request.form.get("section", "list")
        title = request.form.get("title", "").strip()
        text = request.form.get("text", "").strip()
        slug_raw = request.form.get("slug", "").strip()
        if not title or not text:
            flash("Заголовок и текст обязательны", "error")
            return redirect(url_for("admin"))
        slug_base = slugify(slug_raw if slug_raw else title)
        slug = slug_base
        i = 1
        while Article.query.filter_by(slug=slug).first():
            i += 1
            slug = f"{slug_base}-{i}"
        a = Article(title=title, text=text, section=section, slug=slug)
        db.session.add(a)
        db.session.commit()
        flash("Статья добавлена", "success")
        return redirect(url_for("admin"))
    articles = Article.query.order_by(Article.created_at.desc()).all()
    return render_template("admin.html", articles=articles)

# редактирование
@app.route("/admin/edit/<int:article_id>", methods=["GET", "POST"])
def admin_edit(article_id):
    a = Article.query.get_or_404(article_id)
    if request.method == "POST":
        a.title = request.form.get("title", a.title)
        a.text = request.form.get("text", a.text)
        section = request.form.get("section", a.section)
        a.section = section
        slug_raw = request.form.get("slug", a.slug)
        slug_base = slugify(slug_raw)
        slug = slug_base
        i = 1
        while True:
            other = Article.query.filter_by(slug=slug).first()
            if not other or other.id == a.id:
                break
            i += 1
            slug = f"{slug_base}-{i}"
        a.slug = slug
        db.session.commit()
        flash("Статья обновлена", "success")
        return redirect(url_for("admin"))
    return render_template("admin_edit.html", article=a)

# удаление
@app.route("/admin/delete/<int:article_id>", methods=["POST"])
def admin_delete(article_id):
    a = Article.query.get_or_404(article_id)
    db.session.delete(a)
    db.session.commit()
    flash("Статья удалена", "success")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    # в продакшене запускать через gunicorn
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
