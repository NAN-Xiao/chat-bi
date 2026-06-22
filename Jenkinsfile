pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    string(name: 'BRANCH_NAME', defaultValue: 'jenkins', description: 'Git 分支')
    string(name: 'IMAGE_TAG', defaultValue: '', description: '镜像标签，留空时使用 BUILD_NUMBER-git短哈希')
  }

  environment {
    DOCKER_BUILDKIT = '0'
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
          env.IMAGE_TAR = "${env.APP_HOME}/chat-bi-${env.EFFECTIVE_IMAGE_TAG}.tar"
          env.BUILD_AT = sh(script: "TZ=Asia/Shanghai date +'%Y-%m-%dT%H:%M'", returnStdout: true).trim()
          env.GITHUB_COMMIT = shortCommit
          env.FRONTEND_API_BASE_URL = "./api/v1"
        }
        sh '''
          set -eux
          command -v git
          command -v docker
          command -v curl
          docker version
          if ! mkdir -p "$APP_HOME" "$APP_HOME/data/sqlbot/excel" "$APP_HOME/data/sqlbot/file" "$APP_HOME/data/sqlbot/images" "$APP_HOME/data/sqlbot/logs" "$APP_HOME/data/postgresql" "$NGINX_ROOT"; then
            echo "Jenkins 用户没有 $APP_HOME 写入权限，请先在 Linux 服务器执行：sudo mkdir -p $APP_HOME && sudo chown -R $(id -u):$(id -g) $APP_HOME"
            exit 1
          fi
          test -w "$APP_HOME" || { echo "Jenkins 用户没有 $APP_HOME 写入权限，请先在 Linux 服务器执行：sudo mkdir -p $APP_HOME && sudo chown -R $(id -u):$(id -g) $APP_HOME"; exit 1; }
        '''
      }
    }

    stage('构建 Docker 镜像') {
      steps {
        sh '''
          set -eux
          docker build \
            --tag "$IMAGE" \
            --build-arg BUILD_AT="$BUILD_AT" \
            --build-arg GITHUB_COMMIT="$GITHUB_COMMIT" \
            --build-arg SQLBOT_BASE_IMAGE="$SQLBOT_BASE_IMAGE" \
            --build-arg SQLBOT_RUNTIME_IMAGE="$SQLBOT_RUNTIME_IMAGE" \
            --build-arg VITE_API_BASE_URL="$FRONTEND_API_BASE_URL" \
            .
        '''
      }
    }

    stage('发布前端到 Nginx') {
      steps {
        sh '''
          set -eux
          tmp_container="$(docker create "$IMAGE")"
          trap 'docker rm -f "$tmp_container" >/dev/null 2>&1 || true' EXIT

          rm -rf "$NGINX_ROOT"
          mkdir -p "$NGINX_ROOT"
          docker cp "$tmp_container:/opt/sqlbot/frontend/dist/." "$NGINX_ROOT"
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

    stage('检查宿主机 Nginx 配置') {
      steps {
        sh '''
          set -eux
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
        proxy_pass http://127.0.0.1:${WEB_PORT}/api/v1/;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location = /openapi.json {
        proxy_pass http://127.0.0.1:${WEB_PORT}/openapi.json;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /docs {
        proxy_pass http://127.0.0.1:${WEB_PORT}/docs;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /images/ {
        proxy_pass http://127.0.0.1:${MCP_PORT}/images/;
        proxy_set_header Host ${DOLLAR}host;
        proxy_set_header X-Real-IP ${DOLLAR}remote_addr;
        proxy_set_header X-Forwarded-For ${DOLLAR}proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto ${DOLLAR}scheme;
    }

    location /mcp {
        proxy_pass http://127.0.0.1:${MCP_PORT};
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
          echo "本流水线不再写入宿主机 Nginx 配置，最终通过 http://127.0.0.1:${NGINX_PORT}/ 做访问校验。"
        '''
      }
    }

    stage('保存镜像到 /home/chat-bi') {
      steps {
        sh '''
          set -eux
          docker save "$IMAGE" -o "$IMAGE_TAR"
          ls -lh "$IMAGE_TAR"
        '''
      }
    }

    stage('启动镜像') {
      steps {
        sh '''
          set -eux
          docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
          docker run -d \
            --name "$CONTAINER_NAME" \
            --restart unless-stopped \
            --privileged=true \
            -p "${WEB_PORT}:8000" \
            -p "${MCP_PORT}:8001" \
            -v "$APP_HOME/data/sqlbot/excel:/opt/sqlbot/data/excel" \
            -v "$APP_HOME/data/sqlbot/file:/opt/sqlbot/data/file" \
            -v "$APP_HOME/data/sqlbot/images:/opt/sqlbot/images" \
            -v "$APP_HOME/data/sqlbot/logs:/opt/sqlbot/app/logs" \
            -v "$APP_HOME/data/postgresql:/var/lib/postgresql/data" \
            -e SECRET_KEY="${SECRET_KEY:-jenkins-chat-bi-secret}" \
            -e FRONTEND_HOST="http://${FRONTEND_HOST}" \
            -e BACKEND_CORS_ORIGINS="http://${FRONTEND_HOST}" \
            -e LOG_DIR="/opt/sqlbot/app/logs" \
            -e LOG_FORMAT="%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s" \
            "$IMAGE"

          docker ps --filter "name=$CONTAINER_NAME"
        '''
      }
    }

    stage('清理旧镜像') {
      steps {
        sh '''
          set -eu
          KEEP_COUNT=3
          RUNNING_IMAGE_ID="$(docker inspect --format='{{.Image}}' "$CONTAINER_NAME" 2>/dev/null || true)"

          docker images "$IMAGE_REPOSITORY" --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}' \
            | sort -k3,4r \
            | awk -v keep="$KEEP_COUNT" -v running_id="$RUNNING_IMAGE_ID" '
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
        '''
      }
    }
  }

  post {
    success {
      echo "发布完成：${env.IMAGE}，镜像文件：${env.IMAGE_TAR}"
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
