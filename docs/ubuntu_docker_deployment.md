# Ubuntu Docker 部署文档

本文档用于将星通智数部署到 Ubuntu Linux 服务器。当前仓库已提供单容器体验镜像和 `docker-compose.yaml`，适合内网试用、演示和迁移验证；正式生产上线前建议进一步拆分为独立 PostgreSQL、Redis、Nginx、backend 和 worker。

## 1. 部署目标

基础部署完成后，服务访问方式如下：

```text
http://服务器IP:8000/
```

容器内包含：

- backend API：`8000`
- MCP 服务：`8001`
- PostgreSQL 系统库：容器内 `5432`
- 前端静态资源：由 backend 对外提供

持久化数据保存在服务器项目目录下的 `data/`：

```text
data/postgresql          # 系统库数据
data/zhishu/file         # 上传文件
data/zhishu/excel        # Excel/CSV 相关文件
data/zhishu/images       # 图片文件
data/zhishu/logs         # 应用日志
```

## 2. 服务器要求

建议配置：

- Ubuntu 22.04 LTS 或 Ubuntu 24.04 LTS
- CPU：4 核或以上
- 内存：8 GB 或以上
- 磁盘：100 GB 或以上，生产环境建议单独挂载数据盘
- 网络：内网开放 `8000`，如需要 MCP 再开放 `8001`

如果后续正式对外访问，建议通过 Nginx 暴露 `80/443`，不要直接暴露后端端口。

## 3. 安装 Docker

在 Ubuntu 服务器执行：

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg git python3

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
| sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

验证安装：

```bash
docker --version
docker compose version
```

可选：将当前用户加入 docker 组，避免每次都输入 `sudo`：

```bash
sudo usermod -aG docker $USER
newgrp docker
```

## 4. 准备项目目录

推荐统一部署到 `/opt/zhishu/chat-bi`：

```bash
sudo mkdir -p /opt/zhishu
sudo chown -R $USER:$USER /opt/zhishu
cd /opt/zhishu
```

如果服务器可以访问 Git 仓库：

```bash
git clone <你的仓库地址> chat-bi
cd chat-bi
```

如果服务器不能访问 Git，可以在本地打包后上传：

```bash
tar -czf chat-bi.tar.gz chat-bi
scp chat-bi.tar.gz user@服务器IP:/opt/zhishu/
```

服务器解压：

```bash
cd /opt/zhishu
tar -xzf chat-bi.tar.gz
cd chat-bi
```

## 5. 构建 Docker 镜像

当前项目需要先构建基础镜像，再构建应用镜像：

```bash
cd /opt/zhishu/chat-bi

export DOCKER_BUILDKIT=1

docker build -f Dockerfile-base \
  -t zhishu-base:local \
  -t zhishu-python-pg:local \
  .

docker buildx build \
  --load \
  -t zhishu:latest \
  --build-arg ZHISHU_BASE_IMAGE=zhishu-base:local \
  --build-arg ZHISHU_RUNTIME_IMAGE=zhishu-python-pg:local \
  --build-arg VITE_API_BASE_URL=./api/v1 \
  --build-arg PYTHON_DEPENDENCY_EXTRA=cpu \
  .
```

说明：

- `Dockerfile-base` 会安装 Python、Node.js、PostgreSQL 基础环境和数据库驱动。
- 上面两个本地基础镜像 tag 指向同一个构建结果，分别供 `ZHISHU_BASE_IMAGE` 和 `ZHISHU_RUNTIME_IMAGE` 引用。
- `Dockerfile` 会构建前端、后端依赖和图表 SSR 服务。
- 首次构建耗时较长，通常需要数分钟到数十分钟，取决于服务器网络和 CPU。

构建完成后检查镜像：

```bash
docker images | grep zhishu
```

## 6. 准备 Compose 配置

不要直接改原始 `docker-compose.yaml`，先复制一份本机部署配置：

```bash
cp docker-compose.yaml docker-compose.local.yaml
```

生成两个随机密钥：

```bash
python3 - <<'PY'
import secrets
print("SECRET_KEY=" + secrets.token_urlsafe(48))
print("SENSITIVE_CONFIG_ENCRYPTION_KEY=" + secrets.token_urlsafe(48))
PY
```

编辑配置：

```bash
nano docker-compose.local.yaml
```

建议至少修改以下内容：

