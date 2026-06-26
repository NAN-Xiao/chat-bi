# 星通智数 Docker 发布文档

本文档基于当前仓库的 `Dockerfile`、`Jenkinsfile`、`start.sh`、`docker-compose.yaml` 和 `installer` 脚本整理，说明 Docker 镜像构建、运行、发布、回滚与排障流程。

## 一、当前发布模型

当前仓库同时保留了几类部署资产，需要先区分清楚：

| 文件 | 当前定位 | 注意事项 |
| --- | --- | --- |
| `Dockerfile` | 当前 Docker 应用镜像构建主入口 | 运行目录为 `/opt/zhishu` |
| `Dockerfile-base` | 构建本地基础镜像 | 可作为 `Dockerfile` 的基础镜像来源 |
| `start.sh` | 容器入口脚本 | 通过 `APP_ROLE` 控制容器角色 |
| `Jenkinsfile` | 当前推荐的 Docker 发布主线 | 构建镜像、执行迁移、重启 systemd 管理的 Docker 实例、发布前端静态文件 |
| `docker-compose.yaml` | 单容器本地/简易部署参考 | 使用 `/opt/zhishu` 路径 |
| `installer/zhishu/docker-compose.yml` | 历史安装包模板 | 使用前需要校准镜像名、端口和环境变量 |
| `deploy/systemd/*.service` | 历史非 Docker systemd 模板 | 直接运行 Python 虚拟环境，不是当前 Jenkins Docker 发布方式 |

推荐生产发布路径：

```text
Git 分支
  -> Jenkins 拉取代码
  -> docker buildx 构建 zhishu:<tag>
  -> docker run APP_ROLE=migrate 执行 Alembic 迁移
  -> systemd 重启 API / worker Docker 实例
  -> 从镜像中复制 frontend/dist 到 Nginx 静态目录
  -> Nginx 反向代理 /api/v1/ 到 API 多副本
```

## 二、镜像构建结构

`Dockerfile` 是多阶段构建：

| 阶段 | 作用 |
| --- | --- |
| `zhishu-ui-builder` | 安装前端依赖并执行 `npm run build` |
| `zhishu-builder` | 使用 `uv sync` 安装后端 Python 依赖，并复制后端代码和前端构建产物 |
| `ssr-builder` | 构建 G2 SSR 图片服务运行目录 |
| runtime | 基于 PostgreSQL/Python 运行镜像，复制应用、SSR 和入口脚本 |

最终镜像默认暴露端口：

| 端口 | 用途 |
| --- | --- |
| `3000` | G2 SSR 图片服务 |
| `8000` | 后端 API 默认端口 |
| `8001` | MCP 服务默认端口 |
| `5432` | 容器内嵌 PostgreSQL，只有 `POSTGRES_SERVER=localhost/127.0.0.1` 时才会启动 |

## 三、构建参数

当前 `Dockerfile` 支持的主要构建参数如下：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `ZHISHU_BASE_IMAGE` | `zhishu-base:local` | 前端、后端、SSR 构建阶段基础镜像 |
| `ZHISHU_RUNTIME_IMAGE` | `zhishu-python-pg:local` | 最终运行镜像 |
| `VITE_API_BASE_URL` | `./api/v1` | 前端构建时的 API 基础路径 |
| `PYTHON_DEPENDENCY_EXTRA` | `cpu` | Python 可选依赖集合，默认使用 CPU 版依赖 |

注意：README 中旧示例使用过 `BASE_IMAGE` / `RUNTIME_IMAGE`，历史安装包里也会出现旧命名，但当前 `Dockerfile` 的实际参数名是 `ZHISHU_BASE_IMAGE` / `ZHISHU_RUNTIME_IMAGE`。

## 四、本地构建

### 4.1 使用本地基础镜像构建

