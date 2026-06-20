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
- **易于集成**：支持多种集成方式，提供 Web 嵌入、弹窗嵌入、MCP 调用等能力；能够快速嵌入到自动化平台、智能体平台和企业门户等应用，让各类应用快速拥有智能报表能力。
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

### 安装部署

准备一台 Linux 服务器，安装好 [Docker](https://docs.docker.com/get-docker/)，先构建本地基础镜像和应用镜像：

```bash
docker build -f Dockerfile-base -t chat-bi/zhishu-python-pg:latest .
docker build \
  --build-arg BASE_IMAGE=chat-bi/zhishu-python-pg:latest \
  --build-arg RUNTIME_IMAGE=chat-bi/zhishu-python-pg:latest \
  -t chat-bi:latest .
```

然后启动服务：

```bash
docker run -d \
  --name chat-bi \
  --restart unless-stopped \
  -p 8000:8000 \
  -p 8001:8001 \
  -v ./data/chat-bi/excel:/opt/zhishu/data/excel \
  -v ./data/chat-bi/file:/opt/zhishu/data/file \
  -v ./data/chat-bi/images:/opt/zhishu/images \
  -v ./data/chat-bi/logs:/opt/zhishu/app/logs \
  -v ./data/postgresql:/var/lib/postgresql/data \
  --privileged=true \
  chat-bi:latest
```

### 访问方式

- 在浏览器中打开: http://<你的服务器IP>:8000/
- 用户名: admin
- 密码: elex@123

### 联系我们

如你有更多问题，可以加入我们的技术交流群与我们交流。

<img width="180" height="180" alt="contact_me_qr" src="https://github.com/user-attachments/assets/a4b84255-dbe1-43eb-b73f-2bc4ee13f037" />

## UI 展示

  <tr>
    <img alt="q&a" src="https://github.com/user-attachments/assets/55526514-52f3-4cfe-98ec-08a986259280"   />
  </tr>

## License

本仓库遵循 [LICENSE](LICENSE) 中声明的开源协议。

你可以基于星通智数的源代码进行二次开发，但是需要遵守以下规定：

- 不能替换和修改星通智数的 Logo 和版权信息；
- 二次开发后的衍生作品必须遵守 GPL V3 的开源义务。