```yaml
services:
  zhishu:
    image: zhishu:latest
    container_name: zhishu
    restart: always
    privileged: true
    ports:
      - 8000:8000
      - 8001:8001
    environment:
      POSTGRES_SERVER: localhost
      POSTGRES_PORT: 5432
      POSTGRES_DB: zhishu_bi
      POSTGRES_USER: root
      POSTGRES_PASSWORD: 请改成强密码

      PROJECT_NAME: "星通智数"
      DEFAULT_PWD: "请改成强初始密码"

      MCP_ENABLED: "false"
      SERVER_IMAGE_HOST: http://服务器IP:8001/images/

      SECRET_KEY: 请填入上一步生成的_SECRET_KEY
      SENSITIVE_CONFIG_ENCRYPTION_KEY: 请填入上一步生成的_SENSITIVE_CONFIG_ENCRYPTION_KEY

      BACKEND_CORS_ORIGINS: "http://服务器IP:8000,http://127.0.0.1:8000,http://localhost:8000"
      LOG_LEVEL: "INFO"
      SQL_DEBUG: "false"
```

注意：

- `POSTGRES_PASSWORD` 不要使用默认值。
- `DEFAULT_PWD` 是初始化管理员密码，登录后应立即修改。
- `SECRET_KEY` 和 `SENSITIVE_CONFIG_ENCRYPTION_KEY` 必须长期保存，迁移时要跟数据库一起保留。
- 内网部署时 `服务器IP` 填内网 IP。
- 如果暂时不用 MCP，保持 `MCP_ENABLED=false`。

## 7. 创建持久化目录

```bash
cd /opt/zhishu/chat-bi

mkdir -p data/zhishu/excel
mkdir -p data/zhishu/file
mkdir -p data/zhishu/images
mkdir -p data/zhishu/logs
mkdir -p data/postgresql
```

## 8. 启动服务

```bash
docker compose -f docker-compose.local.yaml up -d
```

查看容器：

```bash
docker ps
```

查看启动日志：

```bash
docker logs -f zhishu
```

看到 backend 启动并监听 `8000` 后，执行健康检查：

```bash
curl http://127.0.0.1:8000/health
```

浏览器访问：

```text
http://服务器IP:8000/
```

默认管理员：

```text
用户名：admin
密码：docker-compose.local.yaml 中 DEFAULT_PWD 的值
```

首次登录后请立即修改管理员密码。

## 9. 防火墙放行

如果服务器启用了 UFW：

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
sudo ufw reload
sudo ufw status
```

如果部署在云服务器，还需要在云厂商安全组中放行 `8000`，如确实需要 MCP 再放行 `8001`。

内网正式使用时，建议只在内网安全组或 VPN 网段内开放。

## 10. 配置大模型和数据源

登录系统后，在后台配置默认大模型。

本项目当前内网可用的大模型配置参考：

```text
base_url=https://aikey.elex-tech.com/v1
default_model=qwen3.5-plus
embedding_model=text-embedding-v4
```

API Key 应在系统界面或生产环境变量中配置，不要写入 Git。

系统库是：

```text
PostgreSQL database: zhishu_bi
host: 容器内 localhost
port: 5432
user: root
password: docker-compose.local.yaml 中 POSTGRES_PASSWORD 的值
```

如果要接入业务数据库或演示数据库，请在系统的数据源管理里新增，不要和系统库混用。

## 11. 常用运维命令

进入项目目录：

```bash
cd /opt/zhishu/chat-bi
```

查看服务：

```bash
docker compose -f docker-compose.local.yaml ps
```

查看日志：

```bash
docker logs -f zhishu
```

重启：

```bash
docker compose -f docker-compose.local.yaml restart
```

停止：

```bash
docker compose -f docker-compose.local.yaml down
```

启动：

```bash
docker compose -f docker-compose.local.yaml up -d
```

进入容器：

```bash
docker exec -it zhishu bash
```

查看容器内数据库连接：

```bash
docker exec -it zhishu bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select now();"'
```

## 12. 版本升级

升级前先备份，至少备份 `data/` 和 `docker-compose.local.yaml`。

```bash
cd /opt/zhishu/chat-bi

tar -czf zhishu-data-before-upgrade-$(date +%F-%H%M%S).tar.gz data docker-compose.local.yaml
```

拉取新代码：

```bash
git pull
```

重新构建镜像：

```bash
export DOCKER_BUILDKIT=1

docker build -f Dockerfile-base \
  -t zhishu-base:local \
  -t zhishu-python-pg:local \
  .

docker buildx build \
  --load \
  -t zhishu:latest \
  --build-arg ZHISHU_BASE_IMAGE=zhishu-base:local \
  --build-arg ZHISHU_RUNTIME_IMAGE=zhishu-python-pg:local \
  --build-arg VITE_API_BASE_URL=./api/v1 \
  --build-arg PYTHON_DEPENDENCY_EXTRA=cpu \
  .
