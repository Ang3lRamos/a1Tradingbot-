# Arranca todo lo necesario para la prueba en demo y mantiene vivo un bot (una configuración).
# Lo lanzan las tareas programadas "mt5bot" (config\settings.toml) y "mt5bot-rsi2" (config\rsi2.toml)
# al iniciar sesión; también se puede correr a mano: .\scripts\start_bot.ps1 -Config config\rsi2.toml
# - Abre MT5 de GNT si no está abierto y espera a que conecte con Algo Trading activo.
# - Lanza keep_awake.ps1 para que el equipo y la pantalla no se suspendan.
# - Lanza el vigilante del panel (mt5bot panel --watch), que renueva ~\.mt5bot\panel.html cada pocos minutos.
# - Corre el bot en live y lo reinicia si se cae. Si existe el archivo STOP no lo reinicia:
#   el kill switch manda (detiene a todos los bots). Para volver a arrancar, borra STOP y corre este script.
param([string]$Config = "config\settings.toml")

$project  = Split-Path -Parent $PSScriptRoot
$python   = "$env:USERPROFILE\.venvs\mt5bot\Scripts\python.exe"
$terminal = "C:\Program Files\MetaTrader 5\terminal64.exe"
$logDir   = "$env:USERPROFILE\.mt5bot\logs"
$stopFile = Join-Path $project "STOP"
$botName  = [IO.Path]::GetFileNameWithoutExtension($Config)
$retrySeconds = 60
$panelMinutes = 5

New-Item -ItemType Directory -Force $logDir | Out-Null
Set-Location $project

function Write-Log([string]$message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$botName] $message"
    Write-Host $line
    Add-Content -Path (Join-Path $logDir "launcher.log") -Value $line -Encoding UTF8
}

function Test-ProcessRunning([string]$name, [string]$commandLinePattern) {
    $found = Get-CimInstance Win32_Process -Filter "Name='$name'" |
        Where-Object { $_.CommandLine -like $commandLinePattern }
    return [bool]$found
}

function Test-BotRunning {
    # Un bot sin --config usa config\settings.toml (así se lanzaba antes de existir el segundo bot).
    $bots = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*mt5bot.main*run*" }
    foreach ($bot in $bots) {
        $used = if ($bot.CommandLine -match '--config\s+"?([^"\s]+)') { $Matches[1] } else { "config\settings.toml" }
        if ([IO.Path]::GetFileName($used) -eq [IO.Path]::GetFileName($Config)) { return $true }
    }
    return $false
}

function Wait-Mt5Ready {
    # Conecta sin credenciales a la sesión abierta del terminal de GNT (por ruta: hay otro MT5 instalado)
    # y revisa conexión y Algo Trading.
    $check = "import sys, MetaTrader5 as m; ok = m.initialize(path=r'$terminal') and m.terminal_info().connected and m.terminal_info().trade_allowed; m.shutdown(); sys.exit(0 if ok else 1)"
    $attempt = 0
    while ($true) {
        & $python -c $check
        if ($LASTEXITCODE -eq 0) { return }
        if ($attempt % 5 -eq 0) {
            Write-Log "MT5 aun no esta listo (sin conexion o Algo Trading apagado); reintento cada $retrySeconds s"
        }
        $attempt++
        Start-Sleep -Seconds $retrySeconds
    }
}

if (Test-BotRunning) {
    Write-Log "ya hay un bot corriendo con $Config; no se lanza otro"
    exit 0
}
if (Test-Path $stopFile) {
    Write-Log "existe el archivo STOP: no se arranca. Borralo para volver a operar."
    exit 0
}

if (-not (Test-ProcessRunning "powershell.exe" "*keep_awake.ps1*")) {
    Start-Process powershell.exe -WindowStyle Minimized -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSScriptRoot\keep_awake.ps1`"")
    Write-Log "keep_awake iniciado"
}

if (-not (Test-ProcessRunning "python.exe" "*mt5bot.main panel*--watch*")) {
    # Solo lee datos. Si MT5 aún no conecta, lo anota en panel.log y reintenta en el siguiente ciclo.
    Start-Process $python -WindowStyle Hidden -WorkingDirectory $project `
        -ArgumentList @("-m", "mt5bot.main", "panel", "--watch", "$panelMinutes", "--no-open") `
        -RedirectStandardError (Join-Path $logDir "panel.log")
    Write-Log "vigilante del panel iniciado (cada $panelMinutes min)"
}

if (-not (Get-Process terminal64 -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $terminal })) {
    Start-Process $terminal
    Write-Log "MT5 abierto"
}

while (-not (Test-Path $stopFile)) {
    Wait-Mt5Ready
    $botLog = Join-Path $logDir "bot_${botName}_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
    Write-Log "bot arrancando en live; log en $botLog"
    $bot = Start-Process $python -ArgumentList @("-m", "mt5bot.main", "--config", $Config, "run", "--mode", "live") `
        -WorkingDirectory $project -RedirectStandardError $botLog -NoNewWindow -PassThru -Wait
    Write-Log "bot termino con codigo $($bot.ExitCode)"
    if (Test-Path $stopFile) { break }
    Start-Sleep -Seconds $retrySeconds
}
Write-Log "archivo STOP presente: el bot no se reinicia"
