# 单用户高可用 Jenkins 发布文档

本文档面向当前 `chat-bi` 仓库的单用户/单租户高可用发布方案。核心原则是：先不拆代码仓库、不拆服务代码，只把部署形态拆开，让同一套代码可以在多台应用服务器上运行。

目标演进顺序：

```text
第一阶段：不拆代码，只拆部署

用户浏览器
  -> Nginx
    -> 服务器 A
        API
        worker
    -> 服务器 B
        API
        worker

共享依赖：
  -> PostgreSQL: 10.1.5.193:5432
  -> Redis
  -> 共享文件目录或对象存储

第二阶段：整理启动脚本和生产配置

去掉单容器 start.sh 的强绑定
使用 systemd / supervisor 分别管理 API 和 worker
```

## 一、发布目标

第一阶段的目标是两台应用服务器高可用，而不是立即重构代码。

要解决的问题：

- 任意一台应用服务器异常时，另一台服务器仍可承接 API 请求。
- 任意一个 API 进程异常时，Nginx 可以将请求转发到存活节点。
- 任意一个 worker 异常时，Redis 队列中的任务可由另一台服务器上的 worker 消费或超时恢复。
- PostgreSQL 已外置到远程服务，避免应用服务器本地数据库成为发布耦合点。
- Jenkins 可以把同一份构建产物发布到服务器 A 和服务器 B。

暂不解决或需要单独增强的问题：

- 如果 Nginx 只有一台，它仍然是入口单点；后续可用 SLB、VIP 或双 Nginx 解决。
- 如果 Redis 只有一台，它仍然是队列和共享缓存单点；后续可升级为云 Redis、Redis Sentinel 或 Redis Cluster。
- 如果文件仍保存在某台应用服务器本地，两台服务器之间会出现文件不一致；第一阶段应至少使用共享目录，生产更推荐对象存储。
- Smart Q&A 生成当前主要在 API 进程内执行，API 进程宕机时，正在生成的回答不能自动转移到另一个 API 继续执行。

## 二、第一阶段目标架构

推荐部署形态：

```text
用户浏览器
  -> Nginx: 80/443
    -> 服务器 A: 10.1.5.201
        API: 127.0.0.1:8000 或 0.0.0.0:8000
        worker: zhishu-worker
        frontend/dist
    -> 服务器 B: 10.1.5.202
        API: 127.0.0.1:8000 或 0.0.0.0:8000
        worker: zhishu-worker
        frontend/dist

共享依赖：
  -> PostgreSQL: 10.1.5.193:5432
  -> Redis: 10.1.5.193:6379
  -> 共享文件目录: /opt/zhishu/data/file
  -> Excel 目录: /opt/zhishu/data/excel
  -> 图片目录: /opt/zhishu/images
  -> 日志目录: /opt/zhishu/logs
```

如果 Nginx 和应用部署在同一台机器上，可以把服务器 A 的 API 写成 `127.0.0.1:8000`。如果 Nginx 独立部署，则 upstream 必须写服务器 A/B 的内网 IP，例如 `10.1.5.201:8000`、`10.1.5.202:8000`。

代码入口：

```text
API 入口:
backend/main.py

worker 入口:
backend/scripts/task_worker.py

前端构建:
frontend/dist

Nginx 模板:
deploy/nginx/nginx.production.conf.template

systemd 模板:
deploy/systemd/zhishu-api@.service
deploy/systemd/zhishu-worker@.service
```

## 三、与当前 Jenkinsfile 的差异

当前 `Jenkinsfile` 更接近单容器发布流程：

```text
1. 构建 Docker 镜像
2. 停旧容器
3. 启动新容器
4. 从镜像中拷贝 frontend/dist 到宿主机 Nginx 目录
```

当前容器启动脚本 `start.sh` 会同时管理：

```text
PostgreSQL
g2-ssr
MCP app
FastAPI API
```

第一阶段可以先不重构 `start.sh`，但生产发布思路要从“启动一个大容器”转成“同一份代码发布到服务器 A/B，API 和 worker 分别运行”。第二阶段再正式去掉 `start.sh` 对多个角色的强绑定，改用 systemd 或 supervisor 管理 API / worker。

## 四、发布前置条件

### 1. 远程 PostgreSQL

当前默认远程 PostgreSQL：

```text
POSTGRES_SERVER=10.1.5.193
POSTGRES_PORT=5432
```

