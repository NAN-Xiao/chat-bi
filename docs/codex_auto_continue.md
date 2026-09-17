# Codex 429 / 503 自动继续

`tools/codex_auto_continue.py` 是独立 Python 标准库脚本，不依赖 ChatBI 服务或模型 API Key。

脚本连接**现有 Codex app-server 的控制 socket**，读取指定会话最后一轮的结构化状态。只有会话处于 idle/systemError，且最后一轮明确 failed、错误中包含 HTTP 429 或 503 时才触发。默认等待 60 秒，再次核对状态后通过 `turn/start` 发送“继续”。后续等待时间指数增长，最长 900 秒。

不会在 Codex 内部自动重试、等待审批或等待用户输入时发送消息；正常完成、用户中断以及单纯在聊天内容中提到 429/503 都不会触发。脚本不批准工具操作。读取和发送之间存在很短的并发窗口；协议没有“仅当上一轮仍然失败才启动”的原子条件，用户同时手动继续时应先停止监听器。

## 使用

从仓库根目录先验证连接（不发送消息）：

```powershell
& .\backend\.venv\Scripts\python.exe .\tools\codex_auto_continue.py --thread <会话UUID> --check
```

验证连接和会话状态后，运行监听：

```powershell
& .\backend\.venv\Scripts\python.exe .\tools\codex_auto_continue.py --thread <会话UUID>
```

也可使用其他 Python 3.10+。`--socket <路径>` 可指定**已存在且属于目标 Codex 实例**的控制 socket。脚本不创建新的 app-server；新建服务不能保证控制桌面 App 正在运行的会话。

默认每 10 秒检查一次，最多发送 3 次；可用 `--interval`、`--cooldown`、`--max-retries` 调整。Ctrl+C 停止。

状态保存在 `$CODEX_HOME/auto-continue/<会话UUID>.json`（默认 `~/.codex/auto-continue/`）。去重和累计次数跨脚本重启保留，单会话锁阻止重复启动。发送前落盘，所以即使发送结果不明确也不会自动重复提交。达到上限后须人工确认是否继续；需要重置时先停止监听器，再删除该会话的状态 JSON。

## 当前机器验证结果与限制

2026-09-17 在本机调用 `codex app-server proxy` 时，默认控制 socket 无法连接，返回 Windows socket 错误 10050。因此当前桌面会话的自动发送尚未打通，也没有启用后台监听。需目标桌面实例提供可连接的控制 socket 后再运行 `--check`；本脚本不能让没有暴露控制接口的桌面实例自动获得该接口。

协议行为依据：[官方 Codex App Server 文档](https://learn.chatgpt.com/docs/app-server)。本机已核对 `codex app-server proxy --help`。

验证：

```powershell
& .\backend\.venv\Scripts\python.exe -m unittest discover -s tools -p test_codex_auto_continue.py
```

测试覆盖错误格式、最后一轮判断、运行中/完成/中断排除、避免数字误判，以及持久化去重和上限。测试不向真实会话发送消息；真实发送仍需在控制接口可用后验证。
