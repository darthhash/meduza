import os, re
from datetime import datetime
from html import unescape, escape
from flask import Flask, render_template, abort, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

# DB (Railway Postgres или локальный SQLite)
db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url or ("sqlite:///" + os.path.join(DATA_DIR, "news.db"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ── Model ────────────────────────────────────────────────────────────────────
class Article(db.Model):
    __tablename__ = "articles"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(255), unique=True, index=True, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    text = db.Column(db.Text, default="")              # ПОЛНЫЙ текст / HTML
    section = db.Column(db.String(20), default="list") # main | side | list
    tags = db.Column(db.Text)                          # "economy, МВД, коррупция"
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

with app.app_context():
    db.create_all()

# ── helpers: тизер и форматирование plain-текста ─────────────────────────────
TAG_RE = re.compile(r"<[^>]+>")
WS_RE  = re.compile(r"\s+")
# вырезаем блок <figure class="article-hero">…</figure> из текста,
# чтобы подпись «Источник…» не попадала в подводку
FIGURE_BLOCK_RE = re.compile(
    r'<figure[^>]*class="[^"]*article-hero[^"]*"[^>]*>.*?</figure>',
    re.I | re.S
)

# признаки «текст уже в HTML»
TAG_PRESENT_RE = re.compile(
    r"</?(p|br|ul|ol|li|h[1-6]|figure|img|blockquote|pre|code|div|span)\b",
    re.I,
)
# строки списка типа "- пункт" / "* пункт" / "• пункт"
LIST_LINE_RE   = re.compile(r"^\s*([-*•])\s+")
# делим длинное «полотно» по предложениям
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")

def strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    s = TAG_RE.sub(" ", html_text)
    s = unescape(s)
    return WS_RE.sub(" ", s).strip()

def teaser_source_text(html_text: str) -> str:
    # сначала убираем hero-figure целиком
    cleaned = FIGURE_BLOCK_RE.sub("", html_text or "")
    # затем уже чистим HTML → plain
    return strip_html(cleaned)

def make_teaser(html_text: str, max_len: int = 220) -> str:
    plain = teaser_source_text(html_text)
    if len(plain) <= max_len:
        return plain
    cut = plain[:max_len].rsplit(" ", 1)[0]
    return cut + "…"

def _paragraphs_from_plain(s: str, target_len: int = 600):
    sentences = SENTENCE_SPLIT.split(s.strip())
    out, buf, cur_len = [], [], 0
    for sent in sentences:
        if not sent:
            continue
        buf.append(sent)
        cur_len += len(sent)
        if cur_len >= target_len:
            out.append(" ".join(buf).strip())
            buf, cur_len = [], 0
    if buf:
        out.append(" ".join(buf).strip())
    return out or ([s.strip()] if s.strip() else [])

def ensure_html(text: str) -> str:
    """Если нет HTML — делаем p/ul автоматически."""
    if not text:
        return ""
    if TAG_PRESENT_RE.search(text):
        return text
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n{2,}", raw)
    html_blocks = []
    if len(blocks) == 1:
        for para in _paragraphs_from_plain(raw):
            html_blocks.append(f"<p>{escape(para)}</p>")
        return "\n".join(html_blocks)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if all(LIST_LINE_RE.match(line or "") for line in lines):
            items = []
            for line in lines:
                item = LIST_LINE_RE.sub("", line).strip()
                if item:
                    items.append(f"<li>{escape(item)}</li>")
            if items:
                html_blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
        else:
            joined = " ".join(l.strip() for l in lines if l.strip())
            if joined:
                html_blocks.append(f"<p>{escape(joined)}</p>")
    return "\n".join(html_blocks)

# ── slugify для админки ──────────────────────────────────────────────────────
TRANS = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i',
         'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
         'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ы':'y','э':'e','ю':'yu','я':'ya','ь':'','ъ':''}
def slugify(value: str) -> str:
    s = (value or "").lower().strip()
    s = "".join(TRANS.get(ch, ch) for ch in s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "article"

# ── страницы ─────────────────────────────────────────────────────────────────
def build_news_dict():
    main_obj = Article.query.filter_by(section="main").order_by(Article.created_at.desc()).first()
    side_objs = Article.query.filter_by(section="side").order_by(Article.created_at.desc()).limit(6).all()
    list_objs = Article.query.filter(Article.section != "main").order_by(Article.created_at.desc()).all()
    news = {"main": None, "side": [], "list": []}
    if main_obj:
        news["main"] = {
            "slug": main_obj.slug,
            "title": main_obj.title,
            "teaser": make_teaser(main_obj.text, 260),
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

@app.route("/")
def index():
    return render_template("index.html", news=build_news_dict())

@app.route("/news/<slug>")
def article(slug):
    a = Article.query.filter_by(slug=slug).first()
    if not a:
        abort(404)
    article_html = ensure_html(a.text or "")
    return render_template("article.html", article=a, article_html=article_html)

# ── админка ──────────────────────────────────────────────────────────────────
@app.route("/admin")
def admin():
    items = Article.query.order_by(Article.created_at.desc()).all()
    return render_template("admin.html", items=items)

@app.route("/admin/new", methods=["GET","POST"])
def admin_new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        section = (request.form.get("section") or "list").strip()
        slug = (request.form.get("slug") or "").strip() or slugify(title)
        text = request.form.get("text") or ""
        tags = (request.form.get("tags") or "").strip()
        if not title:
            flash("Нужен заголовок", "error")
            return redirect(url_for("admin_new"))
        a = Article(slug=slug, title=title, section=section, text=text, tags=tags)
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
        a.title = (request.form.get("title") or a.title).strip()
        a.section = (request.form.get("section") or a.section).strip()
        a.slug = slugify((request.form.get("slug") or a.slug).strip())
        a.text = request.form.get("text") or ""
        a.tags = (request.form.get("tags") or "").strip()
        try:
            db.session.commit()
            flash("Сохранено", "success")
            return redirect(url_for("admin"))
        except IntegrityError:
            db.session.rollback()
            flash("Slug уже используется", "error")
    return render_template("admin_edit.html", article=a)

@app.post("/admin/<int:aid>/delete")
def admin_delete(aid):
    a = Article.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    flash("Удалено", "success")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
