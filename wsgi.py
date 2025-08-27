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

# 2) Фолбэк: топ-левел app.py с объектом app
if application is None:
    root = pathlib.Path(__file__).resolve().parent
    app_py = root / "app.py"
    try:
        if app_py.exists():
            spec = importlib.util.spec_from_file_location("app_legacy", str(app_py))
            mod = importlib.util.module_from_spec(spec)  # type: ignore
            assert spec and spec.loader
            spec.loader.exec_module(mod)  # type: ignore
            if hasattr(mod, "app"):
                application = getattr(mod, "app")
                print("[ok] loaded legacy app from app.py")
    except Exception as e:
        print("[warn] legacy app.py load failed:", e)

# 3) Если подняли legacy-приложение — аккуратно навесим newsgen (если есть)
try:
    if application is not None:
        from flask import Flask  # type: ignore
        if isinstance(application, Flask):
            try:
                from app.newsgen import newsgen_bp  # type: ignore
                application.register_blueprint(newsgen_bp)
                print("[ok] registered newsgen blueprint on legacy app")
            except Exception as e:
                print("[warn] no newsgen blueprint:", e)
except Exception as e:
    print("[warn] blueprint attach failed:", e)

if application is None:
    raise RuntimeError("WSGI application not found (neither app.create_app() nor app.py:app)")
