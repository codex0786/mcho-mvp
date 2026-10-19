FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /api
COPY services/api/pyproject.toml ./pyproject.toml
COPY services/api/app ./app
RUN pip install --no-cache-dir .
WORKDIR /worker
COPY services/workers/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/workers/mcho_workers ./mcho_workers
ENV PYTHONPATH=/api:/worker
RUN useradd --create-home --uid 10002 worker && chown -R worker:worker /api /worker
USER worker
CMD ["celery", "-A", "mcho_workers.celery_app:app", "worker", "--loglevel=INFO"]
