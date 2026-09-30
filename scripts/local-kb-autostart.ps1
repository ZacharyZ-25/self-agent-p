[CmdletBinding()]
param(
    [ValidateSet('Install', 'Start', 'Stop', 'Status', 'Remove')]
    [string]$Action = 'Status'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $root 'knowledge-data/personal-kb'
$taskName = 'Local RAG Knowledge Base'
$pythonw = Join-Path $root 'backend/.venv/Scripts/pythonw.exe'
$entrypoint = Join-Path $PSScriptRoot 'local-kb-background.py'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

switch ($Action) {
    'Install' {
        if (-not (Test-Path -LiteralPath (Join-Path $data 'admin-password.dpapi') -PathType Leaf)) {
            throw '先运行 backend/.venv/Scripts/python.exe scripts/local-kb-password.py set，设置一次本地管理密码。'
        }
        if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
            throw '找不到本地 Python 依赖，请先安装 backend/.venv。'
        }
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $taskAction = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + $entrypoint + '"') -WorkingDirectory $root
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Write-Output '已配置当前用户登录后后台启动；不会弹出 CMD 窗口。'
    }
    'Start' {
        if (-not $task) { throw '尚未配置开机自启。' }
        Start-ScheduledTask -TaskName $taskName
        Write-Output '已请求后台启动。管理页：http://127.0.0.1:8000/admin/kb；访客接口：http://127.0.0.1:8003/readyz。'
    }
    'Stop' {
        New-Item -ItemType Directory -Force -Path $data | Out-Null
        New-Item -ItemType File -Force -Path (Join-Path $data 'stop.request') | Out-Null
        Write-Output '已请求后台服务退出；请稍后查看状态。'
    }
    'Status' {
        if ($task) { Write-Output ("开机任务：" + $task.State) } else { Write-Output '开机任务：未配置' }
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/admin/kb/session' -TimeoutSec 2 -UseBasicParsing
            Write-Output ("本地管理页：" + $response.StatusCode)
        } catch { Write-Output '本地管理页：未运行' }
        try {
            $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8003/readyz' -TimeoutSec 2
            Write-Output ("访客问答接口：" + $response.status)
        } catch { Write-Output '访客问答接口：未运行' }
        Write-Output ("日志：" + (Join-Path $data 'logs/launcher.log'))
    }
    'Remove' {
        if ($task) {
            New-Item -ItemType Directory -Force -Path $data | Out-Null
            New-Item -ItemType File -Force -Path (Join-Path $data 'stop.request') | Out-Null
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
        Write-Output '已取消开机自启；知识库资料未删除。'
    }
}
