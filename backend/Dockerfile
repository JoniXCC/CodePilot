# Build context is the project root (see docker-compose.yml) so eval/ and examples/ are available.
FROM python:3.12-slim

# git: CodePilot's git tools. nodejs/npm: running tests of JavaScript target repositories.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    # Mounted repositories are owned by the host user; tell git to trust them.
    && git config --system --add safe.directory '*'

WORKDIR /srv
# Install dependencies first so this layer is cached between code changes.
# Editable install: the code stays in /srv/backend, so app/config.py can find /srv/eval and /srv/examples.
COPY backend/pyproject.toml backend/
RUN mkdir -p backend/app && touch backend/app/__init__.py \
    && pip install --no-cache-dir -e ./backend

COPY backend/ backend/
COPY eval/ eval/
COPY examples/ examples/

WORKDIR /srv/backend
ENV PROJECTS_DIR=/projects \
    DATABASE_URL=sqlite:////data/codepilot.db \
    PYTHONUNBUFFERED=1
RUN mkdir -p /projects /data

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
