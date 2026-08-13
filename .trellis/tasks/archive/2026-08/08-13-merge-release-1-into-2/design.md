# 合并设计

## Boundaries

- Git 历史变更限定在 `release/release_2.0.0` 新增一个 merge commit。
- 用户工作区修改独立于 merge commit，通过唯一命名的 stash 临时保存和恢复。
- 冲突处理限定为预检发现的文件及合并过程中 Git 实际报告的文件。

## Merge Flow

1. 记录当前 HEAD、工作区状态、未提交文件列表和 stash 基线。
2. `git stash push --include-untracked` 保存现场，并验证工作区干净。
3. 将本地 `release/release_1.0.0` fast-forward 到 `origin/release/release_1.0.0`，返回目标分支。
4. 执行 `git merge --no-ff release/release_1.0.0`，先保留未提交的 merge 状态。
5. 对每个冲突比较 base/ours/theirs 和双方相关提交，组合保留兼容逻辑。
6. 运行定向测试/校验；通过后创建中文 merge commit。
7. `git stash pop` 恢复用户现场。如恢复冲突，仅解决工作区冲突，不 amend merge commit。
8. 核验父提交、祖先关系、冲突状态和用户改动文件集合。

## Conflict Policy

- 默认以 2.0 当前架构和通用平台约束为主干，吸收 1.0 的缺陷修复意图。
- 对源分支中已被后续 revert 的功能，尊重源分支最终状态，不重新引入被撤销实现。
- 测试冲突与实现冲突同步处理，保留双方仍适用的回归覆盖。
- 数据技能和种子脚本保持幂等、数据源范围隔离和明细数据约束。

## Rollback

- merge commit 前若判断无法可靠解决，可执行 `git merge --abort`，再恢复 stash。
- merge commit 后若 stash 恢复失败，保留 stash 引用，先恢复到干净 merge 结果，再逐文件应用用户改动。
- 不使用 `git reset --hard`、`git checkout --` 等会丢失用户现场的命令。

## Risks

- 两分支分叉较大，自动合并文件也可能存在语义冲突；除定向测试外需检查关键自动合并差异。
- `frontend/src/router/index.ts` 同时存在用户修改和源分支修改，stash 恢复可能产生二次冲突。
- 全量测试可能耗时较长，优先覆盖冲突文件的相关测试并记录残余风险。