发布前在 Jenkins 节点、服务器 A、服务器 B 都要确认可达：

```bash
nc -vz 10.1.5.193 5432
```

或：

```bash
psql -h 10.1.5.193 -p 5432 -U <user> -d <db> -c 'select 1'
```

必须确认数据库名、用户名、密码与生产环境变量一致。

### 2. Redis

两台应用服务器必须连接同一个 Redis。Redis 同时承担：

- 多 API 共享缓存和状态。
- worker 任务队列。
- 任务去重、锁、执行结果缓存。

推荐配置：

```text
CACHE_TYPE=redis
REDIS_HOST=<redis 内网地址>
REDIS_PORT=6379
REDIS_PASSWORD=<strong-password>
TASK_QUEUE_MAX_ATTEMPTS=3
TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS=3600
```

如果 Redis 仍部署为单机，要接受 Redis 单点风险；如果要做到更完整的高可用，应升级为云 Redis、Redis Sentinel 或 Redis Cluster。

### 3. 文件目录

两台服务器都运行 API 和 worker 后，文件目录不能只存在某一台服务器本地。否则用户在服务器 A 上传的文件，后续请求打到服务器 B 时可能读不到。

第一阶段建议至少使用共享目录，例如 NFS、NAS、云盘挂载：

```bash
sudo mkdir -p /opt/zhishu/backend
sudo mkdir -p /opt/zhishu/frontend/dist
sudo mkdir -p /opt/zhishu/data/file
sudo mkdir -p /opt/zhishu/data/excel
sudo mkdir -p /opt/zhishu/images
sudo mkdir -p /opt/zhishu/logs
sudo mkdir -p /etc/zhishu
sudo chown -R zhishu:zhishu /opt/zhishu
```

生产更推荐把 `UPLOAD_DIR`、`EXCEL_PATH`、`MCP_IMAGE_PATH` 迁移到对象存储或专用共享存储。

### 4. 生产环境变量

服务器 A 和服务器 B 的生产环境变量必须保持一致，建议放在：

```text
/etc/zhishu/zhishu.env
```

关键配置：

```env
APP_ENV=production
PRODUCTION_CHECKS_ENABLED=true
PROJECT_NAME=星通智数

FRONTEND_HOST=https://bi.example.com
BACKEND_CORS_ORIGINS=https://bi.example.com
ENABLE_LOCAL_DEV_CORS=false

SECRET_KEY=<长期稳定的随机密钥>
SENSITIVE_CONFIG_ENCRYPTION_KEY=<长期稳定的敏感配置加密密钥>
DEFAULT_PWD=<强初始密码>

POSTGRES_SERVER=10.1.5.193
POSTGRES_PORT=5432
POSTGRES_DB=<生产系统库>
POSTGRES_USER=<生产用户>
POSTGRES_PASSWORD=<生产密码>

CACHE_TYPE=redis
REDIS_HOST=<redis 内网地址>
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=<Redis 密码>
REDIS_KEY_PREFIX=zhishu-prod
CACHE_REDIS_PREFIX=zhishu-prod-cache

TASK_QUEUE_NAME=default
TASK_QUEUE_MAX_ATTEMPTS=3
TASK_QUEUE_RESULT_TTL_SECONDS=86400
TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS=3600
TASK_QUEUE_REQUEUE_INTERVAL_SECONDS=60

BASE_DIR=/opt/zhishu
UPLOAD_DIR=/opt/zhishu/data/file
EXCEL_PATH=/opt/zhishu/data/excel
MCP_IMAGE_PATH=/opt/zhishu/images
LOG_DIR=/opt/zhishu/logs

MCP_ENABLED=false
ZHISHU_ALLOW_METADATA_QUERIES=false
SQL_DEBUG=false
LOG_LEVEL=INFO
```

注意：`SECRET_KEY` 和 `SENSITIVE_CONFIG_ENCRYPTION_KEY` 必须长期稳定保存。丢失或更换会影响登录 token 和已加密的数据源/模型配置。

## 五、第一阶段 Jenkins 发布流程

推荐 Jenkins pipeline 拆成以下阶段。

### 阶段 1：拉取代码

```bash
git clone <repo>
git checkout <branch>
```

### 阶段 2：构建前端

```bash
cd frontend
npm ci
npm run build
```

产物：

```text
frontend/dist
```

### 阶段 3：安装后端依赖

