# 平台 DataSkills 移除显式时区说明

## 目标

移除平台 DataSkills 输出中的 `UTC+8`、`Asia/Shanghai` 和同义的实时业务时区说明，避免 Smart Q&A 将该规则作为回答步骤展示。

## 范围

- 更新 flam/first_zombie DataSkill 种子中的显式时区说明及跨 Skill 引用。
- 同步更新系统库中对应的平台 DataSkills。
- 保留 SQL 中已有的时间转换表达式，避免改变实时统计结果。
- 不修改其他数据源的时区配置或平台通用时间能力。

## 验证

- 种子回归测试确认平台 DataSkill prompt 不包含 `UTC+8`、`Asia/Shanghai` 或“业务时区”说明。
- 同步后回读系统库，确认对应 DataSkill prompt 与种子一致。
