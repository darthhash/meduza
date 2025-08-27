# app/newsgen.py
from flask import Blueprint, request, jsonify
import os

# защищаем вызов простым токеном из ENV (NEWSGEN_TOKEN)
NEWSGEN_TOKEN = os.getenv("NEWSGEN_TOKEN")

newsgen_bp = Blueprint("newsgen", __name__, url_prefix="/newsgen")

@newsgen_bp.get("/health")
def health():
    return jsonify(ok=True)

def _check_token(req) -> bool:
    if not NEWSGEN_TOKEN:
        return True  # без токена — не проверяем
    token = req.headers.get("X-Token") or req.args.get("token")
    return token == NEWSGEN_TOKEN

@newsgen_bp.post("/run")
def run_generation():
    if not _check_token(request):
        return jsonify(error="unauthorized"), 401

    payload = request.get_json(silent=True) or {}
    # можно задать явную тему ИЛИ собрать её из полей (город/экономика/закон/персона)
    topic = payload.get("topic")
    if not topic:
        city = (payload.get("city") or "").strip()
        sector = (payload.get("economy") or payload.get("sector") or "").strip()
        law = (payload.get("law") or "").strip()
        person = (payload.get("person") or "").strip()
        bits = [b for b in [city, sector or law, person] if b]
        if bits:
            topic = " — ".join(bits)

    n = int(payload.get("n", 1 if topic else 3))
    n = max(1, min(n, 5))  # ограничим, чтобы не спалить бюджет

    last_k = payload.get("last_k")
    half_life = payload.get("half_life")
    ctx_max_chars = payload.get("ctx_max_chars")
    do_import = bool(payload.get("import", False))

    # для выбранной темы переопределяем topics
    topics_override = [topic] if topic else None

    # опционально можно на лету управлять изображениями
    if "image_size" in payload:
        os.environ["IMAGE_SIZE"] = str(payload["image_size"])
    if "image_embed_data_url" in payload:
        os.environ["IMAGE_EMBED_DATA_URL"] = "true" if payload["image_embed_data_url"] else "false"

    from scripts.generate_news_openai import run as newsgen_run
    result = newsgen_run(
        n=n,
        last_k=last_k,
        half_life=half_life,
        ctx_max_chars=ctx_max_chars,
        do_import=do_import,
        topics_override=topics_override
    )
    return jsonify(result), 200
