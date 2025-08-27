# scripts/generate_news_openai.py  — фрагмент: замените класс OpenAIChat целиком
import os, re

def _clean_openai_env_nonascii() -> list[tuple[str,str]]:
    """Выбрасываем org/project из ENV, если там не-ASCII (httpx не любит это в заголовках)."""
    bad = []
    for key in ("OPENAI_PROJECT", "OPENAI_ORGANIZATION", "OPENAI_ORG_ID", "OPENAI_ORG"):
        val = os.getenv(key)
        if val and not val.isascii():
            bad.append((key, val))
            os.environ.pop(key, None)
    return bad

def _sanitize_api_key(k: str) -> str:
    """Чистим мусор: умные дефисы, NBSP, кавычки, хвосты X00A/0D0A. Валидируем ASCII и префикс."""
    if not k:
        return k
    k = k.strip()
    # заменить все юникод-дефисы на "-"
    for ch in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212":
        k = k.replace(ch, "-")
    # убрать NBSP и пробелы
    k = k.replace("\u00A0","").replace(" ", "")
    # убрать кавычки
    for ch in ('“','”','„','«','»',"'",'"','`'):
        k = k.replace(ch, "")
    # срезать типичные хвосты копипасты: X00A/0A/0D0A и т.п.
    k = re.sub(r'(?:X?0D0A|X?0A|X?0D)$', '', k, flags=re.IGNORECASE)
    if not k.isascii():
        bad = ''.join(sorted(set(c for c in k if not c.isascii())))
        raise ValueError(f"OPENAI_API_KEY contains non-ASCII characters: {repr(bad)}")
    if not (k.startswith("sk-") or k.startswith("sk_prov-") or k.startswith("sk-proj-")):
        raise ValueError("OPENAI_API_KEY looks invalid (expected to start with 'sk-').")
    return k

class OpenAIChat:
    def __init__(self, model: str, max_tokens: int = 900, temperature: float = 0.7):
        raw_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or ""
        if not raw_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        api_key = _sanitize_api_key(raw_key)

        # убрать не-ASCII org/project из окружения (на всякий)
        bad = _clean_openai_env_nonascii()
        if bad:
            print("[warn] dropped non-ASCII OpenAI env:", ", ".join(k for k,_ in bad))

        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)  # НЕ прокидываем organization/project
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat_json(self, system: str, user: str) -> str:
        from openai import AuthenticationError
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type":"json_object"},
            )
            return resp.choices[0].message.content.strip()
        except AuthenticationError as e:
            # отдаём наверх, чтобы вернулось 401 с нормальным текстом
            raise
        except Exception:
            # fallback без response_format
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"system","content":system},{"role":"user","content":user + "\n\nВерни СТРОГО один JSON-объект."}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return resp.choices[0].message.content.strip()
# === ПУБЛИЧНЫЙ API ДЛЯ БЛЮПРИНТА =============================================

__all__ = ["run", "OpenAIChat", "ImageBackend"]

def run(
    n: int = 3,
    last_k: int | None = None,
    half_life: int | None = None,
    ctx_max_chars: int | None = None,
    do_import: bool = False,
    topics_override: list[str] | None = None,
) -> dict:
    """
    Генерит N вымышленных статей и (опционально) импортит их в БД.
    Возвращает dict: {articles, topics, context, imported}
    """
    import os
    from datetime import datetime

    # 1) параметры
    last_k        = last_k or int(os.getenv("LAST_K", "40"))
    half_life     = half_life or int(os.getenv("HALF_LIFE", "10"))
    ctx_max_chars = ctx_max_chars or int(os.getenv("CTX_MAX_CHARS", "8000"))
    max_tokens    = int(os.getenv("MAX_TOKENS", "1024"))
    temperature   = float(os.getenv("TEMPERATURE", "0.7"))
    model_id      = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # 2) история → контекст/темы
    history = fetch_recent_articles_from_db(limit=last_k)
    context = build_context(history, last_k=last_k, half_life=half_life, max_chars=ctx_max_chars)
    topics  = topics_override or derive_topics(history, n=n, last_k=last_k, half_life=half_life)

    # 3) клиенты
    chat   = OpenAIChat(model=model_id, max_tokens=max_tokens, temperature=temperature)
    images = ImageBackend()

    # 4) генерация
    articles = []
    for i, t in enumerate(topics):
        art = generate_one(chat, images, t, context)
        art["section"] = "main" if i == 0 else "list"
        art["created_at"] = art.get("created_at") or datetime.utcnow().isoformat()
        articles.append(art)

    # 5) payload + импорт (по желанию)
    write_payload(articles, path="scripts/articles_payload.py")

    imported = False
    if do_import:
        try:
            from scripts.import_articles import import_articles
            import_articles(articles)
            imported = True
        except Exception as e:
            print("[warn] import_articles failed:", e)

    return {
        "articles": articles,
        "topics": topics,
        "context": context,
        "imported": imported,
    }


# === CLI (для локального запуска, не мешает блюпринту) =======================

if __name__ == "__main__":
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--last-k", type=int, dest="last_k")
    p.add_argument("--half-life", type=int, dest="half_life")
    p.add_argument("--ctx-max-chars", type=int, dest="ctx_max_chars")
    p.add_argument("--import", dest="do_import", action="store_true")
    args = p.parse_args()

    out = run(
        n=args.n,
        last_k=args.last_k,
        half_life=args.half_life,
        ctx_max_chars=args.ctx_max_chars,
        do_import=args.do_import,
    )
    print(json.dumps(out, ensure_ascii=False)[:1000])