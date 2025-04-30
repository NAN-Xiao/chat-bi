FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1


ENV SQLBOT_HOME=/opt/sqlbot
ENV APP_HOME=$SQLBOT_HOME/app
ENV UI_HOME=$SQLBOT_HOME/frontend
RUN mkdir -p $APP_HOME
RUN mkdir -p $UI_HOME




WORKDIR $APP_HOME
ENV PYTHONPATH=$APP_HOME

# COPY ../frontend/dist $UI_HOME/dist
COPY ./dist $UI_HOME/dist
# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="$APP_HOME/.venv/bin:$PATH"

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy

# Install dependencies
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN test -f "./uv.lock" && \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project || echo "uv.lock file not found, skipping intermediate-layers"

COPY . $APP_HOME


# Sync the project
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN --mount=type=cache,target=/root/.cache/uv \
   uv sync

CMD ["fastapi", "run", "--workers", "4", "main.py"]
