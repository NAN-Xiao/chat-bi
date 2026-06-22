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
            cat > "$INSTALL_CONF_FILE" <<EOF
ZHISHU_BASE=/home/chat-bi
ZHISHU_WEB_PORT=8000
ZHISHU_MCP_PORT=8001
ZHISHU_EXTERNAL_DB=true
ZHISHU_DB_HOST=10.1.5.193
ZHISHU_DB_PORT=5432
ZHISHU_DB_DB=zhishu_bi
ZHISHU_DB_USER=root
ZHISHU_DB_PASSWORD=Password123@pg
ZHISHU_DEFAULT_PWD=elex@123
ZHISHU_SECRET_KEY=jenkins-chat-bi-secret-change-me
ZHISHU_CORS_ORIGINS=http://${FRONTEND_HOST}
ZHISHU_LOG_LEVEL=INFO
ZHISHU_CACHE_TYPE=memory
ZHISHU_REDIS_HOST=127.0.0.1
ZHISHU_REDIS_PORT=6379
ZHISHU_REDIS_DB=0
ZHISHU_REDIS_USERNAME=
ZHISHU_REDIS_PASSWORD=
ZHISHU_REDIS_SSL=false
ZHISHU_REDIS_KEY_PREFIX=zhishu
ZHISHU_TASK_QUEUE_NAME=default
ZHISHU_TASK_QUEUE_RESULT_TTL_SECONDS=86400
ZHISHU_TASK_QUEUE_POLL_TIMEOUT_SECONDS=5
ZHISHU_TASK_QUEUE_MAX_ATTEMPTS=1
ZHISHU_EMBEDDING_MODEL=text-embedding-v4
ZHISHU_EMBEDDING_API_BASE_URL=
ZHISHU_EMBEDDING_API_KEY=
ZHISHU_MCP_ENABLED=false
ZHISHU_SERVER_IMAGE_HOST=http://${FRONTEND_HOST}/images/
ZHISHU_ACCESS_TOKEN_EXPIRE_MINUTES=11520
ZHISHU_CONTEXT_PATH=
EOF
            chmod 600 "$INSTALL_CONF_FILE"
            echo "已生成安装风格配置模板：$INSTALL_CONF_FILE。生产发布前请确认数据库名、账号密码和密钥。"
          fi

          set +x
          set -a
          . "$INSTALL_CONF_FILE"
          set +a
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
            echo "LOG_DIR=/opt/sqlbot/app/logs"
            echo "LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"
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

    stage('生成 Nginx 参考配置') {
      steps {
        sh '''
          set -eux
          set +x
          set -a
          . "$INSTALL_CONF_FILE"
          set +a
          set -x
          web_port="${ZHISHU_WEB_PORT:-$WEB_PORT}"
          mcp_port="${ZHISHU_MCP_PORT:-$MCP_PORT}"
          DOLLAR='$'
          cat > "$APP_HOME/chat-bi-nginx.conf" <<EOF
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
        proxy_pass http://127.0.0.1:${web_port}/api/v1/;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location = /openapi.json {
        proxy_pass http://127.0.0.1:${web_port}/openapi.json;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /docs {
        proxy_pass http://127.0.0.1:${web_port}/docs;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /images/ {
        proxy_pass http://127.0.0.1:${mcp_port}/images/;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /mcp {
        proxy_pass http://127.0.0.1:${mcp_port};
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }
}
EOF

          echo "项目 Nginx 参考配置已生成：$APP_HOME/chat-bi-nginx.conf"
          cat "$APP_HOME/chat-bi-nginx.conf"

          echo "Jenkins 运行在容器中时，$NGINX_CONF_PATH 可能是容器内路径。"
          echo "宿主机 Nginx 配置请由 root 预先放到宿主机 $NGINX_CONF_PATH。"
          echo "本流水线不写入宿主机 Nginx 配置，只生成参考配置供人工比对。"
          if [ -r "$NGINX_CONF_PATH" ]; then
            echo "检测到当前执行环境可读取 $NGINX_CONF_PATH，开始和参考配置比对："
            diff -u "$APP_HOME/chat-bi-nginx.conf" "$NGINX_CONF_PATH" || true
          else
            echo "当前执行环境无法读取 $NGINX_CONF_PATH，跳过自动比对。"
          fi
        '''
      }
    }

    stage('启动镜像') {
      steps {
        sh '''
          set -eux
          set +x
          set -a
          . "$INSTALL_CONF_FILE"
          set +a
          set -x
          web_port="${ZHISHU_WEB_PORT:-$WEB_PORT}"
          mcp_port="${ZHISHU_MCP_PORT:-$MCP_PORT}"
          backup_container="${CONTAINER_NAME}-previous"
          docker rm -f "$backup_container" >/dev/null 2>&1 || true

          restore_previous() {
            status="$1"
            echo "新容器启动失败，准备恢复旧容器。"
            docker logs --tail=200 "$CONTAINER_NAME" || true
            docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
            if docker ps -a --format '{{.Names}}' | grep -Fx "$backup_container" >/dev/null; then
              docker rename "$backup_container" "$CONTAINER_NAME" || true
              docker start "$CONTAINER_NAME" || true
            fi
            exit "$status"
          }

          if docker ps -a --format '{{.Names}}' | grep -Fx "$CONTAINER_NAME" >/dev/null; then
            docker rename "$CONTAINER_NAME" "$backup_container"
            docker stop "$backup_container" >/dev/null 2>&1 || true
          fi

          if ! docker run -d \
            --name "$CONTAINER_NAME" \
            --restart unless-stopped \
            -p "${web_port}:8000" \
            -p "${mcp_port}:8001" \
            -v "$APP_HOME/data/sqlbot/excel:/opt/sqlbot/data/excel" \
            -v "$APP_HOME/data/sqlbot/file:/opt/sqlbot/data/file" \
            -v "$APP_HOME/data/sqlbot/images:/opt/sqlbot/images" \
            -v "$APP_HOME/data/sqlbot/logs:/opt/sqlbot/app/logs" \
            -v "$APP_HOME/data/postgresql:/var/lib/postgresql/data" \
            --env-file "$RUNTIME_ENV_FILE" \
            "$IMAGE"; then
            restore_previous 1
          fi

          sleep 15
          if ! container_status="$(docker inspect --format='{{.State.Status}}' "$CONTAINER_NAME")"; then
            restore_previous 1
          fi
          if [ "$container_status" != "running" ]; then
            restore_previous 1
          fi
          docker ps --filter "name=^/${CONTAINER_NAME}$"
          docker port "$CONTAINER_NAME"

          docker rm -f "$backup_container" >/dev/null 2>&1 || true
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
          RUNNING_IMAGE_ID="$(docker inspect --format='{{.Image}}' "$CONTAINER_NAME" 2>/dev/null || true)"

          docker images "$IMAGE_REPOSITORY" --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}' \
            | sort -k3,4r \
            | awk -v keep="$IMAGE_KEEP_COUNT" -v running_id="$RUNNING_IMAGE_ID" '
                NR <= keep {
                  print "保留镜像：" $1
                  next
                }
                running_id != "" && index(running_id, $2) > 0 {
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
        if docker ps -a --format '{{.Names}}' | grep -Fx "$CONTAINER_NAME" >/dev/null; then
          docker logs --tail=300 "$CONTAINER_NAME"
        else
          echo "容器 $CONTAINER_NAME 不存在，跳过容器日志收集。"
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
