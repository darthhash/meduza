# app/newsgen.py
from flask import Blueprint, request, jsonify
import os, hmac, traceback

newsgen_bp = Blueprint("newsgen", __name__, url_prefix="/newsgen")

def _sec_eq(a: str, b: str) -> bool:
    try: return hmac.compare_digest((a or "").strip(), (b or "").strip())
    except Exception: return False

def _check_token(req) -> bool:
    t = (os.getenv("NEWSGEN_TOKEN") or "").strip()
    if not t:
        return True  # без токена в ENV пускаем — удобно для отладки
    presented = (
        (req.headers.get("X-Token") or "").strip()
        or (req.args.get("token") or "").strip()
        or (req.headers.get("Authorization","").removeprefix("Bearer ").strip())
    )
    return _sec_eq(presented, t)

@newsgen_bp.get("/health")
def health():
    return jsonify(ok=True)

@newsgen_bp.post("/run")
def run_generation():
    if not _check_token(request):
        return jsonify(error="unauthorized"), 401

    payload = request.get_json(silent=True) or {}
    topic = (payload.get("topic") or "").strip()
    if not topic:
        city   = (payload.get("city") or "").strip()
        sector = (payload.get("economy") or payload.get("sector") or "").strip()
        law    = (payload.get("law") or "").strip()
        person = (payload.get("person") or "").strip()
        bits = [b for b in (city, sector or law, person) if b]
        topic = " — ".join(bits) if bits else ""

    n = int(payload.get("n", 1 if topic else 3))
    n = max(1, min(n, 5))

    # параметры контекста
    last_k    = payload.get("last_k")
    half_life = payload.get("half_life")
    ctx_max   = payload.get("ctx_max_chars")
    do_import = bool(payload.get("import", False))

    # управление картинками на лету
    if "image_size" in payload:
        os.environ["IMAGE_SIZE"] = str(payload["image_size"])
    if "image_embed_data_url" in payload:
        os.environ["IMAGE_EMBED_DATA_URL"] = "true" if payload["image_embed_data_url"] else "false"

    try:
        if not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")):
            return jsonify(error="OPENAI_API_KEY is missing"), 400

        # по умолчанию — плейсхолдер (чтобы не упираться в gpt-image-1)
        os.environ.setdefault("IMAGE_BACKEND", "placeholder")

        from scripts.generate_news_openai import run as newsgen_run  # твой файл из прошлых шагов
        topics_override = [topic] if topic else None
        res = newsgen_run(
            n=n,
            last_k=last_k,
            half_life=half_life,
            ctx_max_chars=ctx_max,
            do_import=do_import,
            topics_override=topics_override
        )
        return jsonify(res), 200

    except BaseException as e:  # ловим даже SystemExit
        traceback.print_exc()
        return jsonify(error=e.__class__.__name__, detail=str(e)), 500

@newsgen_bp.get("/diagnose")
def diagnose():
    if not _check_token(request):
        return jsonify(error="unauthorized"), 401

    out = {
        "env": {
            "OPENAI_API_KEY_present": bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")),
            "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "IMAGE_BACKEND": os.getenv("IMAGE_BACKEND", "placeholder"),
            "IMAGE_SIZE": os.getenv("IMAGE_SIZE", "1024x1024"),
        },
        "db_ok": None,
        "can_generate": None,
    }

    # БД-пинг
    try:
        from app import app as _flask_app, db as _db
        from sqlalchemy import text as sql_text
        with _flask_app.app_context():
            _db.session.execute(sql_text("SET client_encoding TO 'UTF8'"))
            _db.session.execute(sql_text("SELECT 1"))
        out["db_ok"] = True
    except Exception as e:
        out["db_ok"] = f"error: {e}"

    # инициализация клиентов
    try:
        from scripts.generate_news_openai import OpenAIChat, ImageBackend  # type: ignore
        _ = OpenAIChat(os.getenv("OPENAI_MODEL", "gpt-4o-mini"), max_tokens=10)
        _ = ImageBackend()
        out["can_generate"] = True
    except Exception as e:
        out["can_generate"] = f"error: {e}"

    return jsonify(out), 200
