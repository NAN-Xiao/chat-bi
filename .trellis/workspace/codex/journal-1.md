# Journal - codex (Part 1)

> AI development session journal
> Started: 2026-08-14

---



## Session 1: 修复知识块列表独立滚动

**Date**: 2026-08-14
**Task**: 修复知识块列表独立滚动
**Branch**: `codex/fix-knowledge-panel-scroll`

### Summary

在最新 2.0 基线上让知识块目录独立滚动，并保持右侧详情固定。

### Main Changes

- 桌面端知识块目录限制高度并独立纵向滚动
- 移动端保留横向滚动并关闭纵向滚动

### Git Commits

| Hash | Message |
|------|---------|
| `8da18554` | (see git log) |

### Testing

- [OK] 知识库文档编辑器布局测试 9 项通过
- [OK] 目标文件 ESLint 与前端生产构建通过

### Status

[OK] **Completed**


## Session 2: Fix knowledge publish embedding batch limit

**Date**: 2026-08-17
**Task**: Fix knowledge publish embedding batch limit
**Branch**: `codex/fix-knowledge-publish-queue`

### Summary

Set the shared embedding batch limit to 10, propagate it through deployment configuration, and verify successful publication on the .193 test environment.

### Git Commits

| Hash | Message |
|------|---------|
| `f8e21ac5` | (see git log) |

### Status

[OK] **Completed**


## Session 3: 修复知识块删除反馈

**Date**: 2026-08-21
**Task**: 修复知识块删除反馈
**Branch**: `codex/fix-knowledge-block-delete-feedback`

### Summary

知识块删除确认后提示保存草稿，补充回归测试并完成构建、定向 lint 与运行时验证。

### Git Commits

| Hash | Message |
|------|---------|
| `d8f80e92` | (see git log) |

### Status

[OK] **Completed**


## Session 4: 修复知识块删除确认框层级

**Date**: 2026-08-21
**Task**: 修复知识块删除确认框层级
**Branch**: `codex/fix-knowledge-block-delete-feedback`

### Summary

统一知识块编辑器弹层组件库，修复确认框被抽屉遮挡，并通过真实点击、成功提示、测试、Lint 和构建验证。

### Git Commits

| Hash | Message |
|------|---------|
| `9c0504e8` | (see git log) |

### Status

[OK] **Completed**


## Session 5: 修复知识源文件跨工作树下载

**Date**: 2026-08-21
**Task**: 修复知识源文件跨工作树下载
**Branch**: `codex/fix-knowledge-source-storage`

### Summary

统一 2.0.0 linked worktree 的本地文件型运行目录，解码 Blob 下载错误并完成上传、发布、下载真实验证。

### Git Commits

| Hash | Message |
|------|---------|
| `d84aecd6` | (see git log) |
| `bdf06abd` | (see git log) |

### Status

[OK] **Completed**


## Session 6: 修复登录后默认工作空间

**Date**: 2026-08-24
**Task**: 修复登录后默认工作空间
**Branch**: `codex/fix-workspace-default`

### Summary

恢复未指定工作空间时按主成员关系自动解析默认工作空间，补充回归测试并合并推送到 release/release_2.0.0。

### Git Commits

| Hash | Message |
|------|---------|
| `93bbf19f` | (see git log) |
| `5b67bb65` | (see git log) |

### Status

[OK] **Completed**
