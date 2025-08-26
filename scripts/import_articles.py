# scripts/import_articles.py
import os, sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath("."))
from app import app, db, Article

try:
    from scripts.articles_payload import ARTICLES
except Exception as e:
    print("ERROR: cannot import scripts.articles_payload:", e)
    ARTICLES = []

def to_dt(val: Any):
    if not val: return None
    if isinstance(val, datetime): return val
    s = str(val).replace("Z","")
    for fmt in ("%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S"):
        try: return datetime.strptime(s[:19], fmt)
        except Exception: pass
    try: return datetime.fromisoformat(s)
    except Exception: return None

def norm_section(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in {"main","side","list"} else "list"

def choose_text(item: Dict[str, Any]) -> str:
    for k in ("content_html","content","text"):
        v = item.get(k)
        if v: return str(v)
    return ""

def to_tags_string(tags_val) -> str:
    if not tags_val: return ""
    if isinstance(tags_val, str):
        # нормализуем "a, b ,c"
        parts = [p.strip() for p in tags_val.split(",") if p.strip()]
        return ", ".join(parts)
    if isinstance(tags_val, (list, tuple)):
        parts = [str(p).strip() for p in tags_val if str(p).strip()]
        return ", ".join(parts)
    return str(tags_val)

def import_articles():
    with app.app_context():
        db.create_all()
        added, updated = 0, 0
        for it in ARTICLES:
            slug = (it.get("slug") or "").strip()
            title = (it.get("title") or "").strip()
            if not slug:
                print("skip (no slug):", title[:80]); continue
            text = choose_text(it)
            section = norm_section(it.get("section"))
            created_at = to_dt(it.get("created_at")) or datetime.utcnow()
            tags = to_tags_string(it.get("tags"))

            obj = Article.query.filter_by(slug=slug).first()
            if not obj:
                obj = Article(slug=slug); db.session.add(obj); added += 1
            else:
                updated += 1

            obj.title = title or obj.title or slug
            obj.text = text
            obj.section = section
            obj.tags = tags
            if not obj.created_at:
                obj.created_at = created_at

        db.session.commit()
        print(f"imported: added={added}, updated={updated}")

if __name__ == "__main__":
    import_articles()
