FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.9

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

CMD ["celery", "-A", "c_backend.celery_app:celery_app", "worker", "--loglevel=INFO"]