```bash
cd backend
uv sync --frozen --no-dev --extra cpu
```

如果生产服务器直接运行源码，需要将 `backend/`、`.venv/`、`alembic/`、`templates/` 等后端运行文件发布到两台服务器：

```text
服务器 A: /opt/zhishu/backend
服务器 B: /opt/zhishu/backend
```

### 阶段 4：发布文件到服务器 A/B

同一份构建产物发布到两台服务器。建议采用 `.new` 和 `.prev` 原子替换，便于回滚。

后端发布示例：

```bash
for host in zhishu-a zhishu-b; do
  ssh $host 'rm -rf /opt/zhishu/backend.new && mkdir -p /opt/zhishu/backend.new'
  rsync -a --exclude '.venv' --exclude '__pycache__' backend/ $host:/opt/zhishu/backend.new/
  rsync -a backend/.venv/ $host:/opt/zhishu/backend.new/.venv/
  ssh $host '
    if [ -d /opt/zhishu/backend ]; then
      rm -rf /opt/zhishu/backend.prev
      mv /opt/zhishu/backend /opt/zhishu/backend.prev
    fi
    mv /opt/zhishu/backend.new /opt/zhishu/backend
    chown -R zhishu:zhishu /opt/zhishu/backend
  '
done
```

前端发布示例：

```bash
for host in zhishu-a zhishu-b; do
  ssh $host 'rm -rf /opt/zhishu/frontend/dist.new && mkdir -p /opt/zhishu/frontend/dist.new'
  rsync -a frontend/dist/ $host:/opt/zhishu/frontend/dist.new/
  ssh $host '
    if [ -d /opt/zhishu/frontend/dist ]; then
      rm -rf /opt/zhishu/frontend/dist.prev
      mv /opt/zhishu/frontend/dist /opt/zhishu/frontend/dist.prev
    fi
    mv /opt/zhishu/frontend/dist.new /opt/zhishu/frontend/dist
    chown -R zhishu:zhishu /opt/zhishu/frontend
  '
done
```

### 阶段 5：生产配置检查

服务器 A/B 都要执行：

```bash
cd /opt/zhishu/backend
set -a
source /etc/zhishu/zhishu.env
set +a
APP_ENV=production python scripts/production_check.py
```

预期输出：

```text
Production settings check passed.
```

如果任一服务器检查失败，不允许继续发布。

### 阶段 6：数据库迁移

多 API 副本发布时，迁移必须单独执行一次。不能让服务器 A 和服务器 B 的 API 同时启动并发迁移。

推荐只在 Jenkins 或指定一台服务器上执行：

```bash
cd /opt/zhishu/backend
set -a
source /etc/zhishu/zhishu.env
set +a
alembic upgrade head
```

当前 `main.py` 启动时仍会执行迁移。生产发布时至少要做到：

- Jenkins 先单独执行一次迁移。
- 应用服务器滚动重启，不要两台同时冷启动。
- 如果后续增加配置开关，生产环境应设置 `RUN_MIGRATIONS_ON_STARTUP=false`。

### 阶段 7：滚动重启服务器 A/B 的 API

先重启服务器 A，健康检查通过后，再重启服务器 B：

```bash
ssh zhishu-a 'systemctl restart zhishu-api && sleep 10 && curl -fsS http://127.0.0.1:8000/ready'
curl -fsS https://bi.example.com/ready

ssh zhishu-b 'systemctl restart zhishu-api && sleep 10 && curl -fsS http://127.0.0.1:8000/ready'
curl -fsS https://bi.example.com/ready
```

如果任一节点 `/ready` 失败，Jenkins 应中断发布并输出日志：

```bash
ssh zhishu-a 'journalctl -u zhishu-api -n 200 --no-pager'
ssh zhishu-b 'journalctl -u zhishu-api -n 200 --no-pager'
```

### 阶段 8：滚动重启服务器 A/B 的 worker

推荐每台服务器一个 worker。先重启 A，再重启 B：

```bash
ssh zhishu-a 'systemctl restart zhishu-worker && sleep 5 && systemctl status zhishu-worker --no-pager'
ssh zhishu-b 'systemctl restart zhishu-worker && sleep 5 && systemctl status zhishu-worker --no-pager'
```

检查任务队列健康：

```text
GET /api/v1/system/tasks/health
```

### 阶段 9：重载 Nginx

如果 Nginx 配置有变，先检查：

```bash
nginx -t
```

