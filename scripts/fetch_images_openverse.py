# scripts/fetch_images_auto.py
import os, sys, re, html, time, hashlib
from typing import Optional, Dict
from urllib.parse import quote_plus

import requests

# импортируем приложение/модель
sys.path.insert(0, os.path.abspath("."))
from app import app, db, Article  # noqa

# ── настройки ────────────────────────────────────────────────────────────────
OPENVERSE_API = "https://api.openverse.engineering/v1/images/"
WMC_API = "https://commons.wikimedia.org/w/api.php"
UA = "meduza-good-news/1.2 (+https://example.com)"

# ищем, не вставляли ли уже картинку
FIGURE_RE = re.compile(r'<figure[^>]+class="[^"]*article-hero[^"]*"[^>]*>', re.I)
WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)

def simplify_query(s: str, max_words: int = 7) -> str:
    s = (s or "").replace("-", " ")
    s = WORD_RE.sub(" ", s).strip()
    words = [w for w in s.split() if len(w) > 2]
    return " ".join(words[:max_words]) or (s or "")

# ── провайдер 1: Openverse (CC0/PDM) ────────────────────────────────────────
def search_openverse(query: str) -> Optional[Dict[str, str]]:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    params = {
        "q": query,
        "license": "cc0,pdm",   # строго без копирайта
        "page_size": 3,
        "mature": "false",
    }
    r = requests.get(OPENVERSE_API, params=params, headers=headers, timeout=15)
    if r.status_code == 400:
        sq = simplify_query(query)
        r = requests.get(OPENVERSE_API, params={**params, "q": sq}, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    for it in data.get("results", []):
        url = it.get("url") or it.get("thumbnail")
        if not url:
            continue
        return {
            "url": url,
            "title": it.get("title") or query,
            "source": it.get("source") or "Openverse",
            "landing": it.get("foreign_landing_url") or url,
            "license": (it.get("license") or "cc0").upper(),
        }
    return None

# ── провайдер 2: Wikimedia Commons (только PD/CC0) ──────────────────────────
def search_wikimedia_pd(query: str) -> Optional[Dict[str, str]]:
    headers = {"User-Agent": UA}
    params = {
        "action": "query",
        "generator": "search",
        "gsrnamespace": "6",   # namespace 6 = File:
        "gsrlimit": "5",
        "gsrsearch": query,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": "1200",
        "format": "json",
        "formatversion": "2",
        "origin": "*",
    }
    r = requests.get(WMC_API, params=params, headers=headers, timeout=15)
    if r.status_code == 400:
        params["gsrsearch"] = simplify_query(query)
        r = requests.get(WMC_API, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    pages = (data.get("query") or {}).get("pages") or []
    for p in pages:
        ii = (p.get("imageinfo") or [])
        if not ii:
            continue
        info = ii[0]
        meta = (info.get("extmetadata") or {})
        lic_short = (meta.get("LicenseShortName") or {}).get("value", "")
        lic = (meta.get("License") or {}).get("value", "")
        ok = ("Public domain" in lic_short) or (lic.upper() == "CC0")
        if not ok:
            continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        title = p.get("title", "Wikimedia image").replace("File:", "")
        landing = "https://commons.wikimedia.org/wiki/" + p.get("title", "")
        return {
            "url": url,
            "title": title,
            "source": "Wikimedia Commons",
            "landing": landing,
            "license": lic_short or lic or "Public Domain",
        }
    return None

# ── ПЛЕЙСХОЛДЕР (SVG) + ссылка на Google Images ─────────────────────────────
def google_images_url(title: str) -> str:
    q = quote_plus(title or "")
    return f"https://www.google.com/search?tbm=isch&q={q}"

def color_from_slug(slug: str) -> str:
    # детерминированный пастельный цвет по слагу
    h = hashlib.md5((slug or "").encode("utf-8")).hexdigest()
    r = 200 + int(h[:2], 16) % 40
    g = 200 + int(h[2:4], 16) % 40
    b = 200 + int(h[4:6], 16) % 40
    return f"rgb({r},{g},{b})"

def make_svg_placeholder(slug: str, title: str) -> str:
    bg = color_from_slug(slug)
    t  = html.escape((title or "")[:60])
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg}"/>
      <stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#g)"/>
  <text x="48" y="330" font-size="56" font-family="PT Serif, Georgia, serif" fill="#222">{t}</text>
</svg>'''
    data = svg.replace("#", "%23").replace("\n", "")
    return f"data:image/svg+xml;utf8,{data}"

def build_placeholder(slug: str, title: str) -> Dict[str, str]:
    return {
        "url": make_svg_placeholder(slug, title),
        "title": title or "image",
        "source": "Google Images (link)",
        "landing": google_images_url(title or slug.replace("-", " ")),
        "license": "—",  # это наш svg, ссылка лишь на поиск
    }

# ── вставка figure ───────────────────────────────────────────────────────────
def inject_figure(html_text: str, img: Dict[str, str]) -> str:
    """Вставляем <figure> сверху статьи, если его ещё нет."""
    if not img or not img.get("url"):
        return html_text or ""
    if FIGURE_RE.search(html_text or ""):
        return html_text or ""

    cap = (
        'Источник: <a href="{landing}" rel="noopener" target="_blank">{src}</a> {lic}'
        .format(landing=html.escape(img["landing"]), src=html.escape(img["source"]), lic=f"({html.escape(img['license'])})" if img.get("license") else "")
    )
    figure = (
        '<figure class="article-hero">'
        f'<img src="{html.escape(img["url"])}" alt="{html.escape(img["title"])}" />'
        f"<figcaption>{cap}</figcaption>"
        "</figure>\n"
    )
    return (figure + (html_text or "")).strip()

# ── основной проход ──────────────────────────────────────────────────────────
def main():
    with app.app_context():
        updated = 0
        arts = Article.query.order_by(Article.created_at.desc()).all()
        for a in arts:
            if FIGURE_RE.search(a.text or ""):
                continue

            q_title = a.title or ""
            q_slug  = a.slug.replace("-", " ")

            img = None
            # 1) Openverse
            try:
                img = search_openverse(q_title or q_slug)
            except Exception as e:
                print("openverse error:", e)

            # 2) Wikimedia Commons (PD/CC0)
            if not img:
                try:
                    img = search_wikimedia_pd(q_title or q_slug)
                except Exception as e:
                    print("wikimedia error:", e)

            # 3) Плейсхолдер + ссылка на Google Images (всегда сработает)
            if not img:
                img = build_placeholder(a.slug, q_title or q_slug)
                print("placeholder for:", a.slug)

            a.text = inject_figure(a.text or "", img)
            db.session.add(a)
            updated += 1
            time.sleep(0.3)

        db.session.commit()
        print(f"done, updated {updated} articles")

if __name__ == "__main__":
    main()
