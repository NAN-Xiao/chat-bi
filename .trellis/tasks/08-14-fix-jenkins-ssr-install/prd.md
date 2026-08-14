# 修复 Jenkins SSR 依赖安装长时间挂起

## Goal

消除 Jenkins 构建 `g2-ssr` 镜像层时因 GitHub Release 二进制下载停滞而无限等待的问题，使依赖安装可复现、失败有明确上限，并保持现有 SSR 运行能力。

## Background

- Jenkins `chat-bi` #82 和 #83 均停在 Dockerfile 的 `ssr-builder` 阶段 `RUN npm install`。
- #83 中 `canvas@2.11.2` 的 `node-pre-gyp` 连接 GitHub CDN `185.199.109.133:443`，接收约 7.1 MB 后超过 26 分钟无新数据；完整预编译包约 48.7 MB。
- 同一 Jenkins 主机通过另一个 GitHub CDN 节点可在约 15 秒完成相同文件下载，证明问题是外部二进制下载连接停滞，而非 CPU、磁盘或 Docker 资源不足。
- `g2-ssr/package.json` 当前没有 lockfile，Dockerfile 使用 `npm install`；Jenkins 的“构建 Docker 镜像”阶段没有超时。
- `Dockerfile` 已安装 `build-essential`、Python、pkg-config、cairo/pango/jpeg/gif/rsvg/pixman/freetype 开发库，满足 canvas 源码编译前置条件。

## Requirements

1. `g2-ssr` 依赖必须通过提交到仓库的 lockfile 固定解析结果，并在镜像构建中使用 `npm ci`。
2. SSR 依赖安装不得依赖 `canvas` 的 GitHub Release 预编译二进制；应使用已有系统工具链从源码编译 native addon。
3. npm 下载缓存应使用 BuildKit cache mount，避免基础镜像刷新后重复下载全部 registry 包，同时不得把缓存内容写入最终镜像。
4. Jenkins 的“构建 Docker 镜像”阶段必须有明确超时；外部依赖或 BuildKit 异常时应失败并显示超时，而不是无限等待。
5. 不改变前端、后端、SSR 的业务行为，不修改 Jenkins 远程任务配置，不引入业务相关兼容兜底。
6. 增加自动化契约测试，覆盖 lockfile、`npm ci`、源码编译开关和 Jenkins 阶段超时，防止后续回退到无锁或无上限构建。

## Acceptance Criteria

- [ ] `g2-ssr/package-lock.json` 存在，锁定文件可通过目标 Node/npm 版本执行 `npm ci --ignore-scripts` 校验。
- [ ] Dockerfile 的 SSR 安装使用 `npm ci`，并设置 `npm_config_build_from_source=true`，不再触发 canvas GitHub 预编译包下载路径。
- [ ] SSR npm 安装使用 `/root/.npm` BuildKit cache mount。
- [ ] Jenkins “构建 Docker 镜像”阶段存在不超过 20 分钟的 declarative stage timeout。
- [ ] 新增的构建契约测试通过，并能在上述任一约束被移除时失败。
- [ ] Dockerfile/Jenkinsfile 语法检查通过；条件允许时完成 SSR 镜像层或等价容器构建验证。
- [ ] 任务记录包含根因、修改和验证结果，未来会话无需重新猜测。

## Out Of Scope

- 更换 Jenkins、Docker、BuildKit 或 npm registry 基础设施。
- 搭建内部 GitHub Release 镜像或制品代理。
- 升级 AntV、Node.js、canvas 或其他 SSR 业务依赖的大版本。
- 修改当前正在运行的 Jenkins #83；部署和重新触发构建在代码合入后单独执行。
