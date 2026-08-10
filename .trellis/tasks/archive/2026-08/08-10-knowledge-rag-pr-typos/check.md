# Typos CI 检查记录

## 根因

- Typos 扫描了 `outputs/` 下的原始业务样本和生成产物，目标分支也持续因此失败。
- 排除 `outputs/` 后剩余项均为目标分支已有的业务标识：真实事件名 `PayBuyRetBenifit`、SQL 别名 `hero_star_starup`、指标缩写 `yoy`，以及凭据随机串。
- Gitee 同步失败是仓库 Secrets 为空，日志显示 401 和 SSH 公钥认证失败，不能通过本分支代码修复。

## 修复

- 将 `outputs` 加入 `files.extend-exclude`。
- 仅对白名单业务标识使用 `default.extend-identifiers`。
- 仅按 `api_key=...` 凭据模式使用 `default.extend-ignore-re`。
- 未修改原始样本或真实业务标识。

## 验证

- Typos CLI：`typos-cli 1.49.0`。
- 全仓检查：通过。
- 检查文件数：1433。
- `outputs/` 被检查文件数：0。
- `git diff --check`：通过。
