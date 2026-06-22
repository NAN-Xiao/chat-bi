pipeline {
  agent any

  options {
    timestamps()
    skipDefaultCheckout(true)
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    string(name: 'BRANCH_NAME', defaultValue: '单用户高可用', description: 'Git 分支')
    string(name: 'IMAGE_TAG', defaultValue: '', description: '镜像标签，留空时使用 BUILD_NUMBER-git短哈希')
    booleanParam(name: 'CLEAN_DANGLING_IMAGES', defaultValue: false, description: '是否清理悬空镜像。默认关闭以保留 Docker 构建缓存')
  }

  environment {
    DOCKER_BUILDKIT = '1'
    BUILDKIT_PROGRESS = 'plain'
    GIT_URL = 'https://github.com/NAN-Xiao/chat-bi.git'
    APP_HOME = '/home/chat-bi'
    CONTAINER_NAME = 'chat-bi'
    IMAGE_REPOSITORY = 'chat-bi/sqlbot'
    SQLBOT_BASE_IMAGE = 'registry.cn-qingdao.aliyuncs.com/dataease/sqlbot-base:latest'
    SQLBOT_RUNTIME_IMAGE = 'registry.cn-qingdao.aliyuncs.com/dataease/sqlbot-python-pg:latest'
    FRONTEND_HOST = '10.1.5.193'
    NGINX_PORT = '80'
    NGINX_ROOT = '/home/chat-bi/nginx/html'
    NGINX_CONF_PATH = '/etc/nginx/conf.d/chat-bi.conf'
    INSTALL_CONF_FILE = '/home/chat-bi/install.conf'
    RUNTIME_ENV_FILE = '/home/chat-bi/chat-bi.runtime.env'
    WEB_PORT = '8000'
    MCP_PORT = '8001'
  }

  stages {
    stage('拉取代码') {
      steps {
        git branch: params.BRANCH_NAME, url: env.GIT_URL
      }
    }

    stage('准备构建参数') {
      steps {
        script {
          def shortCommit = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          env.EFFECTIVE_IMAGE_TAG = params.IMAGE_TAG?.trim() ? params.IMAGE_TAG.trim() : "${env.BUILD_NUMBER}-${shortCommit}"
          env.IMAGE = "${env.IMAGE_REPOSITORY}:${env.EFFECTIVE_IMAGE_TAG}"
          env.BUILD_AT = sh(script: "TZ=Asia/Shanghai date +'%Y-%m-%dT%H:%M'", returnStdout: true).trim()
          env.GITHUB_COMMIT = shortCommit
          env.FRONTEND_API_BASE_URL = "./api/v1"
          env.PYTHON_DEPENDENCY_EXTRA = "cpu"
          env.CLEAN_DANGLING_IMAGES = params.CLEAN_DANGLING_IMAGES.toString()
        }
        sh '''
          set -eux
          case "$EFFECTIVE_IMAGE_TAG" in
            *[!A-Za-z0-9_.-]*|'')
              echo "镜像标签不合法：$EFFECTIVE_IMAGE_TAG。只允许字母、数字、下划线、点和中横线。"
              exit 1
              ;;
          esac
          command -v git
          command -v docker
          docker version
          if ! docker buildx version; then
            mkdir -p /root/.docker/cli-plugins
            if [ -x "$APP_HOME/docker-buildx" ]; then
              cp "$APP_HOME/docker-buildx" /root/.docker/cli-plugins/docker-buildx
              chmod +x /root/.docker/cli-plugins/docker-buildx
            fi
            docker buildx version
          fi
          echo "Python 依赖类型：${PYTHON_DEPENDENCY_EXTRA:-cpu}"
          echo "是否清理悬空镜像：${CLEAN_DANGLING_IMAGES:-false}"
          if ! mkdir -p "$APP_HOME" "$APP_HOME/data/sqlbot/excel" "$APP_HOME/data/sqlbot/file" "$APP_HOME/data/sqlbot/images" "$APP_HOME/data/sqlbot/logs" "$APP_HOME/data/postgresql" "$NGINX_ROOT"; then
            echo "Jenkins 用户没有 $APP_HOME 写入权限，请先在 Linux 服务器执行：sudo mkdir -p $APP_HOME && sudo chown -R $(id -u):$(id -g) $APP_HOME"
            exit 1
          fi
          test -w "$APP_HOME" || { echo "Jenkins 用户没有 $APP_HOME 写入权限，请先在 Linux 服务器执行：sudo mkdir -p $APP_HOME && sudo chown -R $(id -u):$(id -g) $APP_HOME"; exit 1; }
          if [ ! -f "$INSTALL_CONF_FILE" ]; then
            echo "缺少运行配置文件：$INSTALL_CONF_FILE"
            echo "请先按仓库 installer/install.conf 模板在服务器上创建该文件，并填写 ZHISHU_API_PORTS、ZHISHU_WORKER_IDS、Redis、数据库和密钥配置。"
            exit 1
          fi

          set +x
          set -a
          . "$INSTALL_CONF_FILE"
          set +a
          : "${ZHISHU_API_PORTS:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_API_PORTS}"
          : "${ZHISHU_WORKER_IDS:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_WORKER_IDS}"
          : "${ZHISHU_CACHE_TYPE:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_CACHE_TYPE}"
          : "${ZHISHU_REDIS_HOST:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_REDIS_HOST}"
          : "${ZHISHU_REDIS_PORT:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_REDIS_PORT}"
          : "${ZHISHU_TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS}"
          : "${ZHISHU_TASK_QUEUE_REQUEUE_INTERVAL_SECONDS:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_TASK_QUEUE_REQUEUE_INTERVAL_SECONDS}"
          {
            echo "PROJECT_NAME=星通智数"
            echo "POSTGRES_SERVER=${ZHISHU_DB_HOST}"
            echo "POSTGRES_PORT=${ZHISHU_DB_PORT}"
            echo "POSTGRES_DB=${ZHISHU_DB_DB}"
            echo "POSTGRES_USER=${ZHISHU_DB_USER}"
            echo "POSTGRES_PASSWORD=${ZHISHU_DB_PASSWORD}"
            echo "SECRET_KEY=${ZHISHU_SECRET_KEY}"
            echo "DEFAULT_PWD=${ZHISHU_DEFAULT_PWD}"
            echo "FRONTEND_HOST=http://${FRONTEND_HOST}"
            echo "BACKEND_CORS_ORIGINS=${ZHISHU_CORS_ORIGINS}"
            echo "SERVER_IMAGE_HOST=${ZHISHU_SERVER_IMAGE_HOST}"
            echo "LOG_LEVEL=${ZHISHU_LOG_LEVEL}"
            echo "SQL_DEBUG=false"
            echo "BASE_DIR=/opt/sqlbot"
            echo "UPLOAD_DIR=/opt/sqlbot/data/file"
            echo "EXCEL_PATH=/opt/sqlbot/data/excel"
            echo "MCP_IMAGE_PATH=/opt/sqlbot/images"
            echo "LOG_DIR=/opt/sqlbot/app/logs"
            echo "LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"
            echo "AUTO_MIGRATE_ON_STARTUP=false"
            echo "CACHE_TYPE=${ZHISHU_CACHE_TYPE}"
            echo "REDIS_HOST=${ZHISHU_REDIS_HOST}"
            echo "REDIS_PORT=${ZHISHU_REDIS_PORT}"
            echo "REDIS_DB=${ZHISHU_REDIS_DB}"
            echo "REDIS_USERNAME=${ZHISHU_REDIS_USERNAME}"
            echo "REDIS_PASSWORD=${ZHISHU_REDIS_PASSWORD}"
            echo "REDIS_SSL=${ZHISHU_REDIS_SSL}"
            echo "REDIS_KEY_PREFIX=${ZHISHU_REDIS_KEY_PREFIX}"
            echo "TASK_QUEUE_NAME=${ZHISHU_TASK_QUEUE_NAME}"
            echo "TASK_QUEUE_RESULT_TTL_SECONDS=${ZHISHU_TASK_QUEUE_RESULT_TTL_SECONDS}"
            echo "TASK_QUEUE_POLL_TIMEOUT_SECONDS=${ZHISHU_TASK_QUEUE_POLL_TIMEOUT_SECONDS}"
            echo "TASK_QUEUE_MAX_ATTEMPTS=${ZHISHU_TASK_QUEUE_MAX_ATTEMPTS}"
            echo "TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS=${ZHISHU_TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS}"
            echo "TASK_QUEUE_REQUEUE_INTERVAL_SECONDS=${ZHISHU_TASK_QUEUE_REQUEUE_INTERVAL_SECONDS}"
            echo "EMBEDDING_MODEL=${ZHISHU_EMBEDDING_MODEL}"
            echo "EMBEDDING_API_BASE_URL=${ZHISHU_EMBEDDING_API_BASE_URL}"
            echo "EMBEDDING_API_KEY=${ZHISHU_EMBEDDING_API_KEY}"
            echo "MCP_ENABLED=${ZHISHU_MCP_ENABLED}"
            echo "ACCESS_TOKEN_EXPIRE_MINUTES=${ZHISHU_ACCESS_TOKEN_EXPIRE_MINUTES}"
            echo "CONTEXT_PATH=${ZHISHU_CONTEXT_PATH}"
          } > "$RUNTIME_ENV_FILE"
          chmod 600 "$RUNTIME_ENV_FILE"
          set -x
          grep -E '^(POSTGRES_SERVER|POSTGRES_PORT|POSTGRES_DB|POSTGRES_USER|FRONTEND_HOST|BACKEND_CORS_ORIGINS|CACHE_TYPE)=' "$RUNTIME_ENV_FILE" || true
        '''
      }
    }

    stage('构建 Docker 镜像') {
      steps {
        sh '''
          set -eux
          docker buildx inspect --bootstrap
          docker buildx build \
            --load \
            --tag "$IMAGE" \
            --build-arg BUILD_AT="$BUILD_AT" \
            --build-arg GITHUB_COMMIT="$GITHUB_COMMIT" \
            --build-arg SQLBOT_BASE_IMAGE="$SQLBOT_BASE_IMAGE" \
            --build-arg SQLBOT_RUNTIME_IMAGE="$SQLBOT_RUNTIME_IMAGE" \
            --build-arg VITE_API_BASE_URL="$FRONTEND_API_BASE_URL" \
            --build-arg PYTHON_DEPENDENCY_EXTRA="$PYTHON_DEPENDENCY_EXTRA" \
            .
        '''
      }
    }

    stage('生成并安装 Nginx 配置') {
      steps {
        sh '''
          set -eux
          set +x
          set -a
          . "$INSTALL_CONF_FILE"
          set +a
          : "${ZHISHU_API_PORTS:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_API_PORTS}"
          set -x
          DOLLAR='$'
          api_ports="$ZHISHU_API_PORTS"
          cat > "$APP_HOME/chat-bi-nginx.conf" <<EOF
upstream chat_bi_backend {
    least_conn;
EOF
          for api_port in $api_ports; do
            echo "    server 127.0.0.1:${api_port} max_fails=3 fail_timeout=10s;" >> "$APP_HOME/chat-bi-nginx.conf"
          done
          cat >> "$APP_HOME/chat-bi-nginx.conf" <<EOF
}

server {
    listen ${NGINX_PORT};
    server_name ${FRONTEND_HOST};

    root ${NGINX_ROOT};
    index index.html;

    client_max_body_size 200m;

    location / {
        try_files ${DOLLAR}uri ${DOLLAR}uri/ /index.html;
    }

    location /api/v1/ {
        proxy_pass http://chat_bi_backend/api/v1/;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location = /openapi.json {
        proxy_pass http://chat_bi_backend/openapi.json;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /docs {
        proxy_pass http://chat_bi_backend/docs;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /images/ {
        proxy_pass http://chat_bi_backend/images/;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }
}
EOF

          echo "项目 Nginx 参考配置已生成：$APP_HOME/chat-bi-nginx.conf"
          cat "$APP_HOME/chat-bi-nginx.conf"

          if [ "$(id -u)" -eq 0 ]; then
            SUDO=""
          elif command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
          else
            echo "需要 root 或 sudo 权限写入 $NGINX_CONF_PATH 并 reload Nginx。"
            exit 1
          fi
          $SUDO mkdir -p "$(dirname "$NGINX_CONF_PATH")"
          $SUDO cp "$APP_HOME/chat-bi-nginx.conf" "$NGINX_CONF_PATH"
          $SUDO nginx -t
          if command -v systemctl >/dev/null 2>&1; then
            $SUDO systemctl reload nginx
          else
            $SUDO nginx -s reload
          fi
        '''
      }
    }

    stage('安装并重启 systemd 服务') {
      steps {
        sh '''
          set -eux
          set +x
          set -a
          . "$INSTALL_CONF_FILE"
          set +a
          : "${ZHISHU_API_PORTS:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_API_PORTS}"
          : "${ZHISHU_WORKER_IDS:?请在 $INSTALL_CONF_FILE 中配置 ZHISHU_WORKER_IDS}"
          set -x
          api_ports="$ZHISHU_API_PORTS"
          worker_ids="$ZHISHU_WORKER_IDS"

          if [ "$(id -u)" -eq 0 ]; then
            SUDO=""
          elif command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
          else
            echo "需要 root 或 sudo 权限安装 systemd 服务。"
            exit 1
          fi

          cat > "$APP_HOME/chat-bi-systemd.env" <<EOF
APP_HOME=$APP_HOME
IMAGE=$IMAGE
RUNTIME_ENV_FILE=$RUNTIME_ENV_FILE
EOF
          chmod 600 "$APP_HOME/chat-bi-systemd.env"

          cat > "$APP_HOME/chat-bi-api@.service" <<'EOF'
[Unit]
Description=Chat BI API replica on port %i
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
EnvironmentFile=/home/chat-bi/chat-bi-systemd.env
ExecStartPre=-/usr/bin/docker rm -f chat-bi-api-%i
ExecStart=/usr/bin/docker run --rm --name chat-bi-api-%i --env-file ${RUNTIME_ENV_FILE} -e APP_ROLE=api -e API_PORT=%i -e AUTO_MIGRATE_ON_STARTUP=false -p 127.0.0.1:%i:8000 -v ${APP_HOME}/data/sqlbot/excel:/opt/sqlbot/data/excel -v ${APP_HOME}/data/sqlbot/file:/opt/sqlbot/data/file -v ${APP_HOME}/data/sqlbot/images:/opt/sqlbot/images -v ${APP_HOME}/data/sqlbot/logs:/opt/sqlbot/app/logs ${IMAGE}
ExecStop=/usr/bin/docker stop chat-bi-api-%i
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

          cat > "$APP_HOME/chat-bi-worker@.service" <<'EOF'
[Unit]
Description=Chat BI Task Worker %i
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
EnvironmentFile=/home/chat-bi/chat-bi-systemd.env
ExecStartPre=-/usr/bin/docker rm -f chat-bi-worker-%i
ExecStart=/usr/bin/docker run --rm --name chat-bi-worker-%i --env-file ${RUNTIME_ENV_FILE} -e APP_ROLE=worker -e WORKER_INSTANCE=%i -e AUTO_MIGRATE_ON_STARTUP=false -v ${APP_HOME}/data/sqlbot/excel:/opt/sqlbot/data/excel -v ${APP_HOME}/data/sqlbot/file:/opt/sqlbot/data/file -v ${APP_HOME}/data/sqlbot/images:/opt/sqlbot/images -v ${APP_HOME}/data/sqlbot/logs:/opt/sqlbot/app/logs ${IMAGE}
ExecStop=/usr/bin/docker stop chat-bi-worker-%i
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

          $SUDO cp "$APP_HOME/chat-bi-api@.service" /etc/systemd/system/chat-bi-api@.service
          $SUDO cp "$APP_HOME/chat-bi-worker@.service" /etc/systemd/system/chat-bi-worker@.service
          $SUDO rm -f /etc/systemd/system/chat-bi-mcp.service
          $SUDO systemctl daemon-reload

          echo "执行数据库迁移..."
          docker rm -f chat-bi-migrate >/dev/null 2>&1 || true
          docker run --rm \
            --name chat-bi-migrate \
            --env-file "$RUNTIME_ENV_FILE" \
            -e APP_ROLE=migrate \
            -e AUTO_MIGRATE_ON_STARTUP=false \
            -v "$APP_HOME/data/sqlbot/excel:/opt/sqlbot/data/excel" \
            -v "$APP_HOME/data/sqlbot/file:/opt/sqlbot/data/file" \
            -v "$APP_HOME/data/sqlbot/images:/opt/sqlbot/images" \
            -v "$APP_HOME/data/sqlbot/logs:/opt/sqlbot/app/logs" \
            "$IMAGE"

          echo "停止旧单容器实例和旧 systemd 实例..."
          docker rm -f "$CONTAINER_NAME" "${CONTAINER_NAME}-previous" >/dev/null 2>&1 || true
          $SUDO systemctl stop "chat-bi-mcp.service" >/dev/null 2>&1 || true
          docker rm -f chat-bi-mcp >/dev/null 2>&1 || true
          for api_port in $api_ports; do
            $SUDO systemctl stop "chat-bi-api@${api_port}.service" >/dev/null 2>&1 || true
          done
          for worker_id in $worker_ids; do
            $SUDO systemctl stop "chat-bi-worker@${worker_id}.service" >/dev/null 2>&1 || true
          done

          echo "启动 API 副本和 worker..."
          for api_port in $api_ports; do
            $SUDO systemctl enable "chat-bi-api@${api_port}.service"
            $SUDO systemctl restart "chat-bi-api@${api_port}.service"
          done
          for worker_id in $worker_ids; do
            $SUDO systemctl enable "chat-bi-worker@${worker_id}.service"
            $SUDO systemctl restart "chat-bi-worker@${worker_id}.service"
          done

          sleep 15
          for api_port in $api_ports; do
            $SUDO systemctl is-active --quiet "chat-bi-api@${api_port}.service"
          done
          for worker_id in $worker_ids; do
            $SUDO systemctl is-active --quiet "chat-bi-worker@${worker_id}.service"
          done

          docker ps --filter "name=^/chat-bi-"
        '''
      }
    }

    stage('发布前端到 Nginx') {
      steps {
        sh '''
          set -eux
          tmp_container="$(docker create "$IMAGE")"
          nginx_parent="$(dirname "$NGINX_ROOT")"
          nginx_tmp="${nginx_parent}/html.new.$$"
          nginx_backup="${nginx_parent}/html.prev.$$"
          trap 'docker rm -f "$tmp_container" >/dev/null 2>&1 || true; rm -rf "$nginx_tmp" "$nginx_backup"' EXIT

          case "$NGINX_ROOT" in
            "$APP_HOME"/nginx/html|"$APP_HOME"/nginx/html/*)
              ;;
            *)
              echo "NGINX_ROOT 路径异常：$NGINX_ROOT"
              exit 1
              ;;
          esac

          rm -rf "$nginx_tmp" "$nginx_backup"
          mkdir -p "$nginx_tmp"
          docker cp "$tmp_container:/opt/sqlbot/frontend/dist/." "$nginx_tmp"
          test -f "$nginx_tmp/index.html"

          if [ -d "$NGINX_ROOT" ]; then
            mv "$NGINX_ROOT" "$nginx_backup"
          fi
          if ! mv "$nginx_tmp" "$NGINX_ROOT"; then
            if [ -d "$nginx_backup" ]; then
              mv "$nginx_backup" "$NGINX_ROOT"
            fi
            exit 1
          fi
          rm -rf "$nginx_backup"

          chmod o+rx "$APP_HOME" "$APP_HOME/nginx" "$NGINX_ROOT" || true
          find "$NGINX_ROOT" -type d -exec chmod o+rx {} + || true
          find "$NGINX_ROOT" -type f -exec chmod o+r {} + || true
          if command -v chcon >/dev/null 2>&1; then
            chcon -R -t httpd_sys_content_t "$NGINX_ROOT" || true
          fi
          find "$NGINX_ROOT" -maxdepth 2 -type f | head
        '''
      }
    }

    stage('清理旧构建产物') {
      steps {
        sh '''
          set -eu
          IMAGE_KEEP_COUNT=2
          TAR_KEEP_COUNT=1
          RUNNING_IMAGE_IDS="$(docker ps --filter 'name=^/chat-bi-(api|worker)-' --format '{{.ID}}' \
            | xargs -r docker inspect --format='{{.Image}}' 2>/dev/null || true)"

          docker images "$IMAGE_REPOSITORY" --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}' \
            | sort -k3,4r \
            | awk -v keep="$IMAGE_KEEP_COUNT" -v running_ids="$RUNNING_IMAGE_IDS" '
                NR <= keep {
                  print "保留镜像：" $1
                  next
                }
                running_ids != "" && index(running_ids, $2) > 0 {
                  print "跳过运行中镜像：" $1
                  next
                }
                {
                  print $1
                }
              ' \
            | while IFS= read -r image; do
                case "$image" in
                  保留镜像：*|跳过运行中镜像：*)
                    echo "$image"
                    ;;
                  "")
                    ;;
                  *)
                    echo "删除旧镜像：$image"
                    docker rmi "$image" || true
                    ;;
                esac
              done

          echo "当前保留的 $IMAGE_REPOSITORY 镜像："
          docker images "$IMAGE_REPOSITORY"

          echo "清理退出容器，避免失败构建残留占用磁盘："
          docker container prune -f || true

          if [ "${CLEAN_DANGLING_IMAGES:-false}" = "true" ]; then
            echo "按参数清理悬空镜像。注意：这可能降低下一次 Docker 构建缓存命中率。"
            docker image prune -f || true
          else
            echo "跳过悬空镜像清理，以保留 Docker 构建缓存。磁盘紧张时可手动打开 CLEAN_DANGLING_IMAGES。"
          fi

          echo "清理旧镜像归档文件，只保留最近 $TAR_KEEP_COUNT 个："
          find "$APP_HOME" -maxdepth 1 -name 'chat-bi-*.tar' -type f -printf '%T@ %p\n' \
            | sort -nr \
            | awk -v keep="$TAR_KEEP_COUNT" 'NR > keep { print substr($0, index($0, " ") + 1) }' \
            | while IFS= read -r tar_file; do
                [ -n "$tar_file" ] || continue
                echo "删除旧镜像归档：$tar_file"
                rm -f "$tar_file"
              done

          echo "Docker 磁盘使用情况："
          docker system df
        '''
      }
    }
  }

  post {
    success {
      echo "发布完成：${env.IMAGE}，镜像未导出 tar"
    }
    failure {
      sh '''
        set +e
        echo "Docker 容器最近 300 行日志："
        docker ps -a --filter 'name=^/chat-bi-(api|worker)-' --format '{{.Names}}' \
          | while IFS= read -r container; do
              [ -n "$container" ] || continue
              echo "===== container:$container ====="
              docker logs --tail=300 "$container" || true
            done
        if docker ps -a --format '{{.Names}}' | grep -Fx chat-bi-migrate >/dev/null; then
          echo "===== container:chat-bi-migrate ====="
          docker logs --tail=300 chat-bi-migrate || true
        fi
        echo "应用日志目录最近 300 行日志："
        for log_file in "$APP_HOME"/data/sqlbot/logs/*.log; do
          if [ -f "$log_file" ]; then
            echo "===== $log_file ====="
            tail -n 300 "$log_file"
          fi
        done
        exit 0
      '''
    }
  }
}
