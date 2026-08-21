function Resolve-SharedRuntimeRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceRoot
    )

    $workspaceRuntime = Join-Path $WorkspaceRoot ".codex-runtime"
    try {
        $commonDirOutput = & git -C $WorkspaceRoot rev-parse --path-format=absolute --git-common-dir 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $workspaceRuntime
        }

        $commonDirText = [string]($commonDirOutput | Select-Object -First 1)
        if ([string]::IsNullOrWhiteSpace($commonDirText)) {
            return $workspaceRuntime
        }

        $commonDir = [System.IO.Path]::GetFullPath($commonDirText.Trim())
        if ((Split-Path -Leaf $commonDir) -ne ".git") {
            return $workspaceRuntime
        }

        $primaryCheckout = Split-Path -Parent $commonDir
        if (-not (Test-Path -LiteralPath (Join-Path $primaryCheckout ".git"))) {
            return $workspaceRuntime
        }
        return Join-Path $primaryCheckout ".codex-runtime"
    } catch {
        return $workspaceRuntime
    }
}
