# app/newsgen.py
from flask import Blueprint, request, jsonify, current_app
import os, hmac, traceback

newsgen_bp = Blueprint("newsgen", __name__, url_prefix="/newsgen")

def _secure_compare(a: str, b: str) -> bool:
    try:
        return hmac.compare_digest((a or "").strip(), (b or "").strip())
    except Exception:
        return False

def _check_token(req) -> bool:
    token_env = (os.getenv("NEWSGEN_TOKEN") or "").strip()
    if not token_env:
        return True  # если переменной нет — доступ открыт (для отладки)
    presented = (
        (req.headers.get("X-Token") or "").strip() or
        (req.args.get("token") or "").strip() or
        (req.headers.get("Authorization","").removeprefix("Bearer ").strip())
    )
    return _secure_compare(presented, token_env)

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
        # конструктор темы из частей (город/экономика/закон/персона)
        city   = (payload.get("city")   or "").strip()
        sector = (payload.get("economy") or payload.get("sector") or "").strip()
        law    = (payload.get("law")    or "").strip()
        person = (payload.get("person") or "").strip()
        bits = [b for b in (city, sector or law, person) if b]
        topic = " — ".join(bits) if bits else ""

    n = int(payload.get("n", 1 if topic else 3))
    n = max(1, min(n, 5))

    last_k       = payload.get("last_k")
    half_life    = payload.get("half_life")
    ctx_max      = payload.get("ctx_max_chars")
    do_import    = bool(payload.get("import", False))

    # управление изображениями на лету
    if "image_size" in payload:
        os.environ["IMAGE_SIZE"] = str(payload["image_size"])
    if "image_embed_data_url" in payload:
        os.environ["IMAGE_EMBED_DATA_URL"] = "true" if payload["image_embed_data_url"] else "false"

    try:
        # быстрые пред-проверки окружения
        if not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")):
            return jsonify(error="OPENAI_API_KEY is missing"), 400
        # если не хочешь реальную генерацию картинок — насильно ставим плейсхолдер
        if not os.getenv("IMAGE_BACKEND"):
            os.environ["IMAGE_BACKEND"] = "placeholder"

        from scripts.generate_news_openai import run as newsgen_run
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
        # логируем полный трейс в stdout (увидишь в логах Railway)
        traceback.print_exc()
        # в ответ — компактная причина (без секретов)
        return jsonify(error=str(e.__class__.__name__), detail=str(e)), 500

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

    # проверка базы
    try:
        from app import app as _flask_app
        from app import db as _db
        with _flask_app.app_context():
            _db.session.execute(_db.text("SELECT 1"))
        out["db_ok"] = True
    except Exception as e:
        out["db_ok"] = f"error: {e}"

    # легкий пробный вызов без импорта (не делает полноценную генерацию, только попытку инициализации)
    try:
        from scripts.generate_news_openai import OpenAIChat, ImageBackend  # type: ignore
        _ = OpenAIChat(os.getenv("OPENAI_MODEL", "gpt-4o-mini"), max_tokens=10)
        _ = ImageBackend()
        out["can_generate"] = True
    except Exception as e:
        out["can_generate"] = f"error: {e}"

    return jsonify(out), 200
