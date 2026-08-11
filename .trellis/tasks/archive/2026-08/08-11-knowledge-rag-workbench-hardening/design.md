# 技术设计

## 1. 状态边界

知识库页面的管理模式必须来自服务端 capability。请求失败属于 `CAPABILITIES_UNAVAILABLE`，不能被解释为 `LEGACY`；只有服务端明确返回 `management_mode=LEGACY` 才进入旧版页面。

列表加载维护 `idle/loading/success/empty/error` 语义，避免把异常转换为空数组。

## 2. 检索数据流

`KnowledgeRetrievalResult.failure_type` 继续由检索服务产生，并在 `semantic_context` 中写入独立的 `retrieval_failure_type` 字段，同时保留安全中文 warnings。助手快照 sanitizer 允许该字段通过，引用组件展示可理解的索引不可用状态。

## 3. 引用展示

扩展 `KnowledgeCitation` 和 API/前端类型以携带通用来源元数据：知识库名称、源文件名、版本号、章节路径、引用内容和状态。字段均可为空，历史快照只显示已有信息；内部 `chunk_id` 仅用于稳定 key，不直接展示。

## 4. 非目标

本次不重写向量检索执行计划，不新增 pgvector 索引，不切换 V2 开关，不扩展 PDF/PPTX/OCR，不新增评测中心。它们作为后续任务记录。
