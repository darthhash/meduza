import os, re
from datetime import datetime
from html import unescape, escape
from flask import Flask, render_template, abort
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

# DB
db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url or ("sqlite:///" + os.path.join(DATA_DIR, "news.db"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Article(db.Model):
    __tablename__ = "articles"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(255), unique=True, index=True, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    text = db.Column(db.Text, default="")              # здесь лежит ПОЛНЫЙ текст / HTML
    section = db.Column(db.String(20), default="list") # main | side | list
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

with app.app_context():
    db.create_all()

# ─────────────────────────────────────────────────────────────────────────────
# Форматирование «голого» текста в HTML (если тэгов нет)
TAG_PRESENT_RE = re.compile(r"</?(p|br|ul|ol|li|h\d|figure|img|blockquote|pre|code|div|span)\b", re.I)
LIST_LINE_RE   = re.compile(r"^\s*([-*•])\s+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")

def _paragraphs_from_plain(s: str, target_len: int = 600):
    """Если пришло одно полотно без пустых строк — режем по предложениям на блоки ~target_len."""
    sentences = SENTENCE_SPLIT.split(s.strip())
    out, buf = [], []
    cur_len = 0
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
    """
    Если в тексте нет HTML-тегов — конвертим плейнтекст в HTML:
    - пустые строки => новые абзацы
    - строки, начинающиеся с '-'/'*' => <ul><li>…</li></ul>
    - если пустых строк нет — режем по предложениям на несколько <p>
    Всё экранируем.
    """
    if not text:
        return ""
    if TAG_PRESENT_RE.search(text):
        return text  # уже HTML — ничего не трогаем

    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # есть ли явные пустые строки (абзацы)?
    blocks = re.split(r"\n{2,}", raw)
    html_blocks = []

    if len(blocks) == 1:
        # абзацев нет — режем по предложениям
        for para in _paragraphs_from_plain(raw):
            html_blocks.append(f"<p>{escape(para)}</p>")
        return "\n".join(html_blocks)

    # обрабатываем каждый блок отдельно
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        # все строки — маркеры списка?
        if all(LIST_LINE_RE.match(line or "") for line in lines):
            items = []
            for line in lines:
                item = LIST_LINE_RE.sub("", line).strip()
                if item:
                    items.append(f"<li>{escape(item)}</li>")
            if items:
                html_blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
        else:
            # обычный абзац — одиночные переносы превращаем в пробел
            joined = " ".join(l.strip() for l in lines if l.strip())
            if joined:
                html_blocks.append(f"<p>{escape(joined)}</p>")

    return "\n".join(html_blocks)

# ─────────────────────────────────────────────────────────────────────────────

# Главная оставляем как раньше (тизеры ты уже сделал в своём app.py-теасере).
# Ниже — только рендер страницы статьи: прокидываем article_html.
@app.route("/news/<slug>")
def article(slug):
    a = Article.query.filter_by(slug=slug).first()
    if not a:
        abort(404)
    article_html = ensure_html(a.text or "")
    return render_template("article.html", article=a, article_html=article_html)

@app.route("/")
def index():
    # у тебя уже есть версия с тизерами — оставляй её;
    # если нужен «минимум», можно вернуть текущую простую:
    from sqlalchemy import desc
    main_obj = Article.query.filter_by(section="main").order_by(desc(Article.created_at)).first()
    side_objs = Article.query.filter_by(section="side").order_by(desc(Article.created_at)).limit(6).all()
    list_objs = Article.query.filter(Article.section != "main").order_by(desc(Article.created_at)).all()
    news = {"main": None, "side": [], "list": []}
    if main_obj:
        news["main"] = {"title": main_obj.title, "text": "", "slug": main_obj.slug}
    news["side"] = [{"title": x.title, "text": "", "slug": x.slug} for x in side_objs]
    news["list"] = [{"title": x.title, "text": "", "slug": x.slug} for x in list_objs if x.section != "main"]
    return render_template("index.html", news=news)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
