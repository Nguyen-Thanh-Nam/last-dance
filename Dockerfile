FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY docs ./docs
COPY README.md IMPLEMENTATION_PLAN.md ./
RUN python -m pip install . \
    && addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /app/runtime \
    && chown -R app:app /app

USER app
ENV DATABASE_PATH=/app/runtime/surface_map.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
