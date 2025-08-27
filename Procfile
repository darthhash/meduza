web: gunicorn app:app --bind 0.0.0.0:$PORT
worker: python scripts/purge_and_import.py