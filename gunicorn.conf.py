# gunicorn.conf.py
import os
bind        = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers     = int(os.getenv('WEB_CONCURRENCY', '2'))
threads     = int(os.getenv('GUNICORN_THREADS', '8'))
timeout     = int(os.getenv('GUNICORN_TIMEOUT', '180'))
keepalive   = int(os.getenv('GUNICORN_KEEPALIVE', '2'))
