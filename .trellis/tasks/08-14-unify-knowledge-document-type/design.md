# 技术设计

## Architecture

本次改动把知识管理的外部契约统一为普通 Markdown 文档，同时保留现有版本、知识块和对象引用基础设施。

```text
下载模板
  -> 统一 front matter + 内容分类模板
  -> 用户填写 UTF-8 Markdown
  -> 前端格式预检
  -> V2 草稿文件上传 API
  -> 后端权威格式校验
  -> Markdown 标题拆分为 Document blocks
  -> 现有草稿 CAS / 校验 / 发布 / 检索流程
```

## Product And API Boundary

- 前端 `KnowledgeBaseCreatePayload` 删除 `knowledge_type`，创建表单只提交名称、描述、知识范围和工作空间上下文。
- 后端 `CreateKnowledgeBaseRequest` 禁止额外字段，创建服务内部固定写入 `DOCUMENT`；客户端继续提交 `knowledge_type` 时返回 422，而不是忽略或替换。
- 列表和详情响应不再输出 `knowledge_type`，前端列表移除对应列。
- 数据库 `knowledge_base.knowledge_type` 和版本 payload 中的 `knowledge_type: DOCUMENT` 暂时作为固定存储判别值保留。它们不再参与用户选择或运行时类型分支，因此不需要新增破坏性迁移。

## Document Model Simplification

- 前端 payload 类型和编辑器只保留 `DocumentPayload`，默认 payload 不再接受类型参数。
- 删除业务术语、事件参数、JSON 字段三类专用编辑入口及仅由它们使用的组件/类型分支。
- 后端 payload 入口只解析 `DocumentPayload`；标准化、校验、对象引用投影、结构化上下文和发布只处理文档字段。
- 普通文档已有的 `object_references` 继续承担 TABLE / FIELD / JSON_PATH 等显式对象绑定和权限投影，不从模板标题猜测对象。

## Markdown Template Contract

每个模板文件以以下 front matter 开头：

```yaml
---
template_type: knowledge_document
template_version: 1
---
```

随后必须满足：

- UTF-8 或 UTF-8 BOM 编码，不允许替换字符解码。
- 扩展名为 `.md` 或 `.markdown`。
- front matter 是 YAML 映射，类型和版本严格匹配；未知版本不自动兼容。
- 正文第一个有效 Markdown 标题为非空 H1。
- 至少包含一个非空 H2 和一段有效正文。
- Markdown 围栏代码块成对闭合。
- 不根据文件名、模板中文标题或模板分类推断合法性。

前端使用 `yaml` 包解析 front matter，后端使用现有 PyYAML `safe_load`。两端对相同 good/base/bad fixtures 运行契约测试，固定字段名、版本和错误分类。

## Validation And Error Contract

- 前端选择文件后先读取文本并校验；失败时清空本次选择，显示 `格式错误：请使用下载的 Markdown 模板上传。`，不调用创建或替换 API。
- 后端在暂存文件写入后、草稿 CAS 保存前校验。失败返回 422、错误码 `KNOWLEDGE_TEMPLATE_FORMAT_INVALID`，消息以 `格式错误` 开头，并删除暂存文件。
- 非 Markdown 扩展名统一归入同一格式错误类别，建议文案明确仅支持 `.md / .markdown`。
- 校验失败不改变 version payload、source file、revision 或知识块结构；通过后才剥离 front matter，并将 Markdown 正文转换为 blocks。front matter 不进入检索内容。

## Compatibility And Removal Scope

- 当前目标数据库不存在非 `DOCUMENT` 知识记录，因此无需业务数据转换。
- 不提供对旧无标记 Markdown、Word、Excel 或旧结构化类型创建请求的静默兼容；用户需重新下载模板。
- 已存在的普通文档版本继续可编辑、发布和检索。其历史源文件下载不受新上传限制影响。
- Legacy/V2 共享的上传扩展名收紧为 Markdown，避免从旧入口绕过格式约束。

## Rollback

- 前端回滚可恢复类型列、选择器和旧上传扩展名。
- 后端回滚可恢复多类型 adapter 与 Office 解析，不涉及数据库回滚或数据重写。
- 新 front matter 对 Markdown 渲染无副作用；回滚后仍会作为普通 Markdown 元数据保留在源文件中。
