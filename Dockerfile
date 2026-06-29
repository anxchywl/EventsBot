FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN addgroup --system app && adduser --system --ingroup app app
USER app

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "app.main"]
