# scripts/import_articles.py
import os
import sys
# предполагается, что этот скрипт запускают из корня репозитория
sys.path.insert(0, os.path.abspath("."))

from app import app, db, Article  # у тебя в app.py должны быть эти имена
from sqlalchemy.exc import IntegrityError

# список ARTICLES можно либо импортировать из отдельного файла, либо вставить прямо сюда.
ARTICLES = [ 
    # вставь сюда тот же список ARTICLES, который я дал выше (все словари)
]

def import_articles():
    with app.app_context():
        added = 0
        for item in ARTICLES:
            slug = item["slug"]
            existing = Article.query.filter_by(slug=slug).first()
            if existing:
                print(f"Пропускаю (уже есть): {slug} — {existing.title}")
                continue
            a = Article(title=item["title"], text=item["text"], slug=item["slug"], section=item.get("section","list"))
            db.session.add(a)
            try:
                db.session.commit()
                print(f"Добавлена: {slug}")
                added += 1
            except IntegrityError:
                db.session.rollback()
                print(f"Ошибка при добавлении (конфликт slugs?): {slug}")
        print(f"Импорт завершён. Добавлено записей: {added}")

if __name__ == "__main__":
    import_articles()
