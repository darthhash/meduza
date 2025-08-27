# из корня проекта
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip

# если у тебя есть requirements.txt — ставь из него
pip install -r requirements.txt || true

# на всякий случай дотянем нужное
pip install "Flask>=3,<4" "Flask-SQLAlchemy>=3.1" "Flask-Migrate>=4.0" \
            "SQLAlchemy>=2" "psycopg2-binary>=2.9" "gunicorn>=21" \
            "openai>=1.40" "requests>=2.31" "python-dotenv>=1.0" "python-slugify>=8"
