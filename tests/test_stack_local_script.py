import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
STACK_SCRIPT = REPO_ROOT / "tools" / "stack-local.ps1"
BACKEND_SCRIPT = REPO_ROOT / "tools" / "backend-local.ps1"
WORKER_SCRIPT = REPO_ROOT / "tools" / "worker-local.ps1"


def _powershell() -> str:
    powershell = shutil.which("pwsh")
    if not powershell:
        pytest.skip("未安装 PowerShell 7")
    return powershell


def _run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_powershell(), "-NoProfile", "-File", str(script), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def _function_body(content: str, name: str) -> str:
    marker = f"function {name}"
    assert marker in content
    return content.split(marker, 1)[1].split("\nfunction ", 1)[0]


@pytest.mark.skipif(sys.platform != "win32", reason="本地启动脚本只在 Windows 上运行")
def test_stack_status_does_not_require_optional_e_drive():
    """没有可选 E 盘时，状态检查仍应正常执行。"""
    if Path("E:/").exists():
        pytest.skip("当前机器存在 E 盘，无法复现可选路径缺失场景")

    result = _run_script(
        STACK_SCRIPT,
            "-Action",
            "status",
            "-SkipDatabase",
            "-SkipRedis",
            "-SkipNginx",
            "-SkipWorker",
    )

    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def test_stack_restart_forces_unmanaged_backend_ports_to_stop():
    """父级重启必须接管没有 PID 文件的旧 API/MCP 端口进程。"""
    content = STACK_SCRIPT.read_text(encoding="utf-8")

    assert '$Action -eq "restart"' in content
    assert "$backendParams.ForcePortStop = $true" in content


@pytest.mark.skipif(sys.platform != "win32", reason="本地启动脚本只在 Windows 上运行")
@pytest.mark.parametrize(
    ("script", "extra_arguments"),
    [
        (STACK_SCRIPT, ("-SkipDatabase", "-SkipRedis", "-SkipNginx")),
        (BACKEND_SCRIPT, ()),
        (WORKER_SCRIPT, ()),
    ],
)
def test_local_scripts_reject_production_default_queue(script, extra_arguments):
    result = _run_script(
        script,
        "-Action",
        "status",
        "-QueueName",
        "default",
        *extra_arguments,
    )

    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode != 0
    assert "default" in output


@pytest.mark.skipif(sys.platform != "win32", reason="本地启动脚本只在 Windows 上运行")
def test_backend_stop_does_not_kill_stale_pid_or_unrelated_port_owner():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    runtime = REPO_ROOT / ".codex-runtime" / "backend-replicas"
    runtime.mkdir(parents=True, exist_ok=True)
    pid_file = runtime / f"backend-{port}.pid"

    sleeper = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with socket.socket() as client:
                if client.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:
            pytest.fail("临时 HTTP 服务未监听")

        pid_file.write_text(str(sleeper.pid), encoding="ascii")
        result = _run_script(
            BACKEND_SCRIPT,
            "-Action",
            "stop",
            "-BackendPorts",
            str(port),
            "-QueueName",
            "local-test-chat-bi",
            "-ForcePortStop",
        )

        output = (result.stdout or "") + (result.stderr or "")
        assert result.returncode != 0, output
        assert "Refusing to stop unrelated process" in output
        assert sleeper.poll() is None, "陈旧 PID 指向的无关进程被误杀"
        assert server.poll() is None, "占用测试端口的无关进程被误杀"
    finally:
        for process in (server, sleeper):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        pid_file.unlink(missing_ok=True)


def test_backend_defaults_to_lan_listen_address():
    content = BACKEND_SCRIPT.read_text(encoding="utf-8")

    assert '[string]$HostAddress = "0.0.0.0"' in content


def test_backend_waits_for_mcp_listener_before_recording_pid():
    content = BACKEND_SCRIPT.read_text(encoding="utf-8")

    assert "function Wait-PortOwner" in content
    assert "$owner = Wait-PortOwner -Port $Port" in content


def test_backend_process_validation_is_scoped_to_workspace_and_launcher():
    content = BACKEND_SCRIPT.read_text(encoding="utf-8")

    assert "function Test-WorkspaceUvicornProcess" in content
    assert "function Test-ListenerOwnedByLauncher" in content
    assert "ParentProcessId" in content
    assert "$pythonExe" in content


def test_worker_process_validation_is_scoped_to_workspace():
    content = WORKER_SCRIPT.read_text(encoding="utf-8")

    assert 'Contains($pythonExe)' in content
    assert 'Contains("scripts.task_worker")' in content


@pytest.mark.parametrize(
    ("script", "environment_function"),
    [
        (BACKEND_SCRIPT, "Set-BackendEnvironment"),
        (WORKER_SCRIPT, "Set-WorkerEnvironment"),
    ],
)
def test_local_process_environment_pins_llm_timeout_contract(
    script: Path, environment_function: str
):
    content = script.read_text(encoding="utf-8")
    body = _function_body(content, environment_function)

    assert '$env:LLM_REQUEST_TIMEOUT = "120"' in body
    assert '$env:LLM_TASK_MAX_WAIT_SECONDS = "900"' in body
    assert '$env:LLM_MAX_RETRIES = "1"' in body


