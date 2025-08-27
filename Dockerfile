FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway прокидывает PORT; по умолчанию 8000
ENV PORT=8000
CMD ["python","-m","gunicorn","wsgi:application","--bind","0.0.0.0:${PORT}","--workers","2","--threads","4","--timeout","120"]