再重载：

```bash
systemctl reload nginx
```

最终检查：

```bash
curl -fsS https://bi.example.com/health
curl -fsS https://bi.example.com/ready
```

## 六、Nginx upstream 示例

Nginx 独立部署时，upstream 指向服务器 A/B 的内网 API 地址：

```nginx
upstream zhishu_backend {
    least_conn;
    server 10.1.5.201:8000 max_fails=3 fail_timeout=10s;
    server 10.1.5.202:8000 max_fails=3 fail_timeout=10s;
}

server {
    listen 80;
    server_name bi.example.com;

    root /opt/zhishu/frontend/dist;
    index index.html;

    client_max_body_size 100m;

    location = /health {
        proxy_pass http://zhishu_backend/health;
        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /ready {
        proxy_pass http://zhishu_backend/ready;
        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://zhishu_backend;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_connect_timeout 5s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /xpack_static/ {
        proxy_pass http://zhishu_backend;
        proxy_connect_timeout 5s;
        proxy_read_timeout 120s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

如果前端静态文件也由服务器 A/B 分别提供，可以把 Nginx 的静态文件也改成 upstream 或使用统一发布目录。第一阶段建议保持简单：Nginx 本机放一份 `frontend/dist`，API 请求转发到 A/B。

## 七、第二阶段：启动脚本和生产配置整理

第二阶段目标是把运行角色从 `start.sh` 中拆出来。不是拆代码，而是拆启动职责。

### 1. 去掉 start.sh 的强绑定

当前 `start.sh` 偏单容器思路，一个入口脚本管理多个角色。生产高可用下不建议继续让一个脚本同时负责：

```text
PostgreSQL
g2-ssr
MCP app
FastAPI API
worker
```

推荐改成：

```text
PostgreSQL: 外部服务，不由应用服务器 start.sh 管
Redis: 外部服务，不由应用服务器 start.sh 管
API: systemd / supervisor 单独管理
worker: systemd / supervisor 单独管理
g2-ssr: 如生产需要，独立服务管理
MCP app: 如生产需要，独立服务管理
```

### 2. systemd 管理 API

`/etc/systemd/system/zhishu-api.service`：

```ini
[Unit]
Description=星通智数 API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=zhishu
Group=zhishu
WorkingDirectory=/opt/zhishu/backend
EnvironmentFile=/etc/zhishu/zhishu.env
ExecStart=/opt/zhishu/backend/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers
Restart=always
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

### 3. systemd 管理 worker

`/etc/systemd/system/zhishu-worker.service`：

```ini
[Unit]
Description=星通智数 Task Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=zhishu
Group=zhishu
WorkingDirectory=/opt/zhishu/backend
EnvironmentFile=/etc/zhishu/zhishu.env
Environment=WORKER_INSTANCE=%H
ExecStart=/opt/zhishu/backend/.venv/bin/python -m scripts.task_worker
Restart=always
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

启用：

```bash
systemctl daemon-reload
systemctl enable zhishu-api
systemctl enable zhishu-worker
systemctl start zhishu-api
systemctl start zhishu-worker
```

### 4. supervisor 备选

如果服务器暂时不用 systemd，也可以使用 supervisor。原则一样：API 和 worker 必须是两个独立 program。

```ini
[program:zhishu-api]
directory=/opt/zhishu/backend
command=/opt/zhishu/backend/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers
user=zhishu
autostart=true
autorestart=true
stopsignal=TERM
stdout_logfile=/opt/zhishu/logs/api.out.log
stderr_logfile=/opt/zhishu/logs/api.err.log
environment=APP_ENV="production"

