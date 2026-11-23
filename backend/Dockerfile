FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# pg_dump 16, the server's version, for the dump taken before migrations (app/migrate.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-common \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*
ENV PG_DUMP=/usr/lib/postgresql/16/bin/pg_dump

# Install dependencies only (the app itself runs from /app source).
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install ".[dev]" && pip uninstall -y testharbor-backend && rm -rf app build *.egg-info

COPY . .

EXPOSE 8000
CMD ["sh", "/app/docker-entrypoint.sh"]
