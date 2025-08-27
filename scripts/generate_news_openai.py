# scripts/generate_news_openai.py
# -*- coding: utf-8 -*-
"""
Вымышленные новости «Россия будущего» на основе прошлых статей (экспоненциальное
затухание) + аналитика в духе Лакана / Жижека / Смулянского.
Текст — OpenAI Chat API, картинка — OpenAI Images API.

ENV:
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL=gpt-4o-mini
  OPENAI_IMAGE_MODEL=gpt-image-1
  MAX_TOKENS=900
  TEMPERATURE=0.7

  LAST_K=40
  HALF_LIFE=10
  CTX_MAX_CHARS=8000

  IMAGE_SIZE=1024x1024
  IMAGE_EMBED_DATA_URL=true          # true -> <img data:...>, false -> сохраняем PNG в /static/news_images
  IMAGE_ALT_SUFFIX="(вымышленная иллюстрация)"

  # ПРОМПТ override (опц.):
  PROMPT_SYSTEM / PROMPT_USER     ИЛИ  PROMPT_MODULE + PROMPT_SYSTEM_VAR/PROMPT_USER_VAR

CLI:
  python scripts/generate_news_openai.py --n 3 --import
"""

import os, sys, re, json, argparse, textwrap, html, base64, pathlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import Counter

try:
    from dotenv import load_dotenv, find_dotenv
    p = find_dotenv(usecwd=True)
    if p: load_dotenv(p)
except Exception:
    pass

sys.path.insert(0, os.path.abspath("."))

def _wire_slugify():
    for path in ("app", "app.utils", "app.helpers", "app.lib", "app.core", "app.common"):
        try:
            mod = __import__(path, fromlist=["*"])
            fn = getattr(mod, "slugify", None)
            if callable(fn): return fn
        except Exception:
            pass
    try:
        from slugify import slugify as _ext
        return _ext
    except Exception:
        pass
    RU = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"i",
          "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
          "х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ы":"y","э":"e","ю":"yu","я":"ya","ь":"","ъ":""}
    import re as _re
    def _fallback(s: str) -> str:
        s = (s or "").strip().lower()
        t = "".join(RU.get(ch, ch) for ch in s)
        t = _re.sub(r"[^a-z0-9]+", "-", t)
        t = _re.sub(r"-{2,}", "-", t).strip("-")
        return t
    return _fallback

slugify = _wire_slugify()

def getenv_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if (v is not None and str(v).strip() != "") else default

def getenv_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, "").strip())
    except Exception: return default

def getenv_bool(name: str, default: bool) -> bool:
    v = str(os.getenv(name, "")).strip().lower()
    if v in ("1","true","yes","y","on"): return True
    if v in ("0","false","no","n","off"): return False
    return default

def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)

def ts_from_iso(s: Optional[str]) -> float:
    if not s: return 0.0
    try: return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except Exception: return 0.0

def fetch_recent_articles_from_db(limit: int = 40) -> List[Dict[str, Any]]:
    try:
        from app import app as _flask_app  # type: ignore
        from app import Article as _Article  # type: ignore
        if _Article is not None and _flask_app is not None:
            with _flask_app.app_context():
                q = (_Article.query
                     .order_by(_Article.created_at.desc() if hasattr(_Article, "created_at")
                               else _Article.id.desc())
                     .limit(limit))
                rows = q.all()
                out = []
                for r in rows:
                    out.append({
                        "title": getattr(r, "title", "") or "",
                        "text": getattr(r, "text", "") or "",
                        "tags": getattr(r, "tags", "") or "",
                        "slug": getattr(r, "slug", "") or "",
                        "section": getattr(r, "section", "") or "list",
                        "created_at": (getattr(r, "created_at", None) or "").isoformat()
                                      if hasattr(r, "created_at") and getattr(r, "created_at") else ""
                    })
                out.sort(key=lambda x: ts_from_iso(x["created_at"]), reverse=True)
                return out
    except Exception as e:
        print("[warn] SQLAlchemy Article path failed:", e)

    try:
        from app import app as _flask_app  # type: ignore
        from app import db as _db          # type: ignore
        from sqlalchemy import text as sql_text  # type: ignore
        candidate_tables = ["articles", "news", "posts"]
        candidate_cols = [
            ("title","text","tags","slug","section","created_at"),
            ("title","body","tags","slug","section","created_at"),
            ("title","content","tags","slug","section","created_at"),
        ]
        if _flask_app is None or _db is None:
            raise RuntimeError("Flask app/db not available for raw SQL")
        with _flask_app.app_context():
            for tbl in candidate_tables:
                for cols in candidate_cols:
                    cols_sql = ", ".join(cols)
                    q = f"SELECT {cols_sql} FROM {tbl} ORDER BY created_at DESC LIMIT :lim"
                    try:
                        rows = _db.session.execute(sql_text(q), {"lim": limit}).fetchall()
                        if not rows: continue
                        out = []
                        for row in rows:
                            d = dict(zip(cols, row))
                            out.append({
                                "title": d.get("title") or "",
                                "text": d.get("text") or d.get("body") or d.get("content") or "",
                                "tags": d.get("tags") or "",
                                "slug": d.get("slug") or "",
                                "section": d.get("section") or "list",
                                "created_at": d.get("created_at").isoformat()
                                              if hasattr(d.get("created_at"), "isoformat") and d.get("created_at")
                                              else (d.get("created_at") or "")
                            })
                        out.sort(key=lambda x: ts_from_iso(x["created_at"]), reverse=True)
                        return out
                    except Exception:
                        continue
    except Exception as e:
        print("[warn] raw SQL path failed:", e)
    return []

