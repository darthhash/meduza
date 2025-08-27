import os
try:
    # если у тебя фабрика приложений
    from app import create_app
    application = create_app()
except Exception:
    # иначе берём уже созданный app
    from app import app as application

if __name__ == "__main__":
    application.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