[program:zhishu-worker]
directory=/opt/zhishu/backend
command=/opt/zhishu/backend/.venv/bin/python -m scripts.task_worker
user=zhishu
autostart=true
autorestart=true
stopsignal=TERM
stdout_logfile=/opt/zhishu/logs/worker.out.log
stderr_logfile=/opt/zhishu/logs/worker.err.log
environment=APP_ENV="production"
```

## 八、Jenkinsfile 伪代码

```groovy
pipeline {
  agent any

  environment {
    APP_HOME = '/opt/zhishu'
    BACKEND_HOME = '/opt/zhishu/backend'
    FRONTEND_DIST = '/opt/zhishu/frontend/dist'
    ENV_FILE = '/etc/zhishu/zhishu.env'
    DEPLOY_HOSTS = 'zhishu-a zhishu-b'
  }

  stages {
    stage('拉取代码') {
      steps {
        git branch: params.BRANCH_NAME, url: env.GIT_URL
      }
    }

    stage('构建前端') {
      steps {
        sh '''
          set -eux
          cd frontend
          npm ci
          npm run build
        '''
      }
    }

    stage('安装后端依赖') {
      steps {
        sh '''
          set -eux
          cd backend
          uv sync --frozen --no-dev --extra cpu
        '''
      }
    }

    stage('发布到服务器 A/B') {
      steps {
        sh '''
          set -eux
          for host in ${DEPLOY_HOSTS}; do
            ssh $host "rm -rf ${BACKEND_HOME}.new && mkdir -p ${BACKEND_HOME}.new"
            rsync -a --exclude '.venv' --exclude '__pycache__' backend/ $host:${BACKEND_HOME}.new/
            rsync -a backend/.venv/ $host:${BACKEND_HOME}.new/.venv/
            ssh $host "
              if [ -d ${BACKEND_HOME} ]; then
                rm -rf ${BACKEND_HOME}.prev
                mv ${BACKEND_HOME} ${BACKEND_HOME}.prev
              fi
              mv ${BACKEND_HOME}.new ${BACKEND_HOME}
              chown -R zhishu:zhishu ${BACKEND_HOME}
            "

            ssh $host "rm -rf ${FRONTEND_DIST}.new && mkdir -p ${FRONTEND_DIST}.new"
            rsync -a frontend/dist/ $host:${FRONTEND_DIST}.new/
            ssh $host "
              if [ -d ${FRONTEND_DIST} ]; then
                rm -rf ${FRONTEND_DIST}.prev
                mv ${FRONTEND_DIST} ${FRONTEND_DIST}.prev
              fi
              mv ${FRONTEND_DIST}.new ${FRONTEND_DIST}
              chown -R zhishu:zhishu /opt/zhishu/frontend
            "
          done
        '''
      }
    }

    stage('生产配置检查') {
      steps {
        sh '''
          set -eux
          for host in ${DEPLOY_HOSTS}; do
            ssh $host "
              cd ${BACKEND_HOME}
              set -a
              . ${ENV_FILE}
              set +a
              APP_ENV=production ${BACKEND_HOME}/.venv/bin/python scripts/production_check.py
            "
          done
        '''
      }
    }

    stage('数据库迁移') {
      steps {
        sh '''
          set -eux
          ssh zhishu-a "
            cd ${BACKEND_HOME}
            set -a
            . ${ENV_FILE}
            set +a
            ${BACKEND_HOME}/.venv/bin/alembic upgrade head
          "
        '''
      }
    }

    stage('滚动重启 API') {
      steps {
        sh '''
          set -eux
          ssh zhishu-a "systemctl restart zhishu-api && sleep 10 && curl -fsS http://127.0.0.1:8000/ready"
          curl -fsS https://bi.example.com/ready

          ssh zhishu-b "systemctl restart zhishu-api && sleep 10 && curl -fsS http://127.0.0.1:8000/ready"
          curl -fsS https://bi.example.com/ready
        '''
      }
    }

    stage('滚动重启 worker') {
      steps {
        sh '''
          set -eux
          ssh zhishu-a "systemctl restart zhishu-worker && sleep 5 && systemctl status zhishu-worker --no-pager"
          ssh zhishu-b "systemctl restart zhishu-worker && sleep 5 && systemctl status zhishu-worker --no-pager"
        '''
      }
    }

    stage('重载 Nginx') {
      steps {
        sh '''
          set -eux
          nginx -t
          systemctl reload nginx
          curl -fsS https://bi.example.com/ready
        '''
      }
    }
  }
}
```

## 九、发布验收清单

每次发布后至少确认：

```bash
ssh zhishu-a 'systemctl status zhishu-api --no-pager'
ssh zhishu-a 'systemctl status zhishu-worker --no-pager'
ssh zhishu-a 'curl -fsS http://127.0.0.1:8000/ready'

ssh zhishu-b 'systemctl status zhishu-api --no-pager'
ssh zhishu-b 'systemctl status zhishu-worker --no-pager'
ssh zhishu-b 'curl -fsS http://127.0.0.1:8000/ready'

