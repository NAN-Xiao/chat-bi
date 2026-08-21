# 修复知识块删除无反馈

## Goal

让普通文档编辑器中的知识块删除操作给出明确、可理解的反馈，同时保持当前“删除先改本地草稿，点击保存草稿后才落库”的产品语义。

## Requirements

- 删除确认成功后，立即显示“知识块已删除，请保存草稿”提示，说明知识块已从当前编辑草稿移除。

## Acceptance Criteria

- [x] 用户确认删除后，目录和计数立即反映删除结果，并看到“知识块已删除，请保存草稿”提示。
- [x] 用户取消确认或关闭对话框时，不改变知识块结构。
- [x] 只有一个知识块时点击删除，结构不变并看到已有警告。
- [x] 只读模式不提供删除入口。
- [x] 现有保存草稿流程仍负责落库和冲突处理；前端测试覆盖成功反馈及上述边界。

## Confirmed Facts

- `frontend/src/views/knowledge-base/editors/DocumentEditor.vue` 使用 `ElMessageBox.confirm` 确认删除。
- 删除确认后仅通过 `updateBlocks` 更新父组件的本地 payload，并不会直接调用后端。
- 删除确认后的成功路径没有 `ElMessage` 提示；取消/关闭确认框也静默返回。
- 普通文档至少保留一个知识块，当前已有警告提示。
- `KnowledgeBaseV2Panel.vue` 已通过 `saveDocumentDraft`/`saveDraft` 处理文档结构持久化与冲突反馈。

## Out Of Scope

- 不改变知识块删除的后端 API、版本冲突协议或保存草稿流程。
- 不将删除操作改为确认后立即提交服务端。
