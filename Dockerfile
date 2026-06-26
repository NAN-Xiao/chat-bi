# Build zhishu
ARG ZHISHU_BASE_IMAGE=zhishu-base:local
ARG ZHISHU_RUNTIME_IMAGE=zhishu-python-pg:local

FROM --platform=${BUILDPLATFORM} ${ZHISHU_BASE_IMAGE} AS zhishu-ui-builder
ARG VITE_API_BASE_URL=./api/v1
ENV ZHISHU_HOME=/opt/zhishu
ENV APP_HOME=${ZHISHU_HOME}/app
ENV UI_HOME=${ZHISHU_HOME}/frontend
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV DEBIAN_FRONTEND=noninteractive

RUN mkdir -p ${APP_HOME} ${UI_HOME}

COPY frontend /tmp/frontend
RUN cd /tmp/frontend && npm install && npm run build && mv dist ${UI_HOME}/dist


FROM ${ZHISHU_BASE_IMAGE} AS zhishu-builder
ARG PYTHON_DEPENDENCY_EXTRA=cpu
# Set build environment variables
ENV PYTHONUNBUFFERED=1
ENV ZHISHU_HOME=/opt/zhishu
ENV APP_HOME=${ZHISHU_HOME}/app
ENV UI_HOME=${ZHISHU_HOME}/frontend
ENV PYTHONPATH=${ZHISHU_HOME}/app
ENV PATH="${APP_HOME}/.venv/bin:$PATH"
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV DEBIAN_FRONTEND=noninteractive

# Create necessary directories
RUN mkdir -p ${APP_HOME} ${UI_HOME}

WORKDIR ${APP_HOME}

COPY  --from=zhishu-ui-builder ${UI_HOME} ${UI_HOME}
COPY backend/pyproject.toml backend/uv.lock ${APP_HOME}/
# Install dependencies from the committed lockfile so CI does not resolve
# fresh dependency candidates on every image build.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra "${PYTHON_DEPENDENCY_EXTRA}" --no-install-project

COPY ./backend ${APP_HOME}

# Final sync to ensure all dependencies are installed
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra "${PYTHON_DEPENDENCY_EXTRA}"

# Build g2-ssr
FROM ${ZHISHU_BASE_IMAGE} AS ssr-builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3 pkg-config \
    libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev \
    libpixman-1-dev libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

# configure npm
RUN npm config set fund false \
    && npm config set audit false \
    && npm config set progress false

COPY g2-ssr/app.js g2-ssr/package.json /app/
COPY g2-ssr/charts/* /app/charts/
RUN npm install

# Runtime stage
FROM ${ZHISHU_RUNTIME_IMAGE}

RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# 复用基础镜像中已安装的 Oracle Instant Client，避免 CI 依赖私有 zip 构建资产。
ENV ORACLE_CLIENT_PATH=/opt/zhishu/db_client/oracle_instant_client
ENV LD_LIBRARY_PATH=${ORACLE_CLIENT_PATH}:${LD_LIBRARY_PATH}

# This runtime image is the all-in-one evaluation image. It starts PostgreSQ0625$0L
# from start.sh and carries development database defaults for first-run demos.
# Production deployments must override secrets and follow the external
# PostgreSQL/Redis/Nginx/worker baseline in docs/single_tenant_production_readiness.md.
# Set runtime environment variables
ENV PYTHONUNBUFFERED=1
ENV ZHISHU_HOME=/opt/zhishu
ENV PYTHONPATH=${ZHISHU_HOME}/app
ENV PATH="${ZHISHU_HOME}/app/.venv/bin:$PATH"

ENV POSTGRES_DB=zhishu_bi
ENV POSTGRES_USER=root
ENV POSTGRES_PASSWORD=Password123@pg

# Copy necessary files from builder
COPY start.sh /opt/zhishu/app/start.sh
COPY g2-ssr/*.ttf /usr/share/fonts/truetype/liberation/
COPY --from=zhishu-builder ${ZHISHU_HOME} ${ZHISHU_HOME}
COPY --from=ssr-builder /app /opt/zhishu/g2-ssr

WORKDIR ${ZHISHU_HOME}/app

RUN mkdir -p /opt/zhishu/images /opt/zhishu/g2-ssr

EXPOSE 3000 8000 8001 5432

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import os, urllib.request; port=os.environ.get('API_PORT','8000'); p=os.environ.get('CONTEXT_PATH','').strip('/'); urllib.request.urlopen(f'http://localhost:{port}/' + ((p + '/') if p else '') + 'health', timeout=3)" || exit 1

ENTRYPOINT ["sh", "start.sh"]
