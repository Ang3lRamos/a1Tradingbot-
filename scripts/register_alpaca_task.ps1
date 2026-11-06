# Registra la tarea programada "mt5bot-alpaca" (bot RSI2 sobre ETF en la cuenta de práctica de Alpaca, config\alpaca_rsi2.toml) y la arranca.
# Igual que la tarea "mt5bot": corre al iniciar sesión (2 minutos después), sin límite de tiempo, también con batería.
# Para quitarla: Unregister-ScheduledTask -TaskName mt5bot-alpaca

$launcher = Join-Path $PSScriptRoot "start_bot.ps1"
$user = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -Config config\alpaca_rsi2.toml"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = "PT2M"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "mt5bot-alpaca" -Description "Bot RSI2 en ETF (config\alpaca_rsi2.toml) en live (paper de Alpaca) con reinicio automatico" `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
Start-ScheduledTask -TaskName "mt5bot-alpaca"
Write-Host "Tarea mt5bot-alpaca registrada y arrancada."
