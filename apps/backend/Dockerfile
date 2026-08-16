# syntax=docker/dockerfile:1

# Сборка и рантайм разделены: в финальный образ не попадают ни uv, ни dev-зависимости.
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    # Интерпретатор берётся из базового образа: скачивать второй незачем.
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12

WORKDIR /build

# Зависимости ставятся отдельным слоем до копирования исходников: правка кода
# не приводит к переустановке всего дерева пакетов.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Процесс не должен работать от root: контейнер ходит в сеть и в чужие сервисы.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home app

COPY --from=builder --chown=root:root /opt/venv /opt/venv
WORKDIR /srv/app
# Миграции накатываются из контейнера, поэтому вместе с ревизиями нужен и
# alembic.ini: без него alembic не найдёт script_location.
COPY --chown=root:root alembic/ ./alembic/
COPY --chown=root:root alembic.ini ./

USER app
EXPOSE 8000


# HTTP-процесс. Воркеров uvicorn ровно один: масштабирование — репликами
# контейнера, чтобы пул соединений к БД считался на процесс предсказуемо.
FROM runtime AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Фоновый процесс: TaskIQ, консьюмеры RabbitMQ, релей outbox.
FROM runtime AS worker
CMD ["python", "-m", "app.worker"]
