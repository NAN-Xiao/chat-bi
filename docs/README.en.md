<h1 align="center">星通智数</h1>
<h3 align="center">Intelligent Questioning System Based on Large Models and RAG</h3>

<p align="center">
  <a href="README.md"><img alt="中文(简体)" src="https://img.shields.io/badge/中文(简体)-d9d9d9"></a>
  <a href="/docs/README.en.md"><img alt="English" src="https://img.shields.io/badge/English-d9d9d9"></a>
</p>
<hr/>

星通智数 is an intelligent data query system based on large language models and RAG. With 星通智数, users can perform conversational data analysis (ChatBI), quickly extracting the necessary data information and visualizations, and supporting further intelligent analysis.

## How It Works

<img width="1105" height="577" alt="image" src="https://github.com/user-attachments/assets/58f147ff-412e-4ac9-a450-5d01a0bbe9f6" />


## Key Features

- **Out-of-the-Box Functionality:** Simply configure the large model and data source; no complex development is required to quickly enable intelligent data collection. Leveraging the large model's natural language understanding and SQL generation capabilities, combined with RAG technology, it achieves high-quality Text-to-SQL conversion.
- **Secure and Controllable:** Provides a workspace-level resource isolation mechanism, building clear data boundaries and ensuring data access security. Supports fine-grained data permission configuration, strengthening permission control capabilities and ensuring compliance and controllability during use.
- **Easy Integration:** Supports multiple integration methods, providing capabilities such as web embedding, pop-up embedding, and MCP invocation. It can be quickly embedded into applications such as n8n, Dify, and MaxKB, allowing various applications to quickly acquire intelligent data collection capabilities.
- **Increasingly Accurate with Use:** Supports customizable prompts and terminology library configurations, maintainable SQL example calibration logic, and accurate matching of business scenarios. Efficient operation, based on continuous iteration and optimization using user interaction data, the data collection effect gradually improves with use, becoming more accurate with each use.

## Supported LLM Providers

| Provider | API Compatibility |
|----------|-------------------|
| Alibaba Cloud Bailian | OpenAI Compatible |
| Qianfan Model | OpenAI Compatible |
| DeepSeek | OpenAI Compatible |
| Tencent Hunyuan | OpenAI Compatible |
| iFlytek Spark | OpenAI Compatible |
| Gemini | OpenAI Compatible |
| OpenAI | Native |
| Kimi | OpenAI Compatible |
| Tencent Cloud | OpenAI Compatible |
| Volcano Engine | OpenAI Compatible |
| MiniMax | OpenAI Compatible |
| Generic OpenAI Compatible | Custom |

## Quick Start

### Installation and Deployment

Prepare a Linux server, install [Docker](https://docs.docker.com/get-docker/), and build the local base and application images:

```bash
docker build -f Dockerfile-base -t chat-bi/zhishu-python-pg:latest .
docker build \
  --build-arg BASE_IMAGE=chat-bi/zhishu-python-pg:latest \
  --build-arg RUNTIME_IMAGE=chat-bi/zhishu-python-pg:latest \
  -t chat-bi:latest .
```

Then start the service:

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


### Access methods

- Open in your browser: http://<your server IP>:8000/
- Username: admin
- Password: elex@123


## UI Display

  <tr>
    <img width="1920" height="991" alt="image" src="https://github.com/user-attachments/assets/c9f5e1ff-f654-4375-96be-5511fe30c120" />

    
  </tr>

## License

This repository is licensed under the terms declared in [LICENSE](LICENSE).

You may conduct secondary development based on the 星通智数 source code, but you must adhere to the following:

- You cannot replace or modify the 星通智数 logo and copyright information;

- Derivative works resulting from secondary development must comply with the open-source obligations of GPL v3.
