import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "start-local-force.ps1"
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="Requires Windows PowerShell")


def run_powershell(code):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", code],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=20,
    )


def load_function(name):
    path = str(SCRIPT).replace("'", "''")
    return f"""
    $ErrorActionPreference = 'Stop'
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$tokens, [ref]$errors)
    if ($errors.Count) {{ throw ($errors | Out-String) }}
    $definition = $ast.Find({{ param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq '{name}'
    }}, $true)
    Invoke-Expression $definition.Extent.Text
    """


def test_force_stop_only_kills_unique_fixed_port_listeners():
    result = run_powershell(load_function("Stop-LocalListeners") + r"""
    $script:calls = 0
    $script:stopped = @()
    function Get-NetTCPConnection {
        param($LocalPort, $State, $ErrorAction)
        if (($LocalPort -join ',') -ne '5173,8000,8001' -or $State -ne 'Listen') { throw 'Wrong scope' }
        $script:calls++
        if ($script:calls -eq 1) {
            [pscustomobject]@{ LocalPort=5173; OwningProcess=111 }
            [pscustomobject]@{ LocalPort=8000; OwningProcess=222 }
            [pscustomobject]@{ LocalPort=8001; OwningProcess=222 }
        }
    }
    function Get-Process { param($Id, $ErrorAction) [pscustomobject]@{ Id=$Id } }
    function Stop-Process {
        param([Parameter(ValueFromPipeline)]$InputObject, [switch]$Force)
        process {
            if (-not $Force) { throw 'Expected force stop' }
            $script:stopped += $InputObject.Id
        }
    }
    Stop-LocalListeners
    if (($script:stopped -join ',') -ne '111,222') { throw 'Wrong PIDs or duplicate stop' }
    if ($script:calls -lt 2) { throw 'Release was not checked' }
    """)
    assert result.returncode == 0, result.stdout + result.stderr


def test_force_stop_fails_when_port_is_reoccupied():
    result = run_powershell(load_function("Stop-LocalListeners") + r"""
    $script:clock = [datetime]'2026-01-01'
    function Get-Date { $script:clock = $script:clock.AddSeconds(11); $script:clock }
    function Start-Sleep { param($Milliseconds) }
    function Get-NetTCPConnection { [pscustomobject]@{ LocalPort=5173; OwningProcess=111 } }
    function Get-Process { [pscustomobject]@{ Id=111 } }
    function Stop-Process { param([Parameter(ValueFromPipeline)]$InputObject, [switch]$Force) }
    try { Stop-LocalListeners } catch {
        if ($_.Exception.Message -like '*still occupied*') { exit 0 }
        throw
    }
    throw 'An occupied port was treated as released'
    """)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("failed_command", ["fetch", "pull"])
def test_git_failure_preserves_existing_services(failed_command):
    path = str(SCRIPT).replace("'", "''")
    root = str(SCRIPT.parent.parent).replace("'", "''")
    result = run_powershell(f"""
    function Get-Command {{ }}
    function Test-Path {{ $true }}
    function git {{
        $global:LASTEXITCODE = 0
        switch ($args[0]) {{
            'rev-parse' {{ '{root}' }}
            'branch' {{ 'test-branch' }}
            '{failed_command}' {{ $global:LASTEXITCODE = 1 }}
        }}
    }}
    function Get-NetTCPConnection {{ throw 'UNEXPECTED_PORT_ACCESS' }}
    function Stop-Process {{ throw 'UNEXPECTED_PROCESS_STOP' }}
    & '{path}'
    """)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert f"Git {failed_command} failed" in output
    assert "UNEXPECTED_" not in output


def test_http_server_error_does_not_pass_readiness():
    result = run_powershell(load_function("Wait-LocalHttp") + r"""
    $script:clock = [datetime]'2026-01-01'
    function Get-Date { $script:clock = $script:clock.AddSeconds(91); $script:clock }
    function Start-Sleep { param($Milliseconds) }
    function Invoke-WebRequest { [pscustomobject]@{ StatusCode=500 } }
    try { Wait-LocalHttp -Url 'http://127.0.0.1:5173/' -AcceptedStatus @(200) } catch {
        if ($_.Exception.Message -like '*last HTTP status=500*') { exit 0 }
        throw
    }
    throw 'HTTP 500 was treated as ready'
    """)
    assert result.returncode == 0, result.stdout + result.stderr
