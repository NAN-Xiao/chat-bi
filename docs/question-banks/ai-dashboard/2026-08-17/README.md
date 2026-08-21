# AI 看板问题题库

本目录收录 7 个工作空间的 AI 看板问题题库，共 700 题。题目用于 Smart Q&A / AI 看板顺序测试，不是生产环境的推荐问题种子数据。

| 文件 | 工作空间 | tenant_id | datasource_id | 推荐看板数 | 格式 |
| --- | --- | --- | ---: | ---: | --- |
| `gig-ai-dashboard-100-questions-20260817.json` | gig | `7493272549510352896` | 12 | 10 | 可审计版 |
| `unicorn-ai-dashboard-100-questions-20260817.json` | unicorn | `7493583885482070016` | 9 | 10 | 可审计版 |
| `j2000-ai-dashboard-100-questions-20260817.json` | j2000 | `7493583991958671360` | 11 | 10 | 可审计版 |
| `lds-ai-dashboard-100-questions-20260817.json` | lds | `7493272675721154560` | 10 | 10 | 可审计版 |
| `flam-ai-dashboard-100-questions-2026-08-02.json` | flam | `7477202383789887488` | 3 | 14 | 旧版 |
| `xiuxian-ai-dashboard-100-questions-2026-08-02.json` | 修仙 | `7482727237662281728` | 6 | 10 | 旧版 |
| `sample-workspace-ai-dashboard-100-questions-20260811.json` | 示例工作空间 | `7473600346187632640` | 1 | 13 | 旧版 |

可审计版题库由 10 个推荐看板各生成 10 题。每题保存工作空间、tenant、数据源、推荐看板、来源图表、时间范围和预期答案类型，并保留 20 题抽样标记。提交前已修正每套题库内部的 4 组重复题面，因此每套均为 100 个唯一问题。

旧版题库保留原始产物格式，每套同样有 100 个唯一、可独立提交的问题，但题目记录本身没有来源图表和 20 题抽样标记；其 tenant 归属在本文件和校验清单中显式声明。

运行完整性校验：

```powershell
python docs/question-banks/ai-dashboard/2026-08-17/validate_question_banks.py
```