```bash
export DOCKER_BUILDKIT=1

docker build \
  -f Dockerfile-base \
  -t zhishu-base:local \
  -t zhishu-python-pg:local \
  .

docker buildx build \
  --load \
  --tag zhishu:local \
  --build-arg VITE_API_BASE_URL=./api/v1 \
  --build-arg PYTHON_DEPENDENCY_EXTRA=cpu \
  .
```

### 4.2 覆盖基础镜像

如果有内网镜像仓库，可以通过 `ZHISHU_BASE_IMAGE` / `ZHISHU_RUNTIME_IMAGE` 覆盖基础镜像来源：

```bash
docker buildx build \
  --load \
  --tag zhishu:local \
  --build-arg ZHISHU_BASE_IMAGE=registry.example.com/zhishu-base:latest \
  --build-arg ZHISHU_RUNTIME_IMAGE=registry.example.com/zhishu-python-pg:latest \
  --build-arg VITE_API_BASE_URL=./api/v1 \
  --build-arg PYTHON_DEPENDENCY_EXTRA=cpu \
  .
```

`Dockerfile-base` 只有一个最终镜像阶段，默认的 `zhishu-base:local` 和 `zhishu-python-pg:local` 两个 tag 指向同一个本地基础镜像，分别供 `ZHISHU_BASE_IMAGE` 和 `ZHISHU_RUNTIME_IMAGE` 引用。

## 五、单容器运行

单容器模式适合本地验证或小规模试运行。它会在同一个容器中启动 PostgreSQL、迁移、G2 SSR、可选 MCP 和 API。

```bash
mkdir -p data/zhishu/{excel,file,images,logs} data/postgresql

docker run -d \
  --name chat-bi \
  --restart unless-stopped \
  -p 8000:8000 \
  -p 8001:8001 \
  -e APP_ROLE=all \
  -e POSTGRES_SERVER=localhost \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=zhishu_bi \
  -e POSTGRES_USER=root \
  -e POSTGRES_PASSWORD='Password123@pg' \
  -e PROJECT_NAME='星通智数' \
  -e DEFAULT_PWD='elex@123' \
  -e FRONTEND_HOST='http://localhost:8000' \
  -e BACKEND_CORS_ORIGINS='http://localhost:8000,http://127.0.0.1:8000' \
  -e SERVER_IMAGE_HOST='http://localhost:8001/images/' \
  -e MCP_ENABLED=false \
  -v "$PWD/data/zhishu/excel:/opt/zhishu/data/excel" \
  -v "$PWD/data/zhishu/file:/opt/zhishu/data/file" \
  -v "$PWD/data/zhishu/images:/opt/zhishu/images" \
  -v "$PWD/data/zhishu/logs:/opt/zhishu/app/logs" \
  -v "$PWD/data/postgresql:/var/lib/postgresql/data" \
  zhishu:local
```

访问：

```text
http://服务器IP:8000/
```

默认账号通常为：

```text
用户名：admin
密码：elex@123
```

实际默认密码以 `DEFAULT_PWD` 和初始化数据为准。

## 六、容器角色

`start.sh` 通过 `APP_ROLE` 控制容器行为：

| `APP_ROLE` | 行为 |
| --- | --- |
| `all` | 单容器模式；启动内嵌或外部 PostgreSQL 检查、迁移、G2 SSR、可选 MCP、API |
| `migrate` | 只等待依赖并执行 `alembic upgrade head` |
| `api` | 只启动 API |
| `worker` | 只启动任务队列 worker |
| `mcp` | 只启动 MCP 服务 |
| `g2-ssr` | 只启动 G2 SSR 图片服务 |

生产多副本模式建议使用独立角色：

```text
迁移：APP_ROLE=migrate，发布时只运行一次
API：APP_ROLE=api，可按端口启动多个实例
Worker：APP_ROLE=worker，可按实例编号启动多个消费者
MCP：默认关闭，确需开启时单独评估访问控制
G2 SSR：可单独运行，或由单容器/all 模式后台启动
```

## 七、核心运行环境变量