RU_STOP = set("""
и в во что на для по как не от из у к до о над под при про без между или но либо либоже
это этой этот эта эти тех там тут такой такая такие было были был была будет будут
""".split())

def tokenize_ru(s: str):
    s = re.sub(r"[^\w\s\-]", " ", s, flags=re.I | re.U).replace("_", " ")
    return [t.lower() for t in s.split() if len(t) >= 4 and t.lower() not in RU_STOP]

def exp_weights(n: int, half_life: int):
    return [0.5 ** (i / max(1, half_life)) for i in range(n)]

def build_context(arts: List[Dict[str, Any]], last_k: int, half_life: int, max_chars: int) -> str:
    subset = arts[:max(1, last_k)]
    weights = exp_weights(len(subset), half_life)
    chunks, total = [], 0
    for i, a in enumerate(subset):
        w = weights[i]
        dt = a.get("created_at") or ""
        try: ds = datetime.fromisoformat(dt.replace("Z","+00:00")).strftime("%Y-%m-%d") if dt else ""
        except Exception: ds = ""
        title = (a.get("title") or "").strip()
        tags = (a.get("tags") or "").strip()
        plain = strip_html(a.get("text") or "")
        block_len = int(400 * (1 + 3 * w))
        brief = plain[:block_len].strip()
        head = f"- ({ds}) {title}" + (f" — теги: {tags}" if tags else "")
        piece = f"{head}\n{brief}\n"
        if total + len(piece) <= max_chars:
            chunks.append(piece); total += len(piece)
        else:
            break
    return ("Предыдущие публикации (новые → старые):\n" + "\n".join(chunks)).strip()

def derive_topics(arts: List[Dict[str, Any]], n: int, last_k: int, half_life: int) -> List[str]:
    subset = arts[:max(1, last_k)]
    weights = exp_weights(len(subset), half_life)
    bag = Counter()
    for i, a in enumerate(subset):
        w = weights[i]
        tags = a.get("tags") or ""
        title = a.get("title") or ""
        for t in re.split(r"[,\|/;]+", tags):
            t = t.strip()
            if len(t) >= 3: bag[t] += 1.5 * w
        for tok in tokenize_ru(title):
            bag[tok] += 1.0 * w
    if not bag:
        return ["общество будущего", "технологии будущего", "политэкономия будущего"][:n]
    topics = []
    for word, _ in bag.most_common(60):
        if not any(word.lower()==t.lower() for t in topics):
            topics.append(word)
        if len(topics) >= n: break
    return topics[:n] if topics else ["будущее России"] * n

class OpenAIChat:
    def __init__(self, model: str, max_tokens: int = 900, temperature: float = 0.7):
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY не задан в ENV/.env")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat_json(self, system: str, user: str) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type":"json_object"},
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"system","content":system},{"role":"user","content":user + "\n\nВерни СТРОГО один JSON-объект."}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return resp.choices[0].message.content.strip()