curl -fsS https://bi.example.com/ready
```

功能验收：

- 登录成功。
- 数据源列表可打开。
- 智能问答可生成 SQL 和图表。
- 字段同步任务能投递到 Redis 并被任意 worker 消费。
- 停掉服务器 A 的 API 后，Nginx 仍能访问服务器 B。
- 停掉服务器 B 的 worker 后，服务器 A 的 worker 仍能消费任务。
- 上传文件、导出 Excel、图片访问在 A/B 两台服务器之间表现一致。

## 十、回滚策略

建议 Jenkins 发布前保留：

```text
服务器 A/B 上一版 backend 目录
服务器 A/B 上一版 frontend/dist
当前数据库备份文件
当前 /etc/zhishu/zhishu.env
```

前端回滚：

```bash
for host in zhishu-a zhishu-b; do
  ssh $host '
    rm -rf /opt/zhishu/frontend/dist
    mv /opt/zhishu/frontend/dist.prev /opt/zhishu/frontend/dist
    chown -R zhishu:zhishu /opt/zhishu/frontend
  '
done
systemctl reload nginx
```

后端回滚：

```bash
for host in zhishu-a zhishu-b; do
  ssh $host '
    systemctl stop zhishu-api zhishu-worker
    rm -rf /opt/zhishu/backend
    mv /opt/zhishu/backend.prev /opt/zhishu/backend
    chown -R zhishu:zhishu /opt/zhishu/backend
    systemctl start zhishu-api
    systemctl start zhishu-worker
    curl -fsS http://127.0.0.1:8000/ready
  '
done
```

数据库回滚不能随意执行。涉及 Alembic 结构变更时，应优先通过向前修复处理；只有确认备份可恢复、停机窗口明确时，才执行数据库恢复。

## 十一、关键风险和处理建议

### 1. 多 API 并发迁移

当前 API 启动会执行 Alembic 迁移。两台服务器发布时必须在 Jenkins 中单独执行迁移，并避免服务器 A/B 同时冷启动。

后续建议增加配置开关：

```env
RUN_MIGRATIONS_ON_STARTUP=false
```

生产环境默认关闭启动迁移，只允许 Jenkins 或人工运维命令执行迁移。

### 2. worker 幂等

Redis 队列是至少执行一次语义。任务可能因 worker 崩溃、网络抖动或可见性超时恢复而重复执行。

要求：

- 入队使用业务去重键。
- 执行前检查业务状态。
- 写入优先 update/upsert，不盲目 insert。
- 对同一资源的强副作用任务加 Redis 锁。
- 数据库唯一约束兜底。
- 任务 payload 不保存明文密码、token 等敏感信息。

### 3. 文件一致性

两台服务器共同对外服务时，`UPLOAD_DIR`、`EXCEL_PATH`、`MCP_IMAGE_PATH` 必须一致可见。

可选方案：

- 短期：NFS/NAS 挂载到两台服务器的同一路径。
- 中期：对象存储，应用保存 object key，访问时生成下载地址。
- 不推荐：A/B 各自使用本地目录，然后靠手工同步。

### 4. Nginx 单点

如果只有一台 Nginx，即使后端有服务器 A/B，入口仍然是单点。第一阶段可以接受这个限制；后续建议：

- 使用云 SLB 作为入口。
- 使用 Keepalived + VIP 管理双 Nginx。
- 使用 DNS 或网关层做入口高可用。

### 5. Smart Q&A 仍在 API 进程内执行

当前 Smart Q&A 生成主要在 API 进程线程池中执行。API 进程宕机时，正在生成的回答不能被另一个 API 自动接续。

第一阶段接受这个限制；后续要做到更强高可用，需要将问答生成改造成 worker 队列任务。

## 十二、阶段演进

第一阶段：不拆代码，只拆部署。

```text
Nginx
  -> 服务器 A
      API
      worker
  -> 服务器 B
      API
      worker

共享：
  PostgreSQL 10.1.5.193:5432
  Redis
  共享文件目录或对象存储
```

第二阶段：整理启动脚本和生产配置。

```text
去掉单容器 start.sh 的强绑定
使用 systemd / supervisor 分别管理 API 和 worker
生产环境变量统一放到 /etc/zhishu/zhishu.env
迁移由 Jenkins 单独执行，API 启动不再自动迁移
```

第三阶段：依赖层和入口层高可用。

```text
SLB/VIP + 双 Nginx
PostgreSQL HA
Redis HA
对象存储
集中日志
监控告警
```