| 变量 | 说明 |
| --- | --- |
| `PROJECT_NAME` | 项目名称 |
| `POSTGRES_SERVER` / `POSTGRES_PORT` | 系统库地址和端口 |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | 系统库名称、用户和密码 |
| `SECRET_KEY` | 服务端密钥，生产环境必须长期稳定保存 |
| `DEFAULT_PWD` | 初始化普通用户默认密码 |
| `FRONTEND_HOST` | 前端访问地址 |
| `BACKEND_CORS_ORIGINS` | 后端 CORS 白名单 |
| `SERVER_IMAGE_HOST` | 图片访问地址 |
| `BASE_DIR` | 应用基础目录，Docker 内建议 `/opt/zhishu` |
| `UPLOAD_DIR` | 文件上传目录，Docker 内建议 `/opt/zhishu/data/file` |
| `EXCEL_PATH` | Excel 目录，Docker 内建议 `/opt/zhishu/data/excel` |
| `MCP_IMAGE_PATH` | 图片目录，Docker 内建议 `/opt/zhishu/images` |
| `LOG_DIR` | 日志目录，Docker 内建议 `/opt/zhishu/app/logs` |
| `CACHE_TYPE` | 缓存类型；多副本生产建议 `redis` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | Redis 连接配置 |
| `TASK_QUEUE_*` | Redis 任务队列配置 |
| `MCP_ENABLED` | 是否启用 MCP，默认建议 `false` |

## 八、Jenkins 发布流程

当前 `Jenkinsfile` 的参数：

| 参数 | 当前默认值 | 说明 |
| --- | --- | --- |
| `BRANCH_NAME` | `release_ha` | 发布分支 |
| `IMAGE_TAG` | 空 | 空值时使用 `BUILD_NUMBER-git短哈希` |
| `CLEAN_OLD_IMAGES` | `false` | 是否清理旧版本镜像 |
| `CLEAN_DANGLING_IMAGES` | `false` | 是否清理悬空镜像，开启会影响构建缓存 |

当前 Jenkins 环境常量：

| 变量 | 当前值 | 说明 |
| --- | --- | --- |
| `APP_HOME` | `/home/chat-bi` | 发布机运行目录 |
| `IMAGE_REPOSITORY` | `zhishu` | 镜像仓库名 |
| `FRONTEND_HOST` | `10.1.5.28` | 前端/Nginx 服务地址 |
| `NGINX_ROOT` | `/home/chat-bi/nginx/html` | 前端静态文件发布目录 |
| `RUNTIME_ENV_FILE` | `/home/chat-bi/chat-bi.runtime.env` | Jenkins 生成的容器运行环境文件 |

Jenkins 发布阶段：

1. 拉取 `BRANCH_NAME` 指定分支。
2. 生成镜像标签、提交哈希、构建时间等变量。
3. 读取 `installer/install.conf`，生成 `/home/chat-bi/chat-bi.runtime.env`。
4. 执行 `docker buildx build --load --tag "$IMAGE" ... .`。
5. 生成 Nginx 参考配置 `/home/chat-bi/chat-bi-nginx.conf`。
6. 使用 `docker run --rm -e APP_ROLE=migrate` 执行数据库迁移。
7. 停止旧单容器实例和旧 MCP 容器。
8. 通过 SSH 重启宿主机预配置的 `chat-bi-api@端口.service` 和 `chat-bi-worker@编号.service`。
9. 从镜像复制 `/opt/zhishu/frontend/dist` 到 Nginx 静态目录。
10. 根据参数清理旧镜像、退出容器和悬空镜像。

## 九、生产发布前检查清单

发布前建议确认：

```bash
git branch --all --list '*release_ha*'
docker version
docker buildx version
docker system df
```

确认 `installer/install.conf` 中关键配置：

```bash
ZHISHU_API_PORTS="8000 8002"
ZHISHU_WORKER_IDS="1 2"
ZHISHU_CACHE_TYPE="redis"
ZHISHU_REDIS_HOST=10.1.5.28
ZHISHU_DB_HOST=10.1.5.28
ZHISHU_DB_DB=zhishu_bi
ZHISHU_MCP_ENABLED=false
```