class OpenAIImages:
    def __init__(self, model: str):
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY не задан в ENV/.env")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.size = getenv_str("IMAGE_SIZE", "1024x1024")
        self.embed_data_url = getenv_bool("IMAGE_EMBED_DATA_URL", True)
        self.alt_suffix = getenv_str("IMAGE_ALT_SUFFIX", "(вымышленная иллюстрация)")

    def _prompt_for_article(self, article_json: Dict[str, Any]) -> str:
        title = article_json.get("title","").strip()
        tags = article_json.get("tags","")
        tema = f"{title}. Теги: {tags}" if tags else title
        return (
            "Stylized editorial illustration, futuristic Russia context, cinematic, subtle, "
            "no text, no logos, no real person likeness. "
            f"Concept: {tema}. "
            "Mood: analytic, reflective, psychoanalytic motifs (lack/desire/symbolic order)."
        )

    def generate_and_attach(self, article_json: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._prompt_for_article(article_json)
        try:
            r = self.client.images.generate(model=self.model, prompt=prompt, size=self.size, n=1)
            b64 = r.data[0].b64_json
            alt = (article_json.get("title","") + " " + self.alt_suffix).strip()
            if self.embed_data_url:
                data_url = f"data:image/png;base64,{b64}"
                img_html = f'<figure><img src="{data_url}" alt="{html.escape(alt)}" /><figcaption>{html.escape(alt)}</figcaption></figure>'
                article_json["text"] = img_html + "\n" + article_json.get("text","")
                article_json["image_inline"] = True
            else:
                slug = article_json.get("slug") or slugify(article_json.get("title",""))
                out_dir = pathlib.Path("static/news_images"); out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{slug}.png"
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                url = f"/static/news_images/{out_path.name}"
                img_html = f'<figure><img src="{url}" alt="{html.escape(alt)}" /><figcaption>{html.escape(alt)}</figcaption></figure>'
                article_json["text"] = img_html + "\n" + article_json.get("text","")
                article_json["image_url"] = url
                article_json["image_inline"] = False
            return article_json
        except Exception as e:
            print("[warn] image generation failed:", e)
            return article_json

DEFAULT_SYSTEM_PROMPT = (
    "Ты — редактор отдела «Россия будущего». Все новости ВЫМЫШЛЕННЫЕ. "
    "Основа — контекстный дайджест прошлых публикаций (новые важнее старых). "
    "Подавай материал аналитически: через оптику психоанализа и критической теории "
    "(Лакан, Жижек, Смулянский) — без прямых цитат и именованных ссылок. "
    "Не используй реальные проверяемые даты/цифры/адреса; если упоминаешь реальных людей — это художественная реконструкция. "
    "Верни СТРОГО один JSON-объект:\n"
    '{ "title": "...<=120...", "section": "main|list", "tags": "теги,через,запятую", "text": "<p>...HTML...</p>" }'
)

DEFAULT_USER_TMPL = (
    "Контекст (новые → старые, экспоненциальное затухание):\n{context}\n\n"
    "Сгенерируй вымышленную новость о ближайшем будущем России по теме: «{topic}».\n"
    "Укажи привязку к: городу/региону, экономике/праву/технологиям, и одному конкретному персонажу (вымышленному или реальному). "
    "Сюжет объясни через: желания/отсутствия/символический порядок (Лакан), "
    "идеологическое интерпеллирование/событие (Жижек), микроаналитику смысла (Смулянский). "
    "Структура: 2–5 абзацев по 400–800 символов, HTML (<p>…</p>, можно 1–2 <h3>). "
    "Без кликбейта, без реальных точных дат/цифр. Верни СТРОГО ОДИН JSON-объект по формату."
)

def load_prompts() -> tuple[str, str]:
    module_name = os.getenv("PROMPT_MODULE")
    sys_var = os.getenv("PROMPT_SYSTEM_VAR", "SYSTEM_PROMPT")
    usr_var = os.getenv("PROMPT_USER_VAR", "USER_PROMPT")
    if module_name:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            return getattr(mod, sys_var), getattr(mod, usr_var)
        except Exception as e:
            print("[warn] PROMPT_MODULE load failed:", e)
    s_env, u_env = os.getenv("PROMPT_SYSTEM"), os.getenv("PROMPT_USER")
    if (s_env or "").strip() and (u_env or "").strip():
        return s_env, u_env
    return DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_TMPL

SYSTEM_PROMPT, USER_TMPL = load_prompts()

def parse_json_or_fallback(raw: str, topic: str) -> Dict[str, Any]:
    try:
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
        data = json.loads(s)
    except Exception:
        title = (raw.split("\n", 1)[0] or topic).strip()[:120]
        body = "<p>" + re.sub(r"\n{2,}", "</p><p>", raw).strip() + "</p>"
        data = {"title": title, "section": "list", "tags": topic, "text": body}
    data["title"] = (data.get("title") or topic)[:120]
    data["section"] = (data.get("section") or "list") if (data.get("section") in ("main","list","side")) else "list"
    text = (data.get("text") or "").strip()
    if not text.startswith("<"): text = "<p>" + text.replace("\n\n","</p><p>").replace("\n"," ") + "</p>"
    data["text"] = text
    return data

def generate_one(chat, images, topic: str, context: str) -> Dict[str, Any]:
    user_prompt = USER_TMPL.format(topic=topic, context=context)
    raw = chat.chat_json(SYSTEM_PROMPT, user_prompt)
    data = parse_json_or_fallback(raw, topic)
    data["slug"] = slugify(data["title"])
    data["created_at"] = datetime.utcnow().isoformat()
    extra_tags = "Лакан,Жижек,Смулянский,психоанализ,идеология"
    data["tags"] = (data.get("tags") or topic)
    seen, merged = set(), []
    for t in (str(data["tags"]) + "," + extra_tags).split(","):
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower()); merged.append(t)
    data["tags"] = ",".join(merged)
    data = images.generate_and_attach(data)
    return data

