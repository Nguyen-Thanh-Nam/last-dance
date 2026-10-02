FROM python:3.11-slim AS frontend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /site
COPY FE ./
RUN addgroup --system app && adduser --system --ingroup app app
USER app
EXPOSE 2222
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2222/', timeout=3)"]
CMD ["python", "serve.py", "--bind", "0.0.0.0", "--port", "2222"]

FROM python:3.11-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY requirements-lock.txt ./
COPY BE ./BE
COPY scripts ./scripts
COPY data ./data
COPY docs ./docs
COPY README.md IMPLEMENTATION_PLAN.md ./
RUN python -m pip install -r requirements-lock.txt \
    && python -m pip install --no-deps . \
    && addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /app/runtime \
    && chown -R app:app /app

USER app
ENV DATABASE_PATH=/app/runtime/surface_map.db
ENV PYTHONPATH=/app/BE
EXPOSE 3333
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3333/api/health', timeout=3)"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3333"]
