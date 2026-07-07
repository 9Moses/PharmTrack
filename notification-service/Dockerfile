FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput || true
EXPOSE 8002
CMD ["gunicorn", "pharmtrack_notification.wsgi:application", "--bind", "0.0.0.0:8002", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
