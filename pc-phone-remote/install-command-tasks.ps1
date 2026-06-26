$ErrorActionPreference = "Stop"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$tasks = @(
    @{
        Name = "PC Phone Remote - Lock"
        Execute = "rundll32.exe"
        Argument = "user32.dll,LockWorkStation"
        Description = "Locks the current Windows session for PC Phone Remote."
    },
    @{
        Name = "PC Phone Remote - Sleep"
        Execute = "powershell.exe"
        Argument = "-NoProfile -ExecutionPolicy Bypass -Command `"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', `$false, `$false)`""
        Description = "Puts the PC to sleep for PC Phone Remote."
    },
    @{
        Name = "PC Phone Remote - Restart"
        Execute = "shutdown.exe"
        Argument = "/r /t 0"
        Description = "Restarts the PC for PC Phone Remote."
    },
    @{
        Name = "PC Phone Remote - Shutdown"
        Execute = "shutdown.exe"
        Argument = "/s /t 0"
        Description = "Shuts down the PC for PC Phone Remote."
    }
)

foreach ($task in $tasks) {
    $action = New-ScheduledTaskAction -Execute $task.Execute -Argument $task.Argument
    Register-ScheduledTask `
        -TaskName $task.Name `
        -Action $action `
        -Principal $principal `
        -Settings $settings `
        -Description $task.Description `
        -Force | Out-Null
}

Write-Host "PC Phone Remote command tasks installed."
