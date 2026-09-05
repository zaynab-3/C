FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.9

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src

RUN uv sync --frozen --no-dev --offline

RUN useradd --create-home --uid 10001 cuser

ENV PATH="/app/.venv/bin:$PATH"

USER cuser

CMD ["celery", "-A", "c_backend.celery_app:celery_app", "worker", "--loglevel=INFO"]
