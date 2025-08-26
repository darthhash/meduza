# scripts/fetch_images_openverse.py
import os, sys, re, html
from datetime import datetime
from urllib.parse import quote_plus

import requests

# импортируем приложение/модель
sys.path.insert(0, os.path.abspath("."))
from app import app, db, Article  # noqa

OPENVERSE_API = "https://api.openverse.engineering/v1/images/"

FIGURE_RE = re.compile(r'<figure[^>]+class="[^"]*article-hero[^"]*"[^>]*>', re.I)

def search_image(query: str):
    """Ищем одно CC0/Public Domain изображение под запрос."""
    params = {
        "q": query,
        "license": "cc0,publicdomain",
        "page_size": 1,
        "extension": "jpg",  # чаще безопасно
    }
    try:
        r = requests.get(OPENVERSE_API, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return None
        it = results[0]
        return {
            "url": it.get("url") or it.get("thumbnail"),
            "title": it.get("title") or query,
            "source": it.get("source") or "Openverse",
            "landing": it.get("foreign_landing_url"),
            "license": (it.get("license") or "cc0").upper()
        }
    except Exception as e:
        print("search_image error:", e)
        return None

def inject_figure(html_text: str, img):
    """Вставляем <figure> в начало контента, если его ещё нет."""
    if not img or not img.get("url"):
        return html_text
    if FIGURE_RE.search(html_text or ""):
        return html_text  # уже есть

    cap = f'Источник: <a href="{html.escape(img.get("landing") or img["url"])}" rel="noopener" target="_blank">{html.escape(img["source"])}</a> ({html.escape(img["license"])})'
    figure = (
        '<figure class="article-hero">'
        f'<img src="{html.escape(img["url"])}" alt="{html.escape(img["title"])}" />'
        f'<figcaption>{cap}</figcaption>'
        '</figure>\n'
    )
    return (figure + (html_text or "")).strip()

def main():
    with app.app_context():
        updated = 0
        arts = Article.query.order_by(Article.created_at.desc()).all()
        for a in arts:
            if FIGURE_RE.search(a.text or ""):
                continue  # уже есть
            img = search_image(a.title)
            if not img:
                print("no image for:", a.slug)
                continue
            a.text = inject_figure(a.text or "", img)
            db.session.add(a)
            updated += 1
        db.session.commit()
        print(f"done, updated {updated} articles")

if __name__ == "__main__":
    main()
