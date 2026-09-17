# AI 看板问题题库

本目录收录 7 个工作空间的 AI 看板问题题库，删除 52 道 ROI 相关问题后共 648 题。题目用于 Smart Q&A / AI 看板顺序测试，不是生产环境的推荐问题种子数据。

| 文件 | 工作空间 | tenant_id | datasource_id | 推荐看板数 | 题数 | 格式 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `gig-ai-dashboard-100-questions-20260817.json` | gig | `7493272549510352896` | 12 | 9 | 90 | 可审计版 |
| `unicorn-ai-dashboard-100-questions-20260817.json` | unicorn | `7493583885482070016` | 9 | 9 | 90 | 可审计版 |
| `j2000-ai-dashboard-100-questions-20260817.json` | j2000 | `7493583991958671360` | 11 | 9 | 90 | 可审计版 |
| `lds-ai-dashboard-100-questions-20260817.json` | lds | `7493272675721154560` | 10 | 9 | 90 | 可审计版 |
| `flam-ai-dashboard-100-questions-2026-08-02.json` | flam | `7477202383789887488` | 3 | 13 | 95 | 旧版 |
| `xiuxian-ai-dashboard-100-questions-2026-08-02.json` | 修仙 | `7482727237662281728` | 6 | 9 | 95 | 旧版 |
| `sample-workspace-ai-dashboard-100-questions-20260811.json` | 示例工作空间 | `7473600346187632640` | 1 | 13 | 98 | 旧版 |

可审计版题库保留 9 个推荐看板各 10 题。每题保存工作空间、tenant、数据源、推荐看板、来源图表、时间范围和预期答案类型，并保留 18 题抽样标记。每套均为 90 个唯一问题。

旧版题库保留原始产物格式，剩余题目均唯一、可独立提交，但题目记录本身没有来源图表和抽样标记；其 tenant 归属在本文件和校验清单中显式声明。

ROI 相关问题包含 ROI 看板下的全部题目，以及其他看板中明确涉及 ROI 的题目。删除后保留原始题目 ID，不重新编号、不补题；文件名中的 `100-questions` 保留为历史产物名称，不代表当前题数。校验清单显式记录删除的 ID。

运行完整性校验：

```powershell
python docs/question-banks/ai-dashboard/2026-08-17/validate_question_banks.py
```
