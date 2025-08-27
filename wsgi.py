# wsgi.py
import importlib.util
import pathlib
from typing import Any

application: Any = None
from dotenv import load_dotenv; load_dotenv()

# 1) Пробуем пакетный вариант: app/__init__.py → create_app()
try:
    from app import create_app  # type: ignore
    application = create_app()
except Exception as e:
    print("[warn] create_app() not usable:", e)

