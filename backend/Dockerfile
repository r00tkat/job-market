FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy project files first so `pip install .` can see the package source.
COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY alembic ./alembic
COPY data ./data

RUN pip install --no-cache-dir .

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Run migrations, then start the API. Secrets (DATABASE_URL) are provided at
# runtime via environment variables and are never baked into the image.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
