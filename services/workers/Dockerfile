FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcho_workers ./mcho_workers
ENV PYTHONPATH=/app
CMD ["celery", "-A", "mcho_workers.celery_app:app", "worker", "--loglevel=INFO"]
