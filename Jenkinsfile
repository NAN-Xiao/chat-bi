pipeline {
  agent any

  options {
    timestamps()
    skipDefaultCheckout(true)
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    string(name: 'BRANCH_NAME', defaultValue: 'release_ha', description: 'Git 分支')
    string(name: 'IMAGE_TAG', defaultValue: '', description: '镜像标签，留空时使用 BUILD_NUMBER-git短哈希')
    booleanParam(name: 'CLEAN_OLD_IMAGES', defaultValue: false, description: '是否清理旧版本镜像。默认关闭以缩短发布耗时')
  }

  environment {
    DOCKER_BUILDKIT = '1'
    BUILDKIT_PROGRESS = 'plain'
    GIT_URL = 'https://github.com/NAN-Xiao/chat-bi.git'
    APP_HOME = '/home/chat-bi'
    CONTAINER_NAME = 'chat-bi'
    IMAGE_REPOSITORY = 'shuzhi'
    SHUZHI_BUILD_BASE_IMAGE = 'shuzhi-base:latest'
    SHUZHI_RUNTIME_IMAGE = 'shuzhi-python-pg:latest'
    FRONTEND_HOST = '10.1.5.28'
    NGINX_PORT = '80'
    NGINX_ROOT = '/home/chat-bi/nginx/html'
    NGINX_CONF_PATH = '/etc/nginx/conf.d/chat-bi.conf'
    INSTALL_CONF_FILE = 'installer/install.conf'
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
          env.CLEAN_OLD_IMAGES = params.CLEAN_OLD_IMAGES.toString()
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
            docker buildx version || echo "docker buildx 不可用，将使用 DOCKER_BUILDKIT=1 docker build。"
          fi
          echo "Python 依赖类型：${PYTHON_DEPENDENCY_EXTRA:-cpu}"
          echo "是否清理旧版本镜像：${CLEAN_OLD_IMAGES:-false}"
          echo "悬空镜像将在构建完成后自动清理。"
          if ! mkdir -p "$APP_HOME" "$APP_HOME/data/shuzhi/excel" "$APP_HOME/data/shuzhi/file" "$APP_HOME/data/shuzhi/images" "$APP_HOME/data/shuzhi/logs" "$APP_HOME/data/postgresql" "$NGINX_ROOT"; then
            echo "Jenkins 用户没有 $APP_HOME 写入权限，请先在 Linux 服务器执行：sudo mkdir -p $APP_HOME && sudo chown -R $(id -u):$(id -g) $APP_HOME"
            exit 1
          fi
          test -w "$APP_HOME" || { echo "Jenkins 用户没有 $APP_HOME 写入权限，请先在 Linux 服务器执行：sudo mkdir -p $APP_HOME && sudo chown -R $(id -u):$(id -g) $APP_HOME"; exit 1; }
          if [ ! -f "$INSTALL_CONF_FILE" ]; then
            echo "缺少仓库配置文件：$INSTALL_CONF_FILE"
            echo "请先在仓库 installer/install.conf 中维护部署配置。"
            exit 1
          fi

          set +x
          install_conf_runtime="$(mktemp)"
          tr -d '\r' < "$INSTALL_CONF_FILE" > "$install_conf_runtime"
          set -a
          . "$install_conf_runtime"
          set +a
          rm -f "$install_conf_runtime"
          : "${SHUZHI_API_PORTS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_API_PORTS}"
          : "${SHUZHI_WORKER_IDS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_WORKER_IDS}"
          : "${SHUZHI_CACHE_TYPE:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_CACHE_TYPE}"
          : "${SHUZHI_REDIS_HOST:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_REDIS_HOST}"
          : "${SHUZHI_REDIS_PORT:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_REDIS_PORT}"
          : "${SHUZHI_DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS}"
          : "${SHUZHI_DASHBOARD_SQL_PREVIEW_DATASOURCE_CONCURRENCY:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_DASHBOARD_SQL_PREVIEW_DATASOURCE_CONCURRENCY}"
          : "${SHUZHI_DASHBOARD_SQL_PREVIEW_WAIT_TIMEOUT_SECONDS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_DASHBOARD_SQL_PREVIEW_WAIT_TIMEOUT_SECONDS}"
          : "${SHUZHI_DASHBOARD_SQL_PREVIEW_DEDUPE_WAIT_TIMEOUT_SECONDS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_DASHBOARD_SQL_PREVIEW_DEDUPE_WAIT_TIMEOUT_SECONDS}"
          : "${SHUZHI_TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS}"
          : "${SHUZHI_TASK_QUEUE_REQUEUE_INTERVAL_SECONDS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_TASK_QUEUE_REQUEUE_INTERVAL_SECONDS}"
          {
            echo "PROJECT_NAME=星通数智"
            echo "POSTGRES_SERVER=${SHUZHI_DB_HOST}"
            echo "POSTGRES_PORT=${SHUZHI_DB_PORT}"
            echo "POSTGRES_DB=${SHUZHI_DB_DB}"
            echo "POSTGRES_USER=${SHUZHI_DB_USER}"
            echo "POSTGRES_PASSWORD=${SHUZHI_DB_PASSWORD}"
            echo "SECRET_KEY=${SHUZHI_SECRET_KEY}"
            echo "DEFAULT_PWD=${SHUZHI_DEFAULT_PWD}"
            echo "FRONTEND_HOST=http://${FRONTEND_HOST}"
            echo "BACKEND_CORS_ORIGINS=${SHUZHI_CORS_ORIGINS}"
            echo "SERVER_IMAGE_HOST=${SHUZHI_SERVER_IMAGE_HOST}"
            echo "LOG_LEVEL=${SHUZHI_LOG_LEVEL}"
            echo "SQL_DEBUG=false"
            echo "BASE_DIR=/opt/shuzhi"
            echo "UPLOAD_DIR=/opt/shuzhi/data/file"
            echo "EXCEL_PATH=/opt/shuzhi/data/excel"
            echo "MCP_IMAGE_PATH=/opt/shuzhi/images"
            echo "LOG_DIR=/opt/shuzhi/app/logs"
            echo "LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"
            echo "AUTO_RUN_MIGRATIONS=false"
            echo "CACHE_TYPE=${SHUZHI_CACHE_TYPE}"
            echo "REDIS_HOST=${SHUZHI_REDIS_HOST}"
            echo "REDIS_PORT=${SHUZHI_REDIS_PORT}"
            echo "REDIS_DB=${SHUZHI_REDIS_DB}"
            echo "REDIS_USERNAME=${SHUZHI_REDIS_USERNAME}"
            echo "REDIS_PASSWORD=${SHUZHI_REDIS_PASSWORD}"
            echo "REDIS_SSL=${SHUZHI_REDIS_SSL}"
            echo "REDIS_KEY_PREFIX=${SHUZHI_REDIS_KEY_PREFIX}"
            echo "DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS=${SHUZHI_DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS}"
            echo "DASHBOARD_SQL_PREVIEW_DATASOURCE_CONCURRENCY=${SHUZHI_DASHBOARD_SQL_PREVIEW_DATASOURCE_CONCURRENCY}"
            echo "DASHBOARD_SQL_PREVIEW_WAIT_TIMEOUT_SECONDS=${SHUZHI_DASHBOARD_SQL_PREVIEW_WAIT_TIMEOUT_SECONDS}"
            echo "DASHBOARD_SQL_PREVIEW_DEDUPE_WAIT_TIMEOUT_SECONDS=${SHUZHI_DASHBOARD_SQL_PREVIEW_DEDUPE_WAIT_TIMEOUT_SECONDS}"
            echo "TASK_QUEUE_NAME=${SHUZHI_TASK_QUEUE_NAME}"
            echo "TASK_QUEUE_RESULT_TTL_SECONDS=${SHUZHI_TASK_QUEUE_RESULT_TTL_SECONDS}"
            echo "TASK_QUEUE_POLL_TIMEOUT_SECONDS=${SHUZHI_TASK_QUEUE_POLL_TIMEOUT_SECONDS}"
            echo "TASK_QUEUE_MAX_ATTEMPTS=${SHUZHI_TASK_QUEUE_MAX_ATTEMPTS}"
            echo "TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS=${SHUZHI_TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS}"
            echo "TASK_QUEUE_REQUEUE_INTERVAL_SECONDS=${SHUZHI_TASK_QUEUE_REQUEUE_INTERVAL_SECONDS}"
            echo "EMBEDDING_MODEL=${SHUZHI_EMBEDDING_MODEL}"
            echo "EMBEDDING_API_BASE_URL=${SHUZHI_EMBEDDING_API_BASE_URL}"
            echo "EMBEDDING_API_KEY=${SHUZHI_EMBEDDING_API_KEY}"
            echo "MCP_ENABLED=${SHUZHI_MCP_ENABLED}"
            echo "ACCESS_TOKEN_EXPIRE_MINUTES=${SHUZHI_ACCESS_TOKEN_EXPIRE_MINUTES}"
            echo "CONTEXT_PATH=${SHUZHI_CONTEXT_PATH}"
          } > "$RUNTIME_ENV_FILE"
          chmod 600 "$RUNTIME_ENV_FILE"
          set -x
          grep -E '^(POSTGRES_SERVER|POSTGRES_PORT|POSTGRES_DB|POSTGRES_USER|FRONTEND_HOST|BACKEND_CORS_ORIGINS|CACHE_TYPE)=' "$RUNTIME_ENV_FILE" || true
        '''
      }
    }

    stage('构建基础镜像') {
      steps {
        sh '''
          set -eux
          docker build \
            -f Dockerfile-base \
            --tag "$SHUZHI_BUILD_BASE_IMAGE" \
            --tag "$SHUZHI_RUNTIME_IMAGE" \
            .
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
            --build-arg SHUZHI_BUILD_BASE_IMAGE="$SHUZHI_BUILD_BASE_IMAGE" \
            --build-arg SHUZHI_RUNTIME_IMAGE="$SHUZHI_RUNTIME_IMAGE" \
            --build-arg VITE_API_BASE_URL="$FRONTEND_API_BASE_URL" \
            --build-arg PYTHON_DEPENDENCY_EXTRA="$PYTHON_DEPENDENCY_EXTRA" \
            .
        '''
      }
    }

    stage('校验前端构建产物') {
      steps {
        sh '''
          set -eux
          tmp_container="$(docker create "$IMAGE")"
          dist_tmp="$(mktemp -d)"
          trap 'docker rm -f "$tmp_container" >/dev/null 2>&1 || true; rm -rf "$dist_tmp"' EXIT

          docker cp "$tmp_container:/opt/shuzhi/frontend/dist/." "$dist_tmp"
          test -f "$dist_tmp/index.html"

          frontend_js="$(grep -o 'assets/index-[^"]*\\.js' "$dist_tmp/index.html" | head -n 1)"
          test -n "$frontend_js"
          test -f "$dist_tmp/$frontend_js"

          echo "校验镜像内前端入口资源：$frontend_js"
          for marker in 'chat.currentChat.' '/chat/question/task' 'record_id' 'task_id'; do
            if ! grep -Fq "$marker" "$dist_tmp/$frontend_js"; then
              echo "前端构建产物缺少关键标记：$marker"
              exit 1
            fi
          done
          echo "镜像内前端构建产物校验通过。"
        '''
      }
    }

    stage('生成 Nginx 参考配置') {
      steps {
        sh '''
          set -eux
          set +x
          install_conf_runtime="$(mktemp)"
          tr -d '\r' < "$INSTALL_CONF_FILE" > "$install_conf_runtime"
          set -a
          . "$install_conf_runtime"
          set +a
          rm -f "$install_conf_runtime"
          : "${SHUZHI_API_PORTS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_API_PORTS}"
          set -x
          DOLLAR='$'
          api_ports="$SHUZHI_API_PORTS"
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

          echo "跳过 Nginx 安装和 reload：当前 Jenkins 运行环境不负责管理宿主机 Nginx。"
          echo "如需更新宿主机配置，请人工比对并应用：$APP_HOME/chat-bi-nginx.conf -> $NGINX_CONF_PATH"
        '''
      }
    }

    stage('重启 Docker 服务') {
      steps {
        sh '''
          set -eux
          set +x
          install_conf_runtime="$(mktemp)"
          tr -d '\r' < "$INSTALL_CONF_FILE" > "$install_conf_runtime"
          set -a
          . "$install_conf_runtime"
          set +a
          rm -f "$install_conf_runtime"
          : "${SHUZHI_API_PORTS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_API_PORTS}"
          : "${SHUZHI_WORKER_IDS:?请在 $INSTALL_CONF_FILE 中配置 SHUZHI_WORKER_IDS}"
          set -x
          api_ports="$SHUZHI_API_PORTS"
          worker_ids="$SHUZHI_WORKER_IDS"

          cat > "$APP_HOME/chat-bi-deploy.env" <<EOF
APP_HOME=$APP_HOME
IMAGE=$IMAGE
RUNTIME_ENV_FILE=$RUNTIME_ENV_FILE
EOF
          chmod 600 "$APP_HOME/chat-bi-deploy.env"

          echo "停止旧应用容器..."
          docker rm -f "$CONTAINER_NAME" "${CONTAINER_NAME}-previous" >/dev/null 2>&1 || true
          for api_port in $api_ports; do
            docker rm -f "chat-bi-api-${api_port}" >/dev/null 2>&1 || true
          done
          for worker_id in $worker_ids; do
            docker rm -f "chat-bi-worker-${worker_id}" >/dev/null 2>&1 || true
          done

          echo "启动 API 副本..."
          for api_port in $api_ports; do
            docker run -d \
              --name "chat-bi-api-${api_port}" \
              --restart unless-stopped \
              --env-file "$RUNTIME_ENV_FILE" \
              -e APP_ROLE=api \
              -e API_PORT="$api_port" \
              -p "127.0.0.1:${api_port}:${api_port}" \
              -v "$APP_HOME/data/shuzhi/excel:/opt/shuzhi/data/excel" \
              -v "$APP_HOME/data/shuzhi/file:/opt/shuzhi/data/file" \
              -v "$APP_HOME/data/shuzhi/images:/opt/shuzhi/images" \
              -v "$APP_HOME/data/shuzhi/logs:/opt/shuzhi/app/logs" \
              "$IMAGE"
          done

          echo "启动 Worker 副本..."
          for worker_id in $worker_ids; do
            docker run -d \
              --name "chat-bi-worker-${worker_id}" \
              --restart unless-stopped \
              --env-file "$RUNTIME_ENV_FILE" \
              -e APP_ROLE=worker \
              -e WORKER_ID="$worker_id" \
              -v "$APP_HOME/data/shuzhi/excel:/opt/shuzhi/data/excel" \
              -v "$APP_HOME/data/shuzhi/file:/opt/shuzhi/data/file" \
              -v "$APP_HOME/data/shuzhi/images:/opt/shuzhi/images" \
              -v "$APP_HOME/data/shuzhi/logs:/opt/shuzhi/app/logs" \
              "$IMAGE"
          done

          deadline=$(( $(date +%s) + 45 ))
          while true; do
            all_ok=1
            for api_port in $api_ports; do
              docker ps --format '{{.Names}}' | grep -Fx "chat-bi-api-${api_port}" >/dev/null || all_ok=0
              docker run --rm --network host busybox:1.36 sh -c "nc -z 127.0.0.1 ${api_port}" >/dev/null 2>&1 || all_ok=0
            done
            for worker_id in $worker_ids; do
              docker ps --format '{{.Names}}' | grep -Fx "chat-bi-worker-${worker_id}" >/dev/null || all_ok=0
            done
            if [ "$all_ok" -eq 1 ]; then
              echo "Docker API 和 worker 容器已就绪。"
              break
            fi
            if [ "$(date +%s)" -ge "$deadline" ]; then
              echo "等待 Docker API 或 worker 容器就绪超时。"
              docker ps -a --filter 'name=^/chat-bi-(api|worker)-'
              for container in $(docker ps -a --filter 'name=^/chat-bi-(api|worker)-' --format '{{.Names}}'); do
                echo "===== container:$container ====="
                docker logs --tail=200 "$container" || true
              done
              exit 1
            fi
            sleep 1
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
          docker cp "$tmp_container:/opt/shuzhi/frontend/dist/." "$nginx_tmp"
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

          frontend_js="$(grep -o 'assets/index-[^"]*\\.js' "$NGINX_ROOT/index.html" | head -n 1)"
          test -n "$frontend_js"
          test -f "$NGINX_ROOT/$frontend_js"
          echo "校验 Nginx 静态目录前端入口资源：$frontend_js"
          for marker in 'chat.currentChat.' '/chat/question/task' 'record_id' 'task_id'; do
            if ! grep -Fq "$marker" "$NGINX_ROOT/$frontend_js"; then
              echo "Nginx 静态目录前端产物缺少关键标记：$marker"
              exit 1
            fi
          done

          if command -v curl >/dev/null 2>&1; then
            public_base="http://127.0.0.1:${NGINX_PORT:-80}"
            if [ "${NGINX_PORT:-80}" = "80" ]; then
              public_base="http://127.0.0.1"
            fi
            http_js_tmp="$(mktemp)"
            if curl -fsS "$public_base/$frontend_js" -o "$http_js_tmp"; then
              http_ok=1
              for marker in 'chat.currentChat.' '/chat/question/task' 'record_id' 'task_id'; do
                if ! grep -Fq "$marker" "$http_js_tmp"; then
                  echo "Nginx HTTP 返回的前端产物缺少关键标记：$marker"
                  http_ok=0
                fi
              done
              if [ "$http_ok" -eq 1 ]; then
                echo "Nginx HTTP 前端产物校验通过：$public_base/$frontend_js"
              else
                echo "Nginx HTTP 前端产物校验未通过，但静态目录文件级校验已通过，继续发布。"
              fi
            else
              echo "无法通过 Jenkins 执行环境访问 $public_base/$frontend_js，跳过 Nginx HTTP 返回内容校验。"
            fi
            rm -f "$http_js_tmp"
          else
            echo "未找到 curl，跳过 Nginx HTTP 返回内容校验。"
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

          if [ "${CLEAN_OLD_IMAGES:-false}" = "true" ]; then
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
          else
            echo "跳过旧版本镜像清理。磁盘紧张时可手动打开 CLEAN_OLD_IMAGES。"
          fi

          echo "当前保留的 $IMAGE_REPOSITORY 镜像："
          docker images "$IMAGE_REPOSITORY"

          echo "清理退出容器，避免失败构建残留占用磁盘："
          docker container prune -f || true

          echo "清理悬空镜像，减少无标签镜像占用："
          docker image prune -f || true

          if [ "${CLEAN_OLD_IMAGES:-false}" = "true" ]; then
            echo "清理旧镜像归档文件，只保留最近 $TAR_KEEP_COUNT 个："
            find "$APP_HOME" -maxdepth 1 -name 'chat-bi-*.tar' -type f -printf '%T@ %p\n' \
              | sort -nr \
              | awk -v keep="$TAR_KEEP_COUNT" 'NR > keep { print substr($0, index($0, " ") + 1) }' \
              | while IFS= read -r tar_file; do
                  [ -n "$tar_file" ] || continue
                  echo "删除旧镜像归档：$tar_file"
                  rm -f "$tar_file"
                done
          else
            echo "跳过旧镜像归档文件清理。"
          fi

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
        echo "应用日志目录最近 300 行日志："
        for log_file in "$APP_HOME"/data/shuzhi/logs/*.log; do
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
