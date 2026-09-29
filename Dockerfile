FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY docs ./docs
COPY README.md IMPLEMENTATION_PLAN.md ./
RUN pip install --no-cache-dir .
ENV DATABASE_PATH=/app/runtime/surface_map.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