```

重启容器：

```bash
docker compose -f docker-compose.local.yaml up -d
```

验证：

```bash
curl http://127.0.0.1:8000/health
docker logs --tail=200 zhishu
```

## 13. 数据备份

### 13.1 文件级备份

停止服务后备份最稳：

```bash
cd /opt/zhishu/chat-bi

docker compose -f docker-compose.local.yaml down
tar -czf zhishu-full-data-$(date +%F-%H%M%S).tar.gz data docker-compose.local.yaml
docker compose -f docker-compose.local.yaml up -d
```

### 13.2 PostgreSQL 逻辑备份

服务运行时也可以做逻辑备份：

```bash
cd /opt/zhishu/chat-bi

docker exec -e PGPASSWORD='你的POSTGRES_PASSWORD' zhishu \
  pg_dump -h 127.0.0.1 -U root -d zhishu_bi \
  -Fc -f /opt/zhishu/app/logs/zhishu_bi.dump

cp data/zhishu/logs/zhishu_bi.dump ./zhishu_bi-$(date +%F-%H%M%S).dump
```

建议每天至少做一次 PostgreSQL 逻辑备份，并定期把备份复制到另一台机器或对象存储。

## 14. 迁移到新服务器

旧服务器：

```bash
cd /opt/zhishu/chat-bi

docker compose -f docker-compose.local.yaml down
tar -czf zhishu-migrate-$(date +%F-%H%M%S).tar.gz data docker-compose.local.yaml
```

传到新服务器：

```bash
scp zhishu-migrate-*.tar.gz user@新服务器IP:/opt/zhishu/chat-bi/
```

新服务器先按本文档安装 Docker、准备代码并构建镜像，然后恢复数据：

```bash
cd /opt/zhishu/chat-bi
tar -xzf zhishu-migrate-*.tar.gz
docker compose -f docker-compose.local.yaml up -d
```

验证：

```bash
curl http://127.0.0.1:8000/health
docker logs --tail=200 zhishu
```

如果服务器 IP 变了，记得修改：

- `docker-compose.local.yaml` 中的 `SERVER_IMAGE_HOST`
- `BACKEND_CORS_ORIGINS`
- 前端访问地址或 Nginx 域名配置

## 15. 可选：用 Nginx 统一入口

如果希望用户访问：

```text
http://bi.company.local/
```

可以在宿主机安装 Nginx：

```bash
sudo apt install -y nginx
```

创建配置：

```bash
sudo nano /etc/nginx/sites-available/zhishu.conf
```

写入：

```nginx
server {
    listen 80;
    server_name bi.company.local;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_connect_timeout 5s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：

```bash
sudo ln -sf /etc/nginx/sites-available/zhishu.conf /etc/nginx/sites-enabled/zhishu.conf
sudo nginx -t
sudo systemctl reload nginx
```

如果使用 Nginx，建议在防火墙上只开放 `80/443`，并限制 `8000/8001` 只允许本机或内网访问。

## 16. 正式生产上线建议

当前根目录 `docker-compose.yaml` 是体验部署，不建议直接作为长期生产方案。正式上线前建议升级为：

```text
Nginx
  -> backend API 多副本
  -> frontend 静态资源

backend API
  -> 独立 PostgreSQL 系统库
  -> 独立 Redis
  -> 共享文件目录或对象存储

worker
  -> Redis 任务队列
  -> PostgreSQL 系统库
```

生产环境关键要求：

- 使用独立 PostgreSQL，不和应用放在同一个容器生命周期里。
- 使用 Redis 作为缓存、限流和任务队列。
- `SECRET_KEY`、`SENSITIVE_CONFIG_ENCRYPTION_KEY`、数据库密码、Redis 密码不能使用默认值。
- 关闭 `SQL_DEBUG`。
- 生产设置 `AUTO_RUN_MIGRATIONS=false`，数据库迁移作为发布步骤单独执行一次。
- Nginx 暴露 `80/443`，backend 只监听内网。
- 配置定时备份和恢复演练。

仓库中已有更完整的生产基线说明：

```text
docs/single_tenant_production_readiness.md
```

## 17. 故障排查

容器没起来：

```bash
docker ps -a
docker logs --tail=300 zhishu
```

端口被占用：

```bash
sudo ss -lntp | grep -E ':8000|:8001'
```

健康检查失败：

```bash
curl -v http://127.0.0.1:8000/health
docker logs --tail=300 zhishu
```

数据库异常：

```bash
docker exec -it zhishu bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

前端能打开但问答失败：

- 检查默认大模型配置是否正确。
- 检查 API Key 是否可用。
- 检查服务器是否能访问大模型 `base_url`。
- 检查数据源连接配置和权限。

查看最近日志：

```bash
docker logs --tail=300 zhishu
tail -n 300 data/zhishu/logs/*.log
```

