<p align="center"><img src="https://resource-fit2cloud-com.oss-cn-hangzhou.aliyuncs.com/sqlbot/sqlbot.png" alt="SQLBot" width="300" /></p>
<h3 align="center">基于大模型和 RAG 的智能问数系统</h3>
<p align="center">
  <a href="https://www.gnu.org/licenses/gpl-3.0.html#license-text"><img src="https://img.shields.io/github/license/1Panel-dev/SQLBot?color=%231890FF" alt="License: GPL v3"></a>
  <a href="https://github.com/1Panel-dev/SQLBot/releases/latest"><img src="https://img.shields.io/github/v/release/1Panel-dev/SQLBot" alt="Latest release"></a>
  <a href="https://github.com/1Panel-dev/SQLBot"><img src="https://img.shields.io/github/stars/1Panel-dev/SQLBot?color=%231890FF&style=flat-square" alt="Stars"></a>    
  <a href="https://hub.docker.com/r/1panel/SQLbot"><img src="https://img.shields.io/docker/pulls/1panel/SQLBot?label=downloads" alt="Download"></a><br/>
</p>
<hr/>

SQLBot 是一款基于大模型和 RAG 的智能问数系统。SQLBot 的优势包括：

- **开箱即用**: 只需配置大模型和数据源即可开启问数之旅，通过大模型和 RAG 的结合来实现高质量的 text2sql；
- **易于集成**: 支持快速嵌入到第三方业务系统，也支持被 n8n、MaxKB、Dify 、Coze 等 AI 应用开发平台集成调用，让各类应用快速拥有智能问数能力；
- **安全可控**: 提供基于工作空间的资源隔离机制，能够实现细粒度的数据权限控制。

## 快速开始

准备一台 Linux 机器，执行一键安装脚本：

```
docker run -d --name=sqlbot --restart=always -p 8080:8080 -v ~/.sqlbot:/var/lib/postgresql/data -v ~/.python-packages:/opt/sqlbot/app/sandbox/python-packages registry.fit2cloud.com/sqlbot/sqlbot

# 用户名: admin
# 密码: SQLBot@123..
```

你也可以通过 [1Panel 应用商店](https://apps.fit2cloud.com/1panel) 快速部署 SQLBot；

如你有更多问题，可以加入我们的技术交流群与我们交流。

TBD

## UI 展示

<table style="border-collapse: collapse; border: 1px solid black;">
  <tr>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo1"   /></td>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo2"   /></td>
  </tr>
  <tr>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo3"   /></td>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo4"   /></td>
  </tr>
</table>

## 飞致云的其他明星项目

- [DataEase](https://github.com/dataease/dataease/) - 人人可用的开源 BI 工具
- [1Panel](https://github.com/1panel-dev/1panel/) - 现代化、开源的 Linux 服务器运维管理面板
- [MaxKB](https://github.com/1panel-dev/MaxKB/) - 基于 LLM 大语言模型的开源知识库问答系统
- [JumpServer](https://github.com/jumpserver/jumpserver/) - 广受欢迎的开源堡垒机
- [Halo](https://github.com/halo-dev/halo/) - 强大易用的开源建站工具
- [MeterSphere](https://github.com/metersphere/metersphere/) - 新一代的开源持续测试工具

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=1Panel-dev/SQLBot&type=Date)](https://star-history.com/#1Panel-dev/SQLBot&Date)

## License

本仓库遵循 [FIT2CLOUD Open Source License](LICENSE) 开源协议，该许可证本质上是 GPLv3，但有一些额外的限制。