def write_payload(articles: List[Dict[str, Any]], path: str = "scripts/articles_payload.py"):
    lines = ["ARTICLES = [\n"]
    for a in articles:
        text = a["text"].replace("\\", "\\\\").replace('"', '\\"')
        title = a["title"].replace("\\", "\\\\").replace('"', '\\"')
        tags = (a.get("tags") or "").replace("\\", "\\\\").replace('"', '\\"')
        lines.append("  {\n")
        lines.append(f'    "title": "{title}",\n')
        lines.append(f'    "slug": "{a["slug"]}",\n')
        lines.append(f'    "section": "{a["section"]}",\n')
        if tags: lines.append(f'    "tags": "{tags}",\n')
        lines.append(f'    "created_at": "{a["created_at"]}",\n')
        if a.get("image_url"): lines.append(f'    "image_url": "{a["image_url"]}",\n')
        lines.append('    "text": (\n')
        for part in textwrap.wrap(text, width=120, break_long_words=False, break_on_hyphens=False):
            lines.append(f'      "{part}"\n')
        lines.append("    )\n")
        lines.append("  },\n")
    lines.append("]\n")
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print(f"[ok] wrote {path}")

def do_import_articles(articles: List[Dict[str, Any]]):
    try:
        import importlib, inspect
        imp_mod = importlib.import_module("scripts.import_articles")
        try: importlib.reload(imp_mod)
        except Exception: pass
        fn = getattr(imp_mod, "import_articles", None)
        if callable(fn):
            try:
                sig = inspect.signature(fn)
                if len(sig.parameters) >= 1:
                    return fn(articles)
                else:
                    setattr(imp_mod, "ARTICLES", articles); return fn()
            except Exception:
                setattr(imp_mod, "ARTICLES", articles); return fn()
        else:
            print("[warn] scripts.import_articles: function import_articles not found")
    except Exception as e:
        print("[warn] import into DB failed:", e)

# -------- programmatic API: run(...) --------
def run(n: int = 3, last_k: Optional[int] = None, half_life: Optional[int] = None,
        ctx_max_chars: Optional[int] = None, do_import: bool = False,
        topics_override: Optional[List[str]] = None) -> Dict[str, Any]:
    last_k = last_k if last_k is not None else getenv_int("LAST_K", 40)
    half_life = half_life if half_life is not None else getenv_int("HALF_LIFE", 10)
    ctx_max_chars = ctx_max_chars if ctx_max_chars is not None else getenv_int("CTX_MAX_CHARS", 8000)

    history = fetch_recent_articles_from_db(limit=last_k)
    context = build_context(history, last_k=last_k, half_life=half_life, max_chars=ctx_max_chars)
    topics = topics_override[:n] if topics_override else derive_topics(history, n=n, last_k=last_k, half_life=half_life)

    chat_model = getenv_str("OPENAI_MODEL", "gpt-4o-mini")
    img_model  = getenv_str("OPENAI_IMAGE_MODEL", "gpt-image-1")
    chat = OpenAIChat(chat_model, max_tokens=getenv_int("MAX_TOKENS", 900),
                      temperature=float(getenv_str("TEMPERATURE","0.7")))
    images = OpenAIImages(img_model)

    articles = []
    for i, t in enumerate(topics):
        art = generate_one(chat, images, t, context)
        art["section"] = "main" if i == 0 else "list"
        articles.append(art)

    write_payload(articles)
    if do_import:
        do_import_articles(articles)
    return {"articles": articles, "topics": topics, "context": context, "imported": bool(do_import)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--last-k", type=int, default=None)
    ap.add_argument("--half-life", type=int, default=None)
    ap.add_argument("--ctx-max-chars", type=int, default=None)
    ap.add_argument("--import", dest="do_import", action="store_true")
    args = ap.parse_args()
    res = run(n=args.n, last_k=args.last_k, half_life=args.half_life,
              ctx_max_chars=args.ctx_max_chars, do_import=args.do_import)
    print(f"[ok] generated {len(res['articles'])} articles")

if __name__ == "__main__":
    main()
