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