@pytest.mark.parametrize(
    ("script", "environment_function"),
    [
        (BACKEND_SCRIPT, "Set-BackendEnvironment"),
        (WORKER_SCRIPT, "Set-WorkerEnvironment"),
    ],
)
def test_local_process_environment_exposes_knowledge_rollout_switches(
    script: Path, environment_function: str
):
    content = script.read_text(encoding="utf-8")
    body = _function_body(content, environment_function)

    assert "$EnableKnowledgeManagementV2" in content
    assert "$DisableKnowledgeManagementV2" in content
    assert "$EnableKnowledgeRuntimeContext" in content
    assert "$DisableKnowledgeRuntimeContext" in content
    assert "$EnableKnowledgeRetrieval" in content
    assert "$DisableKnowledgeRetrieval" in content
    assert "$env:KNOWLEDGE_MANAGEMENT_V2_ENABLED" in body
    assert "$env:KNOWLEDGE_RUNTIME_CONTEXT_ENABLED" in body
    assert "$env:KNOWLEDGE_RETRIEVAL_ENABLED" in body
    assert (
        'if ($DisableKnowledgeManagementV2) { "false" } else { "true" }'
        in body
    )
    assert (
        'if ($DisableKnowledgeRuntimeContext) { "false" } else { "true" }'
        in body
    )
    assert (
        'if ($DisableKnowledgeRetrieval) { "false" } else { "true" }'
        in body
    )


def test_stack_requires_worker_when_redis_is_unreachable():
    content = STACK_SCRIPT.read_text(encoding="utf-8")
    body = _function_body(content, "Start-Workers")

    assert "throw" in body
    assert "Task worker requires Redis" in body
    assert "Write-Warning" not in body


def test_stack_status_delegates_worker_validation_to_worker_script():
    content = STACK_SCRIPT.read_text(encoding="utf-8")
    body = _function_body(content, "Show-StackStatus")

    assert (
        "& $workerScript -Action status -Workers $Workers "
        "-RedisHost $RedisHost -RedisPort $RedisPort -QueueName $QueueName"
    ) in body


def test_stack_passes_the_same_queue_to_backend_and_worker():
    content = STACK_SCRIPT.read_text(encoding="utf-8")
    backend_body = _function_body(content, "Start-Backend")
    worker_body = _function_body(content, "Start-Workers")

    assert 'QueueName = $QueueName' in backend_body
    assert 'QueueName = $QueueName' in worker_body
    assert 'QueueName = "default"' not in backend_body
    assert '-QueueName default' not in worker_body


def test_stack_propagates_knowledge_rollout_switches_to_backend_and_worker():
    content = STACK_SCRIPT.read_text(encoding="utf-8")
    backend_body = _function_body(content, "Start-Backend")
    worker_body = _function_body(content, "Start-Workers")

    for option in (
        "EnableKnowledgeManagementV2",
        "EnableKnowledgeRuntimeContext",
        "EnableKnowledgeRetrieval",
    ):
        assert f"if (${option})" in backend_body
        assert f"$backendParams.{option} = $true" in backend_body
        assert f"if (${option})" in worker_body
        assert f"$workerParams.{option} = $true" in worker_body

    for option in (
        "DisableKnowledgeManagementV2",
        "DisableKnowledgeRuntimeContext",
        "DisableKnowledgeRetrieval",
    ):
        assert f"if (${option})" in backend_body
        assert f"$backendParams.{option} = $true" in backend_body
        assert f"if (${option})" in worker_body
        assert f"$workerParams.{option} = $true" in worker_body


@pytest.mark.parametrize("script", [STACK_SCRIPT, BACKEND_SCRIPT, WORKER_SCRIPT])
@pytest.mark.parametrize(
    ("enable_option", "disable_option", "label"),
    [
        (
            "EnableKnowledgeManagementV2",
            "DisableKnowledgeManagementV2",
            "Knowledge management V2",
        ),
        (
            "EnableKnowledgeRuntimeContext",
            "DisableKnowledgeRuntimeContext",
            "Knowledge runtime context",
        ),
        (
            "EnableKnowledgeRetrieval",
            "DisableKnowledgeRetrieval",
            "Knowledge retrieval",
        ),
    ],
)
def test_local_scripts_reject_conflicting_knowledge_switches(
    script: Path, enable_option: str, disable_option: str, label: str
):
    content = script.read_text(encoding="utf-8")

    assert f"${enable_option} -and ${disable_option}" in content
    assert f"{label} cannot be enabled and disabled at the same time" in content


@pytest.mark.skipif(sys.platform != "win32", reason="本地启动脚本只在 Windows 上运行")
@pytest.mark.parametrize("script", [STACK_SCRIPT, BACKEND_SCRIPT, WORKER_SCRIPT])
@pytest.mark.parametrize(
    ("enable_option", "disable_option", "label"),
    [
        (
            "EnableKnowledgeManagementV2",
            "DisableKnowledgeManagementV2",
            "Knowledge management V2",
        ),
        (
            "EnableKnowledgeRuntimeContext",
            "DisableKnowledgeRuntimeContext",
            "Knowledge runtime context",
        ),
        (
            "EnableKnowledgeRetrieval",
            "DisableKnowledgeRetrieval",
            "Knowledge retrieval",
        ),
    ],
)
def test_local_scripts_fail_fast_for_conflicting_knowledge_switches(
    script: Path, enable_option: str, disable_option: str, label: str
):
    result = _run_script(
        script,
        f"-{enable_option}",
        f"-{disable_option}",
    )

    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode != 0
    assert f"{label} cannot be enabled and disabled at the same time" in output


def test_worker_status_rejects_mismatched_managed_queue():
    content = WORKER_SCRIPT.read_text(encoding="utf-8")
    body = _function_body(content, "Show-Status")

    assert "[string]$managedQueue -ne $QueueName" in body
    assert "throw" in body


def test_worker_start_waits_for_stability_and_cleans_failed_metadata():
    content = WORKER_SCRIPT.read_text(encoding="utf-8")
    body = _function_body(content, "Start-Worker")

    assert "Start-Sleep -Milliseconds" in body
    assert "$process.Refresh()" in body
    assert "$process.HasExited" in body
    assert "Remove-Item -LiteralPath $pidFile, $queueFile" in body
    assert "throw" in body