多副本发布必须使用 Redis：

```text
CACHE_TYPE=redis
```

原因是认证状态、助手状态、任务队列、限流和共享缓存不能依赖进程本地内存。

## 十、systemd Docker 实例要求

当前 Jenkinsfile 不安装 systemd unit，只提示：

```text
chat-bi-api@.service 和 chat-bi-worker@.service 已由宿主机预先配置
```

因此宿主机需要提前配置 Docker 版 systemd unit。推荐形态如下。

API 实例模板示例：

```ini
[Unit]
Description=Chat BI API container on port %i
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
EnvironmentFile=/home/chat-bi/chat-bi-systemd.env
ExecStartPre=-/usr/bin/docker rm -f chat-bi-api-%i
ExecStart=/usr/bin/docker run --rm \
  --name chat-bi-api-%i \
  --env-file ${RUNTIME_ENV_FILE} \
  -e APP_ROLE=api \
  -e API_HOST=0.0.0.0 \
  -e API_PORT=%i \
  -p 127.0.0.1:%i:%i \
  -v ${APP_HOME}/data/zhishu/excel:/opt/zhishu/data/excel \
  -v ${APP_HOME}/data/zhishu/file:/opt/zhishu/data/file \
  -v ${APP_HOME}/data/zhishu/images:/opt/zhishu/images \
  -v ${APP_HOME}/data/zhishu/logs:/opt/zhishu/app/logs \
  ${IMAGE}
ExecStop=/usr/bin/docker stop chat-bi-api-%i
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Worker 实例模板示例：

```ini
[Unit]
Description=Chat BI worker container %i
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
EnvironmentFile=/home/chat-bi/chat-bi-systemd.env
ExecStartPre=-/usr/bin/docker rm -f chat-bi-worker-%i
ExecStart=/usr/bin/docker run --rm \
  --name chat-bi-worker-%i \
  --env-file ${RUNTIME_ENV_FILE} \
  -e APP_ROLE=worker \
  -e WORKER_INSTANCE=%i \
  -v ${APP_HOME}/data/zhishu/excel:/opt/zhishu/data/excel \
  -v ${APP_HOME}/data/zhishu/file:/opt/zhishu/data/file \
  -v ${APP_HOME}/data/zhishu/images:/opt/zhishu/images \
  -v ${APP_HOME}/data/zhishu/logs:/opt/zhishu/app/logs \
  ${IMAGE}
ExecStop=/usr/bin/docker stop chat-bi-worker-%i
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

应用模板后：

```bash
sudo systemctl daemon-reload
sudo systemctl enable chat-bi-api@8000.service chat-bi-api@8002.service
sudo systemctl enable chat-bi-worker@1.service chat-bi-worker@2.service
```

## 十一、Nginx 发布与代理

Jenkins 会把前端构建产物从镜像中复制出来：

```bash
docker cp "$tmp_container:/opt/zhishu/frontend/dist/." "$nginx_tmp"
```

并原子替换：

```text
/home/chat-bi/nginx/html
```

Jenkins 还会生成参考配置：

```text
/home/chat-bi/chat-bi-nginx.conf
```

但不会自动安装或 reload 宿主机 Nginx，需要运维人工比对后应用到：

```text
/etc/nginx/conf.d/chat-bi.conf
```

API upstream 来自 `ZHISHU_API_PORTS`：

```nginx
upstream chat_bi_backend {
    least_conn;
    server 127.0.0.1:8000 max_fails=3 fail_timeout=10s;
    server 127.0.0.1:8002 max_fails=3 fail_timeout=10s;
}
```

## 十二、回滚方案

### 12.1 镜像回滚

1. 查看可用镜像：

```bash
docker images zhishu
```

