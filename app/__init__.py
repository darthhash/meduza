# app/__init__.py
"""Proxy module to re-export objects from top-level app.py so that
"from app import app, db, Article, slugify" works even though there is also an
"app/" package. Also optionally registers the newsgen blueprint if present.
"""
import os, importlib.util, types

_BASE = os.path.dirname(os.path.dirname(__file__))
_APP_PY = os.path.join(_BASE, "app.py")

spec = importlib.util.spec_from_file_location("app_main", _APP_PY)
app_main = importlib.util.module_from_spec(spec)  # type: ignore
assert spec and spec.loader, "cannot build spec for app.py"
spec.loader.exec_module(app_main)  # type: ignore

# re-export
app = getattr(app_main, "app", None)
db = getattr(app_main, "db", None)
Article = getattr(app_main, "Article", None)
slugify = getattr(app_main, "slugify", None)

# опционально: регистрируем блюпринт newsgen, если он есть
try:
    from .newsgen import newsgen_bp  # noqa
    if app is not None:
        app.register_blueprint(newsgen_bp)
except Exception:
    pass

def create_app():
    return app
