# scripts/import_articles.py
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.abspath("."))

from app import app, db, Article
from sqlalchemy.exc import IntegrityError

# грузим ARTICLES из scripts/articles_payload.py
try:
    from scripts.articles_payload import ARTICLES
except Exception as e:
    print("ERROR: cannot import scripts.articles_payload:", e)
    ARTICLES = []

def re_slugify(title: str) -> str:
    import re
    TRANS = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i',
        'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
        'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ы':'y','э':'e','ю':'yu','я':'ya','ь':'','ъ':''
    }
    s = (title or "").lower().strip()
    s = "".join(TRANS.get(ch, ch) for ch in s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "article"

def import_articles():
    with app.app_context():
        db.create_all()
        added, updated = 0, 0
        for item in ARTICLES:
            title = (item.get("title") or "").strip()
            text = item.get("text") or ""
            section = item.get("section") or "list"
            slug = (item.get("slug") or "").strip() or re_slugify(title)

            obj = Article.query.filter_by(slug=slug).first()
            if obj:
                changed = False
                if title and obj.title != title:
                    obj.title = title; changed = True
                if text and obj.text != text:
                    obj.text = text; changed = True
                if section and obj.section != section:
                    obj.section = section; changed = True
                if changed:
                    updated += 1
            else:
                obj = Article(slug=slug, title=title, text=text, section=section)
                db.session.add(obj)
                added += 1

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            print("IntegrityError:", e)

        print(f"Imported payloads: added={added}, updated={updated}")

if __name__ == "__main__":
    import_articles()
