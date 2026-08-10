# 修复 PR Typos 扫描范围

## Goal

修正 Typos CI 的扫描边界，避免将 `outputs/` 下的原始业务样本和生成产物当作源码拼写错误，同时继续检查实际代码、配置与文档。

## Background

- PR #4 的 Typos Check 失败项来自 `outputs/event-field-source-analysis/raw_samples.json` 等原始数据。
- 目标分支 `release/release_2.0.0` 最近多次 Typos Check 也因同类基线问题失败。
- Gitee 同步失败是 `GITEE_PRIVATE_KEY`、`GITEE_TOKEN` 未注入，不属于本任务可通过代码修复的范围。

## Requirements

- 在 `.typos.toml` 的文件排除规则中加入 `outputs`。
- 不修改 `outputs/` 中的原始样本、业务字段或生成文件。
- 不通过逐词白名单掩盖真实源码拼写错误。
- 使用与 GitHub Action 相同的 Typos 检查验证配置。

## Out of Scope

- 修改 Gitee 凭据、仓库 Secrets 或禁用同步工作流。
- 修正原始业务事件名、字段名和用户数据中的拼写。
- 修改知识库或 RAG 产品行为。

## Acceptance Criteria

- [ ] Typos 检查不再扫描 `outputs/`。
- [ ] 全仓 Typos 检查通过，或只剩与本次扫描范围无关且已明确记录的基线项。
- [ ] PR #4 新一轮 Typos Check 通过。
- [ ] 功能 worktree 保持无无关改动，修复提交已推送。

## Notes

- 该任务为单配置项 CI 修复，采用 PRD-only 轻量流程。
