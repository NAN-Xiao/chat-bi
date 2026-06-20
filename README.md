<h1 align="center">星通智数</h1>
<h3 align="center">基于大模型和 RAG 的智能报表系统</h3>

<p align="center">
  <a href="README.md"><img alt="中文(简体)" src="https://img.shields.io/badge/中文(简体)-d9d9d9"></a>
  <a href="/docs/README.en.md"><img alt="English" src="https://img.shields.io/badge/English-d9d9d9"></a>
</p>
<hr/>

星通智数是一款基于大语言模型和 RAG 的智能报表系统。借助星通智数，用户可以实现对话式数据分析（ChatBI），快速提炼获取所需的数据信息及可视化图表，并且支持进一步开展智能分析。

## 工作原理

<img width="1153" height="563" alt="image" src="https://github.com/user-attachments/assets/8bc40db1-2602-4b68-9802-b9be36281967" />

## 核心优势

- **开箱即用**：仅需简单配置大模型与数据源，无需复杂开发，即可快速开启智能报表；依托大模型自然语言理解与 SQL 生成能力，结合 RAG 技术，实现高质量 Text-to-SQL 转换。
- **安全可控**：提供工作空间级资源隔离机制，构建清晰数据边界，保障数据访问安全；支持细粒度数据权限配置，强化权限管控能力，确保使用过程合规可控。
- **易于集成**：支持多种集成方式，提供 Web 嵌入、弹窗嵌入、MCP 调用等能力；能够快速嵌入到现有业务系统和智能体平台，让各类应用快速拥有智能报表能力。
- **越问越准**：支持自定义提示词、术语库配置，可维护 SQL 示例校准逻辑，精准匹配业务场景；高效运营，基于用户交互数据持续迭代优化，报表效果随使用逐步提升，越问越准。

## 支持的大模型服务商

| 服务商 | API 兼容 |
|--------|----------|
| 阿里云百炼 | OpenAI 兼容 |
| 千帆大模型 | OpenAI 兼容 |
| DeepSeek | OpenAI 兼容 |
| 腾讯混元 | OpenAI 兼容 |
| 讯飞星火 | OpenAI 兼容 |
| Gemini | OpenAI 兼容 |
| OpenAI | 原生 |
| Kimi | OpenAI 兼容 |
| 腾讯云 | OpenAI 兼容 |
| 火山引擎 | OpenAI 兼容 |
| MiniMax | OpenAI 兼容 |
| 通用 OpenAI 兼容 | 自定义 |

## 快速开始

### Docker 体验部署

以下命令用于本地体验、功能评估或离线演示。该单容器镜像内置 PostgreSQL，并使用默认初始账号、默认数据库密码和直连 `8000/8001` 端口，**不要直接作为生产部署方案**。

准备一台 Linux 服务器，安装好 [Docker](https://docs.docker.com/get-docker/)，执行：

```bash
docker run -d \
  --name zhishu \
  --restart unless-stopped \
  -p 8000:8000 \
  -p 8001:8001 \
  -v ./data/zhishu/excel:/opt/zhishu/data/excel \
  -v ./data/zhishu/file:/opt/zhishu/data/file \
  -v ./data/zhishu/images:/opt/zhishu/images \
  -v ./data/zhishu/logs:/opt/zhishu/app/logs \
  -v ./data/postgresql:/var/lib/postgresql/data \
  --privileged=true \
  zhishu:latest
```

### 访问方式

- 在浏览器中打开: http://<你的服务器IP>:8000/
- 用户名: admin
- 密码: elex@123

首次体验后请立即在系统内修改管理员密码。暴露到公网、接入企业数据或提供给客户使用前，必须改走生产基线。

### 生产部署

生产环境不要使用上面的快速体验命令，也不要直接使用根目录 `docker-compose.yaml` 中的默认配置。正式上线前请按 [B2B 多租户高可用生产基线](docs/single_tenant_production_readiness.md) 执行，至少完成以下事项：

- 使用 Nginx 统一暴露 `80/443` 和 TLS，后端只监听内网或受控网段。
- 使用独立 PostgreSQL、Redis、backend API 副本和 worker，生产开启 `CACHE_TYPE=redis`。
- 从私有环境变量提供 `SECRET_KEY`、`SENSITIVE_CONFIG_ENCRYPTION_KEY`、数据库密码、Redis 密码和模型 API Key，禁止使用开发默认值。
- 设置 `APP_ENV=production`、`PRODUCTION_CHECKS_ENABLED=true`、`AUTO_RUN_MIGRATIONS=false`，迁移作为发布步骤单独执行。
- 上线前通过后端测试、前端构建、依赖审计、生产配置检查、数据库备份恢复、多租户权限和 worker 故障恢复验收。

### 联系我们

如你有更多问题，可以加入我们的技术交流群与我们交流。

<img width="180" height="180" alt="contact_me_qr" src="https://github.com/user-attachments/assets/a4b84255-dbe1-43eb-b73f-2bc4ee13f037" />

## UI 展示

  <tr>
    <img alt="q&a" src="https://github.com/user-attachments/assets/55526514-52f3-4cfe-98ec-08a986259280"   />
  </tr>

## License

本仓库遵循 [Open Source License](LICENSE) 开源协议，该许可证本质上是 GPLv3，但有一些额外的限制。

你可以基于星通智数的源代码进行二次开发，但是需要遵守以下规定：

- 不能替换和修改星通智数的 Logo 和版权信息；
- 二次开发后的衍生作品必须遵守 GPL V3 的开源义务。