2. 修改 `/home/chat-bi/chat-bi-systemd.env` 中的 `IMAGE`：

```bash
IMAGE=zhishu:<上一版本tag>
```

3. 重启服务：

```bash
sudo systemctl restart chat-bi-api@8000.service chat-bi-api@8002.service
sudo systemctl restart chat-bi-worker@1.service chat-bi-worker@2.service
```

### 12.2 前端静态文件回滚

Jenkins 发布前端时会临时生成 `html.prev.*`，发布失败会自动恢复。发布成功后备份目录会删除，因此若需要可审计回滚，建议发布前手动归档：

```bash
tar -czf /home/chat-bi/nginx/html-$(date +%Y%m%d_%H%M%S).tar.gz -C /home/chat-bi/nginx html
```

### 12.3 数据库回滚

数据库迁移不可简单依赖镜像回滚自动逆转。生产发布前应先备份系统库：

```bash
pg_dump -h 10.1.5.28 -p 5432 -U root -Fc zhishu_bi > zhishu_bi-before-release.dump
```

如需回滚数据库，应按 Alembic 迁移内容和备份策略单独评估。

## 十三、常见排障

### 13.1 构建失败：基础镜像不存在

检查：

```bash
docker images zhishu-base
docker images zhishu-python-pg
```

如果不存在，先执行：

```bash
docker build -f Dockerfile-base -t zhishu-base:local -t zhishu-python-pg:local .
```

如果使用内网镜像仓库，通过 `ZHISHU_BASE_IMAGE` / `ZHISHU_RUNTIME_IMAGE` 覆盖。

### 13.2 前端 API 地址不对

当前 Jenkins 使用：

```text
VITE_API_BASE_URL=./api/v1
```

这要求 Nginx 同域代理 `/api/v1/` 到后端。若前后端分域部署，需要重新构建镜像并设置合适的 `VITE_API_BASE_URL`。

### 13.3 API 多副本登录态异常

检查是否使用 Redis：

```bash
grep -E '^(CACHE_TYPE|REDIS_HOST|REDIS_PORT|REDIS_DB)=' /home/chat-bi/chat-bi.runtime.env
```

多副本模式下不要使用 `CACHE_TYPE=memory`。

### 13.4 迁移失败

查看迁移容器日志：

```bash
docker logs chat-bi-migrate
```

如果容器已自动删除，需要从 Jenkins 失败日志或应用日志中查看：

```bash
tail -n 300 /home/chat-bi/data/zhishu/logs/*.log
```

### 13.5 systemd 服务启动失败

检查：

```bash
sudo systemctl status chat-bi-api@8000.service --no-pager
sudo journalctl -u chat-bi-api@8000.service -n 200 --no-pager
docker ps -a --filter 'name=chat-bi-api'
```

重点确认：

```text
/home/chat-bi/chat-bi-systemd.env 是否存在
/home/chat-bi/chat-bi.runtime.env 是否存在
IMAGE 指向的镜像是否存在
宿主机挂载目录是否有权限
API 端口是否被占用
```

### 13.6 路径混用导致文件找不到

当前 Docker 镜像内部路径是：

```text
/opt/zhishu
```

历史草稿或旧发布脚本里仍可能出现和当前路径不一致的旧路径。

使用 Docker 发布时，容器内挂载目标应以 `/opt/zhishu` 为准；宿主机目录当前 Jenkins 使用 `/home/chat-bi`。

## 十四、建议改进项

1. 将 Docker 版 `chat-bi-api@.service` 和 `chat-bi-worker@.service` 模板纳入仓库，避免宿主机手工配置不可追溯。
2. 更新 README 中旧的 `BASE_IMAGE` / `RUNTIME_IMAGE` 示例参数，避免和当前 `Dockerfile` 不一致。
3. Jenkins 发布成功后保留最近一次前端静态文件归档，提升前端回滚确定性。
4. 若后续启用 MCP，应补充访问控制和网络隔离说明，避免直接暴露工具服务。
