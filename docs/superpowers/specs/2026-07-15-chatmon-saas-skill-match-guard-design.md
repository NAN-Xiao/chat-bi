# ChatMon SaaS Skill 误匹配修复设计

## 背景

平台级 `SaaS ChatMon MCP 告警搜索 Skill` 把“查看”等通用动作词配置为独立触发条件，导致“查看近半月朱果的变化情况”这类普通 BI 问题误命中 ChatMon MCP。未绑定第三方 MCP 的工作空间随后收到“当前工作空间未绑定第三方 MCP 数据源”的错误，普通 SQL 问答被提前中断。

## 目标

- 普通 BI 问题不能仅凭“查看、列表、趋势、数量、明细”等通用词命中 ChatMon Skill。
- 明确包含“告警、舆情、风险反馈、ChatMon、告警 ID”等领域语义的问题仍可命中对应 Skill。
- 保持当前通用 SaaS Skill 匹配算法、MCP 权限校验和未绑定提示不变。

## 方案

只修改 `tools/seed_saas_mcp_data_skills.py` 中四条 ChatMon Skill 的 `match.keywords_any`：

- 删除可单独触发的通用动作或展示词。
- 保留能够表明 ChatMon 领域意图的词，如“告警”“舆情”“风险反馈”“ChatMon”“告警ID”。
- “过滤项”“证据”“原文”等动作含义继续保留在 `intent` 中参与评分，但必须先通过领域词条件。

不修改 `find_matching_executable_saas_skill`。该函数是平台通用能力，当前问题来自一组全局 Skill 的配置过宽，配置层修复的影响范围更小。

## 数据流

1. 自动 Skills 检索得到平台级 ChatMon Skill。
2. `_required_terms_match` 先检查问题是否含 ChatMon 领域词。
3. 不含领域词时跳过 ChatMon Skill，Smart Q&A 继续普通数据源 SQL 流程。
4. 含领域词时继续现有评分、参数解析、MCP 绑定与权限校验流程。

## 错误处理

用户明确询问 ChatMon，但工作空间未绑定第三方 MCP 时，继续返回现有显式提示；不增加静默回退。普通 BI 问题不再进入 MCP 执行路径，因此不会看到无关的 MCP 绑定错误。

## 测试

- 回归用例：“查看近半月朱果的变化情况”不命中任何 ChatMon SaaS Skill。
- 正向用例：“查看最近 7 天告警列表”命中 `saas_chatmon_alert_search`。
- 正向用例：“查看最近 7 天舆情趋势”命中 `saas_chatmon_alert_count`。
- 运行现有 `tests/test_saas_skill_execution.py`，确认通用 SaaS Skill 行为不回归。

## 发布

代码验证通过后运行幂等种子脚本，将四条平台级 Data Skill 更新到系统数据库。更新后使用当前数据库配置重新执行匹配函数，确认普通 BI 问题不命中、明确 ChatMon 问题仍命中。
